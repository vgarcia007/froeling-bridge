from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from froeling_bridge.controller_errors import merge_events, view
from froeling_bridge.messages import ErrorEntry
from froeling_bridge.errors import RequestTimeout, ValidationError
from froeling_bridge.standalone import StandaloneRuntime
from froeling_bridge.client import HeatingClient
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.api import create_app


def event(state, hour=10, number=7, text='Fiktiver Fehler'):
    return dict(number=number, state=state, info=3, text=text,
                local_time=datetime(2026, 1, 1, hour).isoformat())


class ErrorMergeTests(unittest.TestCase):
    def test_arrival_departure_acknowledgement_and_repeated_occurrences(self):
        rows, changed = merge_events([event(1),event(4,11),event(2,12),event(1,13)])
        self.assertEqual(len(changed),2)
        first=rows[(7,datetime(2026,1,1,10))]
        self.assertEqual(first['state'],'quittiert')
        self.assertEqual(first['time4'],datetime(2026,1,1,11))
        self.assertEqual(first['time2'],datetime(2026,1,1,12))
        self.assertEqual(rows[(7,datetime(2026,1,1,13))]['state'],'gekommen')

    def test_original_transition_guards_preserve_ack_and_metadata(self):
        key=(7,datetime(2026,1,1,10))
        existing={key:dict(id=42,number=7,time1=key[1],state='quittiert',text='Original',info=9)}
        rows,changed=merge_events([event(1),event(4,11)],existing)
        self.assertFalse(changed)
        self.assertEqual(rows,existing)

    def test_orphans_skipped_and_ack_resets_anchor_like_original(self):
        rows,_=merge_events([event(4),event(2),event(1),event(2,11),event(4,12)])
        self.assertEqual(len(rows),1)
        self.assertNotIn('time4',next(iter(rows.values())))

    def test_empty_snapshot_preserves_old_rows_and_unknown_state_rejected(self):
        self.assertEqual(merge_events([],{'old':{'state':'quittiert'}}),({'old':{'state':'quittiert'}},set()))
        with self.assertRaises(ValidationError):merge_events([event(3)])
        self.assertFalse(view({})['available'])
        self.assertTrue(view({})['stale'])

    def test_runtime_persists_and_serves_without_reading_on_get_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as d:
            heater=demo_heater()
            heater.errors=(ErrorEntry(7,3,1,datetime(2026,1,1,10),b'Fictional'),ErrorEntry(7,3,4,datetime(2026,1,1,11),b'Fictional'))
            transport=MemoryTransport(heater)
            runtime=StandaloneRuntime(d,lambda:(HeatingClient(ProtocolSession(transport)),lambda:None),simulator=True,autostart=False)
            try:
                runtime.refresh_errors()
                api=create_app(runtime.service).test_client()
                before=len(transport.requests)
                result=api.get('/api/v1/errors').get_json()
                self.assertTrue(result['available']);self.assertFalse(result['stale'])
                self.assertEqual(result['items'][0]['state'],'gegangen')
                self.assertEqual(len(transport.requests),before)
                old=result['observed_at']
                runtime.client.inner.get_errors=Mock(side_effect=RequestTimeout())
                with self.assertLogs('froeling_bridge.standalone',level='WARNING'):runtime.refresh_errors()
                result=api.get('/api/v1/errors').get_json()
                self.assertEqual(result['observed_at'],old);self.assertIsNotNone(result['error'])
                self.assertEqual(len(result['items']),1)
                self.assertTrue((Path(d)/'catalogue.sqlite3').exists())
            finally:runtime.close()
