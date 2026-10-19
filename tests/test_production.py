from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock

from froeling_bridge.errors import ValidationError
from froeling_bridge.production import Production, LIVE, GUARD, PREVIEW, P4D, TEST, TIMER, TestControlError
from froeling_bridge.storage import P4dDatabase, DatabaseConfig, MemoryRepository
from froeling_bridge.service import BridgeService
from froeling_bridge.client import ReadOnlyHeatingClient
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.api import create_app
from test_host_test import FakeSystem


class LiveSystem(FakeSystem):
    def __init__(self):
        super().__init__()
        self.units.update({LIVE: False, GUARD: False, PREVIEW: True})
        self.boot = {P4D: True, LIVE: False}
        self.fail_live = False

    def enabled(self, unit):
        return self.boot.get(unit, False)

    def enable(self, unit):
        self.events.append('enable:' + unit)
        self.boot[unit] = True

    def disable(self, unit):
        self.events.append('disable:' + unit)
        self.boot[unit] = False

    def preflight_live(self):
        self.events.append('preflight')

    def port_free(self):
        self.events.append('port-free')

    def live_ready(self, after):
        if self.fail_live:
            raise TestControlError('recording failed')
        return {'successful_cycles': 2}


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.system = LiveSystem()
        self.control = Production(self.system, Path(self.tmp.name))

    def test_live_activation_arms_guard_before_switch_and_preserves_boot_choice(self):
        result = self.control.start()
        self.assertTrue(result['live_active'])
        self.assertTrue(result['live_enabled'])
        self.assertFalse(result['p4d_enabled'])
        self.assertFalse(result['activation_guard'])
        self.assertLess(self.system.events.index('start:' + GUARD), self.system.events.index('stop:' + P4D))
        self.assertLess(self.system.events.index('stop:' + P4D), self.system.events.index('start:' + LIVE))

    def test_failed_recording_restores_original_and_its_autostart(self):
        self.system.fail_live = True
        with self.assertRaises(TestControlError):
            self.control.start()
        self.assertTrue(self.system.active(P4D))
        self.assertTrue(self.system.enabled(P4D))
        self.assertFalse(self.system.active(LIVE))
        self.assertFalse(self.system.enabled(LIVE))
        self.assertFalse(self.system.active(GUARD))

    def test_occupied_adapter_never_starts_competing_original(self):
        self.control.start()
        self.system.free = False
        self.system.events.clear()
        with self.assertRaises(TestControlError):
            self.control.rollback()
        self.assertNotIn('start:' + P4D, self.system.events)

    def test_original_restored_only_after_live_stopped(self):
        self.control.start()
        self.system.events.clear()
        result = self.control.rollback()
        self.assertTrue(result['p4d_active'])
        self.assertLess(self.system.events.index('stop:' + LIVE), self.system.events.index('start:' + P4D))

    def test_live_writer_requires_explicit_authorization_and_only_writes_sample_tables(self):
        with self.assertRaises(ValidationError):
            P4dDatabase(DatabaseConfig('p4', 'user'))
        config = MagicMock()
        connection = config.connect.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        repo = P4dDatabase(config, allow_recording=True)
        repo.store_cycle([dict(address=1, type='VA', value=42)], datetime(2026, 1, 1), 1)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        writes = [s for s in statements if s.startswith('INSERT')]
        self.assertEqual(len(writes), 2)
        self.assertTrue(writes[0].startswith('INSERT INTO samples '))
        self.assertTrue(writes[1].startswith('INSERT INTO peaks '))
        connection.commit.assert_called_once()

    def test_live_api_collects_but_rejects_heating_writes_before_transmission(self):
        transport = MemoryTransport()
        service = BridgeService(MemoryRepository(), mode='hardware-live', client=ReadOnlyHeatingClient(ProtocolSession(transport)), autostart=False)
        self.addCleanup(service.close)
        http = create_app(service, authentication=False).test_client()
        health = http.get('/api/v1/health').get_json()
        self.assertEqual(health['mode'], 'hardware-live')
        self.assertFalse(health['capabilities']['heating_write'])
        response = http.post('/api/v1/jobs', json=dict(operation='write_parameter', menu_id=2, value='67.5'))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(transport.requests, [])
        service.collect_once()
        self.assertGreater(service.collector_status()['stored'], 0)
        self.assertIsNone(service.fatal_reason)
