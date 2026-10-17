import fcntl
import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from froeling_bridge import lifecycle
from froeling_bridge.host_test import TestControlError


class LifecycleTests(unittest.TestCase):
    def test_first_reported_startup_failure_restores_p4d_without_waiting_for_deadline(self):
        from io import BytesIO

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / 'installation.json').write_text(json.dumps(dict(
                p4d_fallback=True, p4d_enabled=True, device='/dev/test', port=8000)))
            system = Mock()
            active = {lifecycle.GUARD}
            system.active.side_effect = lambda unit: unit in active
            system.start.side_effect = active.add
            system.stop.side_effect = active.discard
            response = BytesIO(json.dumps(dict(last_failure=dict(
                phase='discovery:sensors', error_type='RequestTimeout'))).encode())
            opener = Mock()
            opener.open.return_value = response
            with patch.object(lifecycle, 'STATE', state), patch.object(
                lifecycle, 'build_opener', return_value=opener
            ), patch.object(lifecycle.time, 'sleep') as sleep:
                with self.assertRaisesRegex(TestControlError, 'discovery:sensors'):
                    lifecycle.control('start', system)
            sleep.assert_not_called()
            system.stop.assert_any_call(lifecycle.LIVE)
            system.start.assert_any_call(lifecycle.P4D)
            system.boot.assert_any_call(lifecycle.P4D, True)

    def test_status_available_while_start_owns_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(lifecycle, 'STATE', Path(directory)):
                with open(Path(directory) / 'control.lock', 'a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    with patch.object(lifecycle, 'control', return_value={'running': True}):
                        self.assertEqual(lifecycle.locked_control('status'), {'running': True})

    def test_rollback_signals_activation_before_waiting_for_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            started, cancelled = Event(), Event()
            errors = []
            def activate():
                try:
                    with open(state / 'control.lock', 'a') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        started.set()
                        for _ in range(100):
                            if (state / 'cancel-start').exists():
                                cancelled.set()
                                return
                            Event().wait(.01)
                        raise AssertionError('activation never received cancellation')
                except BaseException as exc:
                    errors.append(exc)
            with patch.object(lifecycle, 'STATE', state):
                worker = Thread(target=activate)
                worker.start()
                self.assertTrue(started.wait(2))
                with patch.object(lifecycle, 'control', return_value={'p4d_active': True}) as control:
                    result = lifecycle.locked_control('rollback')
                worker.join(2)
                self.assertFalse(worker.is_alive())
                self.assertTrue(cancelled.is_set())
                self.assertEqual(errors, [])
                self.assertTrue(result['p4d_active'])
                control.assert_called_once_with('rollback')
                self.assertFalse((state / 'cancel-start').exists())

    def test_activation_cancellation_restores_original(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / 'installation.json').write_text(json.dumps(dict(
                p4d_fallback=True, p4d_enabled=True, device='/dev/test', port=8000)))
            system = Mock()
            system.active.side_effect = lambda unit: unit in (lifecycle.P4D, lifecycle.GUARD)
            def start(unit):
                if unit == lifecycle.LIVE:
                    (state / 'cancel-start').touch()
            system.start.side_effect = start
            with patch.object(lifecycle, 'STATE', state):
                with self.assertRaisesRegex(TestControlError, 'cancelled'):
                    lifecycle.control('start', system)
            system.stop.assert_any_call(lifecycle.LIVE)
            system.start.assert_any_call(lifecycle.P4D)
            system.boot.assert_any_call(lifecycle.P4D, True)


if __name__ == '__main__':
    unittest.main()
