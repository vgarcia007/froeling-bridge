"""Independent guard uses cached API data only; recovery commands are mocked."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import tempfile
import json

spec = importlib.util.spec_from_file_location('bridge_guard', Path(__file__).resolve().parents[1] / 'deploy/libexec/froeling-bridge-health.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class HealthGuardTests(unittest.TestCase):
    def test_fresh_controller_status_does_not_hide_stale_measurements(self):
        now = datetime.now(timezone.utc)
        runtime = dict(phase='ready', connection=dict(connected=True, last_success=now.isoformat()))
        sensor = dict(supported=True, active=True, type='VA', latest=dict(
            origin='controller', observed_at=(now - timedelta(seconds=181)).isoformat()))
        self.assertFalse(guard.healthy(runtime, [sensor], now, 180))
        sensor['latest']['observed_at'] = now.isoformat()
        self.assertTrue(guard.healthy(runtime, [sensor], now, 180))
        sensor['latest']['origin'] = 'local-persisted'
        self.assertFalse(guard.healthy(runtime, [sensor], now, 180))

    def test_short_incident_recovers_without_switching_services(self):
        since, recover = guard.decide(None, 100, False)
        self.assertFalse(recover)
        self.assertEqual(guard.decide(since, 159, False), (100, False))
        self.assertEqual(guard.decide(since, 160, False), (100, True))
        self.assertEqual(guard.decide(since, 150, True), (None, False))
        self.assertEqual(guard.decide(since, 90, False), (90, False))
        self.assertEqual(guard.decide(since, 200, False, grace=700), (100, False))

    def test_future_and_naive_timestamps_cannot_count_as_current(self):
        now = datetime.now(timezone.utc)
        for stamp in [None, 'bad', now.replace(tzinfo=None).isoformat(),
                      (now + timedelta(seconds=20)).isoformat()]:
            self.assertFalse(guard.fresh(stamp, now, 180))

    def test_recovery_is_role_specific_and_never_replays_heating_operations(self):
        for fallback in (True, False):
            with self.subTest(fallback=fallback), tempfile.TemporaryDirectory() as directory:
                state = Path(directory)
                (state / 'installation.json').write_text(json.dumps(dict(p4d_fallback=fallback)))
                (state / 'health-failure.json').write_text(json.dumps(dict(since=100)))
                original_read = Path.read_text
                def read(path, *args, **kwargs):
                    return '{}' if str(path) == '/etc/froeling-bridge/settings.json' else original_read(path, *args, **kwargs)
                with patch.object(guard, 'STATE', state), patch.object(guard, 'active', side_effect=[True, False]), patch.object(guard.time, 'time', return_value=200), patch.object(Path, 'read_text', read):
                    opener = Mock()
                    opener.open.side_effect = OSError('private-details')
                    with patch.object(guard, 'build_opener', return_value=opener), patch.object(guard.subprocess, 'run') as run:
                        guard.main()
                        expected = [guard.HELPER, 'rollback'] if fallback else ['/usr/bin/systemctl', 'restart', 'froeling-bridge.service']
                        run.assert_called_once_with(expected, check=True, timeout=80)
                        self.assertFalse((state / 'health-failure.json').exists())


if __name__ == '__main__':
    unittest.main()
