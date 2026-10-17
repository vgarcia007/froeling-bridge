from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock
import uuid

from froeling_bridge.history import Historian, initialize_database
from froeling_bridge.local_store import LocalRepository
from froeling_bridge.storage import DatabaseConfig, DatabaseUnavailable, ZONE


@unittest.skipUnless(
    os.environ.get("FROELING_TEST_DB_CONFIG"), "separate MariaDB required"
)
class HistoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        base = DatabaseConfig.load(os.environ["FROELING_TEST_DB_CONFIG"])
        base.require_test()
        self.config = replace(
            base, database="froeling_bridge_test_history_" + uuid.uuid4().hex[:10]
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.local = LocalRepository(Path(self.temp.name) / "local.sqlite3")
        self.repo = initialize_database(self.config, self.local)
        self.history = Historian(self.repo, self.local, autostart=False)
        self.addCleanup(self.history.close)
        self.history.history_days = 91
        self.history.aggregate_minutes = 30

    def rows(self):
        with self.repo.transaction() as c:
            c.execute(
                "SELECT address,type,aggregate,time,value,samples FROM samples ORDER BY time,aggregate"
            )
            return c.fetchall()

    def point(self, when, value):
        self.repo.store_cycle(
            [dict(type="VA", address=1, value=value, text="test")],
            when,
            int(when.replace(tzinfo=ZONE).timestamp()),
        )

    def test_empty_database_created_and_repeated_setup_preserves_existing_data(self):
        self.point(datetime(2026, 1, 1), 42)
        second = initialize_database(self.config, self.local)
        self.assertEqual(len(self.rows()), 1)
        second.validate_schema()
        with self.repo.transaction() as c:
            c.execute("SHOW TABLES")
            self.assertEqual(len(c.fetchall()), 7)

    def test_existing_compatible_database_never_initializes_or_changes_metadata(self):
        self.point(datetime(2026, 1, 1), 42)
        other = LocalRepository(Path(self.temp.name) / "other.sqlite3")
        initialize_database(self.config, other)
        self.assertIsNone(other.get_meta("database_initialization"))
        self.assertEqual(len(self.rows()), 1)

    def test_aggregation_means_counts_boundaries_and_recent_values(self):
        for t, v in [
            (datetime(2026, 1, 1, 12, 0), 10),
            (datetime(2026, 1, 1, 12, 29), 20),
            (datetime(2026, 1, 1, 12, 30), 40),
            (datetime(2026, 9, 30), 99),
        ]:
            self.point(t, v)
        self.history.aggregate(datetime(2026, 10, 17, 1, tzinfo=ZONE))
        rows = self.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            (
                rows[0]["aggregate"],
                rows[0]["value"],
                rows[0]["samples"],
                rows[0]["time"],
            ),
            ("A", 15, 2, datetime(2026, 1, 1, 12, 30)),
        )
        self.assertEqual(rows[1]["value"], 40)
        self.assertEqual(rows[2]["aggregate"], "S")
        before = self.rows()
        self.history.aggregate(datetime(2026, 10, 17, 1, tzinfo=ZONE))
        self.assertEqual(before, self.rows())

    def test_existing_aggregate_conflict_keeps_raw_and_original_aggregate(self):
        self.point(datetime(2026, 1, 1, 12), 10)
        with self.repo.transaction(writable=True) as c:
            c.execute(
                "INSERT INTO samples(address,type,aggregate,time,value,samples) VALUES(1,'VA','A',%s,99,7)",
                (datetime(2026, 1, 1, 12, 30),),
            )
        before = self.rows()
        self.history.aggregate(datetime(2026, 10, 17, 1, tzinfo=ZONE))
        self.assertEqual(before, self.rows())
        self.assertEqual(self.history.status()["aggregation"]["conflicts"], 1)

    def test_failure_between_insert_and_delete_rolls_back_both(self):
        self.point(datetime(2026, 1, 1, 12), 10)
        original = self.repo.transaction

        class FailingCursor:
            def __init__(self, c):
                self.c = c

            def execute(self, sql, args=None):
                if sql.startswith("DELETE FROM samples"):
                    raise RuntimeError("injected delete failure")
                return self.c.execute(sql, args)

            def __getattr__(self, name):
                return getattr(self.c, name)

        @contextmanager
        def fail(writable=False):
            with original(writable) as c:
                yield FailingCursor(c)

        self.repo.transaction = fail
        with self.assertRaises(DatabaseUnavailable):
            self.history.aggregate(datetime(2026, 10, 17, 1, tzinfo=ZONE))
        self.repo.transaction = original
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["aggregate"], "S")

    def test_incomplete_cutoff_bucket_kept_and_disabled_aggregation_does_nothing(self):
        now = datetime(2026, 10, 17, 1, 17, tzinfo=ZONE)
        cutoff = (now - timedelta(days=91)).replace(tzinfo=None)
        self.point(cutoff.replace(minute=5), 10)
        self.history.aggregate(now)
        self.assertEqual(self.rows()[0]["aggregate"], "S")
        self.history.history_days = 0
        self.history.aggregate(now + timedelta(days=200))
        self.assertEqual(self.rows()[0]["aggregate"], "S")

    def test_flags_sync_catalogue_and_no_other_settings_changed(self):
        sensor = dict(
            type="VA",
            address=1,
            state="A",
            record="D",
            factor=1,
            res1=1,
            unit="C",
            title="Demo",
            usrtitle="Custom",
        )
        menu = [
            dict(
                id=1,
                parent=1,
                child=0,
                type=3,
                address=1,
                title="Demo",
                unit="C",
                unknown1=0,
                unknown2=0,
            )
        ]
        self.local.replace_catalogue([sensor], menu)
        self.history.sync_catalogue()
        self.local.patch_sensor("VA", 1, dict(record=True))
        self.history.sync_flags()
        with self.repo.transaction() as c:
            c.execute(
                "SELECT state,record,usrtitle FROM valuefacts WHERE type='VA' AND address=1"
            )
            self.assertEqual(
                c.fetchone(), dict(state="A", record="A", usrtitle="Custom")
            )
        self.assertEqual(self.local.pending_changes(), [])

    def test_invalid_aggregation_configuration_does_not_prevent_recording(self):
        with self.repo.transaction(writable=True) as c:
            c.execute(
                "INSERT INTO config(owner,name,value) VALUES('p4d','aggregateInterval','bad')"
            )
        self.history._settings()
        self.assertEqual(self.history.history_days, 0)
        self.point(datetime(2026, 1, 1), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_dst_repeated_hour_uses_existing_p4d_local_time_identity(self):
        self.point(datetime(2025, 10, 26, 2, 10), 10)
        self.point(datetime(2025, 10, 26, 2, 20), 20)
        self.history.aggregate(datetime(2026, 10, 17, 1, tzinfo=ZONE))
        row = self.rows()[0]
        self.assertEqual(
            (row["time"], row["value"], row["samples"]),
            (datetime(2025, 10, 26, 2, 30), 15, 2),
        )


    def test_error_sync_preserves_occurrences_ids_mail_counters_and_does_not_delete(self):
        from test_controller_errors import event
        def sync(data, stamp):
            self.local.set_meta('controller_errors', dict(events=data,observed_at=stamp))
            self.history.sync_errors()
            self.assertTrue(self.history.status()['controller_errors']['available'])
        sync([event(1)],'first')
        with self.repo.transaction(writable=True) as c:
            c.execute("UPDATE errors SET mailcnt=9")
        sync([event(1),event(4,11),event(2,12)],'second')
        with self.repo.transaction() as c:
            c.execute('SELECT * FROM errors'); rows=c.fetchall()
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row['state'],'quittiert');self.assertEqual(row['mailcnt'],9)
        self.assertEqual(row['time4'],datetime(2026,1,1,11))
        self.assertEqual(row['time2'],datetime(2026,1,1,12))
        sync([event(1),event(4,11)],'third')  # Old heater data cannot regress acknowledged state.
        sync([],'empty')  # Empty heater list never erases database history.
        with self.repo.transaction() as c:
            c.execute('SELECT * FROM errors');self.assertEqual(c.fetchall(),rows)
        sync([event(1,13)],'new occurrence')
        with self.repo.transaction() as c:
            c.execute('SELECT count(*) AS n FROM errors');self.assertEqual(c.fetchone()['n'],2)

    def test_live_error_transitions_refresh_existing_row_and_repair_missing_times(self):
        from test_controller_errors import event
        def sync(events,stamp):
            self.local.set_meta('controller_errors',dict(events=events,observed_at=stamp))
            self.history.sync_errors()
            self.assertTrue(self.history.status()['controller_errors']['available'])
            with self.repo.transaction() as c:
                c.execute('SELECT * FROM errors');rows=c.fetchall()
            self.assertEqual(len(rows),1)
            return rows[0]
        first=sync([event(1)],'arrival')
        gone=sync([event(1),event(4,11)],'departure')
        self.assertEqual((gone['id'],gone['state'],gone['time4']),(first['id'],'gegangen',datetime(2026,1,1,11)))
        ack=sync([event(1),event(4,11),event(2,12)],'acknowledgement')
        self.assertEqual((ack['id'],ack['state'],ack['time2']),(first['id'],'quittiert',datetime(2026,1,1,12)))
        with self.repo.transaction(writable=True) as c:
            c.execute('UPDATE errors SET time2=NULL,time4=NULL,mailcnt=7')
        repaired=sync([event(1),event(4,11),event(2,12)],'repair same label')
        self.assertEqual(repaired['id'],first['id'])
        self.assertEqual(repaired['state'],'quittiert');self.assertEqual(repaired['mailcnt'],7)
        self.assertEqual(repaired['time4'],datetime(2026,1,1,11))
        self.assertEqual(repaired['time2'],datetime(2026,1,1,12))
        repeated=sync([event(1),event(4,11),event(2,12)],'repeat after restart')
        self.assertEqual(repaired,repeated)

    def test_error_history_pages_all_database_rows_in_original_order_without_writes(self):
        from froeling_bridge.storage import ReadOnlyDatabase
        with self.repo.transaction(writable=True) as c:
            for n in range(105):
                c.execute("INSERT INTO errors(number,state,text,time1) VALUES(%s,'quittiert','Fictional stored error',%s)",(n,datetime(2020,1,1)))
        reader=ReadOnlyDatabase(self.config)
        first=reader.error_history(limit=100)
        second=reader.error_history(limit=100,offset=100)
        self.assertEqual((first['total'],len(first['items']),first['has_more']),(105,100,True))
        self.assertEqual((len(second['items']),second['has_more']),(5,False))
        ids=[row['id'] for row in first['items']+second['items']]
        self.assertEqual(ids,sorted(ids,reverse=True))
        self.assertEqual(len(set(ids)),105)
        self.assertEqual(reader.error_history(offset=105)['items'],[])

    def test_error_sync_rolls_back_partial_write_and_remains_independent_of_samples(self):
        from test_controller_errors import event
        self.history._errors_schema_ready=True
        original=self.repo.transaction
        class Cursor:
            def __init__(self,c):self.c=c;self.count=0
            def execute(self,sql,args=None):
                if sql.startswith('INSERT INTO errors'):
                    self.count+=1
                    if self.count==2:raise RuntimeError('test interruption')
                return self.c.execute(sql,args)
            def __getattr__(self,name):return getattr(self.c,name)
        @contextmanager
        def failing(writable=False):
            with original(writable=writable) as c:yield Cursor(c)
        self.local.set_meta('controller_errors',dict(observed_at='first',events=[event(1),event(1,13)]))
        self.repo.transaction=failing
        self.history.sync_errors()
        self.assertFalse(self.history.status()['controller_errors']['available'])
        self.assertIsNone(self.history._errors_stamp)
        self.repo.transaction=original
        with self.repo.transaction() as c:
            c.execute('SELECT count(*) AS n FROM errors');self.assertEqual(c.fetchone()['n'],0)
        self.point(datetime(2026,1,1),42)
        self.assertEqual(len(self.rows()),1)
        self.history._errors_retry=0
        self.history.sync_errors()
        self.assertTrue(self.history.status()['controller_errors']['available'])



class HistoryIsolationTests(unittest.TestCase):
    def test_unavailable_historian_does_not_block_acceptance_and_drops_without_replay(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            local = LocalRepository(Path(directory) / "local.sqlite3")
            repo = Mock()
            repo.transaction.side_effect = DatabaseUnavailable()
            h = Historian(repo, local)
            try:
                count = h.enqueue(
                    [dict(type="VA", address=1, value=10)], datetime(2026, 1, 1), 1
                )
                self.assertEqual(count, 1)
                for _ in range(100):
                    if h.status()["dropped_cycles"]:
                        break
                    time.sleep(0.01)
                self.assertEqual(h.status()["dropped_cycles"], 1)
                self.assertFalse(h.status()["available"])
                repo.store_cycle.assert_not_called()
            finally:
                h.close()
