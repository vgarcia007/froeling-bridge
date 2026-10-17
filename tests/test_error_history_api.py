from pathlib import Path
from datetime import datetime
import tempfile
import unittest
from unittest.mock import Mock, patch
from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.standalone import StandaloneRuntime
from froeling_bridge.storage import DatabaseUnavailable, DatabaseConfig
from froeling_bridge.messages import ErrorEntry


class ErrorHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        h=demo_heater();h.errors=(ErrorEntry(7,0,1,datetime(2026,1,1,10),b'Fictional'),)
        self.transport=MemoryTransport(h)
        self.runtime=StandaloneRuntime(self.directory.name,lambda:(HeatingClient(ProtocolSession(self.transport)),lambda:None),simulator=True,autostart=False)
        self.addCleanup(self.runtime.close)
        self.runtime.refresh_errors();self.http=create_app(self.runtime.service).test_client()

    def test_default_returns_database_history_and_controller_is_explicit(self):
        self.runtime.database_config=DatabaseConfig('froeling_bridge_test_mock','test')
        row=dict(id=42,number=99,info=0,state='quittiert',text='Old stored error',time1=datetime(2020,1,1))
        with patch('froeling_bridge.storage.ReadOnlyDatabase') as db:
            db.return_value.error_history.return_value=dict(items=[row],total=86,offset=0,limit=100,has_more=False)
            count=len(self.transport.requests)
            data=self.http.get('/api/v1/errors').get_json()
            self.assertEqual(data['source'],'p4d-database');self.assertEqual(data['total'],86)
            self.assertEqual(data['items'][0]['id'],42);self.assertTrue(data['history_available'])
            self.assertIsNotNone(data['read_at'])
            self.assertEqual(len(self.transport.requests),count)
            db.reset_mock()
            data=self.http.get('/api/v1/errors?source=controller').get_json()
            self.assertEqual(data['total'],1);self.assertEqual(data['source'],'controller-error-memory')
            db.assert_not_called()

    def test_database_failure_is_explicit_and_history_only_is_503(self):
        self.runtime.database_config=DatabaseConfig('froeling_bridge_test_mock','test')
        with patch('froeling_bridge.storage.ReadOnlyDatabase') as db:
            db.return_value.error_history.side_effect=DatabaseUnavailable()
            data=self.http.get('/api/v1/errors').get_json()
            self.assertTrue(data['fallback']);self.assertFalse(data['history_available'])
            self.assertIsNotNone(data['history_error']);self.assertEqual(data['total'],1)
            self.assertEqual(self.http.get('/api/v1/errors?source=history').status_code,503)
        self.assertIsNone(self.runtime.service.fatal_reason)

    def test_no_database_uses_persistent_controller_page_with_total(self):
        data=self.http.get('/api/v1/errors?limit=1&offset=1').get_json()
        self.assertEqual(data['total'],1);self.assertEqual(data['items'],[])
        self.assertFalse(data['has_more']);self.assertFalse(data['history_configured'])
        self.assertFalse(data['fallback'])
        self.assertEqual(self.http.get('/api/v1/errors?source=history').status_code,503)

    def test_query_validation(self):
        for query in ('source=other','limit=0','limit=1001','offset=-1','offset=1000001','limit=hello','extra=1','limit=1&limit=2'):
            with self.subTest(query=query):self.assertEqual(self.http.get('/api/v1/errors?'+query).status_code,400)
