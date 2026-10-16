from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from froeling_bridge.errors import ValidationError
from froeling_bridge.storage import (DatabaseConfig, DatabaseUnavailable, MemoryRepository,
                                     ReadOnlyDatabase, TestDatabase)


class StorageTests(unittest.TestCase):
    def test_test_writer_guard(self):
        for host, name in [('example.invalid','froeling_bridge_test_demo'), ('127.0.0.1','p4'),
                           ('127.0.0.1','froeling_bridge_test_x`'), ('127.0.0.2','froeling_bridge_test_demo')]:
            with self.assertRaises(ValidationError):
                TestDatabase(DatabaseConfig(name, 'user', host=host))
        TestDatabase(DatabaseConfig('froeling_bridge_test_demo','user'))

    def test_readonly_cannot_request_write_transaction(self):
        repo = ReadOnlyDatabase(DatabaseConfig('p4','user'))
        with self.assertRaises(ValidationError):
            with repo.transaction(writable=True):
                self.fail('must reject before connecting')

    def test_credentials_not_in_repr_or_configuration_errors(self):
        self.assertNotIn('SECRET', repr(DatabaseConfig('test','user','SECRET')))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            path.write_text('{"password":"SECRET", "unknown":true}')
            with self.assertRaisesRegex(ValidationError, '^invalid database configuration file$'):
                DatabaseConfig.load(path)

    def test_collision_keeps_original_inssp_and_updates_peak(self):
        repo = MemoryRepository()
        when = datetime(2026, 10, 25, 2, 30)
        for value, stamp in [('10.5', 1792888200), ('5.5', 1792891800)]:
            repo.store_cycle([dict(address=1,type='VA',value=value)], when, stamp)
        row = next(iter(repo.rows.values()))
        self.assertEqual(row['inssp'],1792888200)
        self.assertEqual(row['updsp'],1792891800)
        self.assertEqual(row['value'],Decimal('5.5'))
        self.assertEqual(repo.peaks[(1,'VA')],(Decimal('5.5'),Decimal('10.5')))

    def test_identity_filter_limits_and_invalid_samples(self):
        repo = MemoryRepository(max_samples=2)
        when = datetime(2026,1,1)
        for kind,value in [('VA',3),('DO',1)]:
            repo.store_cycle([dict(address=1,type=kind,value=value)],when,1)
        rows = repo.history(1,'DO',when,when+timedelta(seconds=1))
        self.assertEqual(rows[0]['value'],1)
        self.assertEqual(len(rows),1)
        repo.store_cycle([dict(address=2,type='VA',value=4)],when,2)
        self.assertEqual(len(repo.rows),2)
        for sample in [dict(address=3,type='VA',value='NaN'),dict(address=3,type='VA',value=1,text='x'*51)]:
            with self.assertRaises(ValidationError):repo.store_cycle([sample],when,3)
        self.assertEqual(len(repo.rows),2)

    def test_ambiguous_commit_is_not_retried_or_exposed(self):
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        connection.commit.side_effect = RuntimeError('SECRET')
        config = Mock()
        config.connect.return_value = connection
        repo = TestDatabase(config)
        with self.assertRaisesRegex(DatabaseUnavailable, '^database operation failed$'):
            repo.store_cycle([dict(address=1,type='VA',value=1)],datetime(2026,1,1),1)
        config.connect.assert_called_once()
        connection.commit.assert_called_once()
        connection.rollback.assert_called_once()
        self.assertFalse(repo.available)


