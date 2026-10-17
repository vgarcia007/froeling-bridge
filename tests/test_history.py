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
            self.assertEqual(len(c.fetchall()), 6)

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