@unittest.skipUnless(os.environ.get('FROELING_TEST_DB_CONFIG'), 'set FROELING_TEST_DB_CONFIG for local MariaDB integration')
class MariaDBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from froeling_bridge.testdb import initialize
        base = DatabaseConfig.load(os.environ['FROELING_TEST_DB_CONFIG'])
        base.require_test()
        cls.config = replace(base,database=base.database+'_'+uuid.uuid4().hex[:8])
        initialize(cls.config)
        cls.repo = TestDatabase(cls.config)

    def setUp(self):
        with self.repo.transaction(writable=True) as cursor:
            cursor.execute('DELETE FROM samples')
            cursor.execute('DELETE FROM peaks')

    def rows(self, table):
        with self.repo.transaction() as cursor:
            cursor.execute('SELECT * FROM '+table)
            return list(cursor.fetchall())

    def test_schema_matches_known_columns_types_and_keys(self):
        snapshot = json.loads(Path('docs/live-schema.json').read_text())
        expected = {(c['table_name'],c['column_name']):(c['column_type'],c['is_nullable'],c['column_key'])
                    for c in snapshot['columns'] if c['table_name'] in ('valuefacts','menu','samples','peaks')}
        with self.repo.transaction() as cursor:
            cursor.execute('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s',(self.config.database,))
            actual={(r['TABLE_NAME'],r['COLUMN_NAME']):(r['COLUMN_TYPE'],r['IS_NULLABLE'],r['COLUMN_KEY']) for r in cursor.fetchall()}
        self.assertEqual(actual,expected)

    def test_roundtrip_collision_peaks_and_scaled_history(self):
        when = datetime(2026,10,25,2,30)
        self.repo.store_cycle([dict(address=43,type='VA',value=Decimal('-1.2')),dict(address=43,type='DO',value=1)],when,100)
        self.repo.store_cycle([dict(address=43,type='VA',value=Decimal('2.3'))],when,200)
        rows=self.repo.history(43,'VA',when,when+timedelta(seconds=1))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],Decimal('2.3'))
        self.assertEqual((rows[0]['inssp'],rows[0]['updsp']),(100,200))
        self.assertEqual(len(self.rows('samples')),2)
        peak=next(r for r in self.rows('peaks') if r['type']=='VA')
        self.assertEqual((peak['minv'],peak['maxv']),(-1.2,2.3))

    def test_failure_rolls_back_samples_and_peaks(self):
        with self.assertRaises(DatabaseUnavailable):
            self.repo.store_cycle([dict(address=1,type='VA',value=1),dict(address=2,type='VA',value='1e99')],datetime(2026,1,1),100)
        self.assertEqual(self.rows('samples'),[])
        self.assertEqual(self.rows('peaks'),[])

    def test_read_only_transaction_rejects_mutation_on_server(self):
        repo = ReadOnlyDatabase(self.config)
        self.assertEqual(len(repo.sensors()),5)
        with self.assertRaises(DatabaseUnavailable):
            with repo.transaction() as cursor:
                cursor.execute("INSERT INTO peaks (address,type) VALUES (123,'VA')")
        self.assertEqual(self.rows('peaks'),[])
        self.assertEqual(len(repo.menu(10)),3)

    def test_service_repeated_cycles_and_readonly_api(self):
        from froeling_bridge.api import create_app
        from froeling_bridge.service import BridgeService
        from unittest.mock import patch
        service=BridgeService(self.repo,mode='demo-db',autostart=False)
        self.addCleanup(service.close)
        for stamp in (1700000000,1700000060):
            with patch('froeling_bridge.service.time.time',return_value=stamp):service.collect_once()
        self.assertEqual(len(self.rows('samples')),10)
        self.assertEqual(service.collector_status()['errors'],[])
        view=BridgeService(ReadOnlyDatabase(self.config),mode='database')
        self.addCleanup(view.close)
        http=create_app(view).test_client()
        r=http.get('/api/v1/history?address=43&type=VA&start=2023-11-14&end=2023-11-16')
        self.assertEqual(r.status_code,200)
        self.assertEqual([row['value'] for row in r.get_json()['items']],['-1.2','-1.2'])
        self.assertEqual(http.post('/api/v1/jobs',json={'operation':'write_parameter','menu_id':2,'value':'70.0'}).status_code,409)

    def test_initializer_refuses_existing_tables(self):
        from froeling_bridge.testdb import initialize
        with self.assertRaisesRegex(ValidationError,'must be empty'):
            initialize(self.config)
        self.assertEqual(len(self.repo.sensors()),5)
