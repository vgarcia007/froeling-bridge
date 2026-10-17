"""Source-derived p4d list behavior and failure visibility; no real heater."""
import tempfile
import unittest

from froeling_bridge.client import HeatingClient
from froeling_bridge.codec import Frame, StreamDecoder, encode_frame
from froeling_bridge.errors import ListLimitExceeded, RequestTimeout
from froeling_bridge.messages import Command
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.standalone import StandaloneRuntime


class DiscoveryRecoveryTests(unittest.TestCase):
    def test_list_check_precedes_each_first_request(self):
        transport = MemoryTransport()
        client = HeatingClient(ProtocolSession(transport))
        client.get_value_specs()
        client.get_menu()
        commands = [r.command for r in transport.requests]
        for first in (Command.VALUES_FIRST, Command.MENU_FIRST):
            i = commands.index(first)
            self.assertEqual(commands[i - 1], Command.CHECK)
            self.assertEqual(transport.requests[i - 1].payload, b'Tescht ;-)')

    def test_skipped_empty_entries_do_not_truncate_lists(self):
        for first, method in ((Command.VALUES_FIRST, 'get_value_specs'),
                              (Command.MENU_FIRST, 'get_menu')):
            with self.subTest(method=method):
                def empty_first(request, wire):
                    return encode_frame(Frame(first, b'\x01')) if request.command == first else wire
                transport = MemoryTransport(wire_filter=empty_first)
                result = getattr(HeatingClient(ProtocolSession(transport)), method)()
                original = transport.heater.value_specs if first == Command.VALUES_FIRST else transport.heater.menu
                self.assertEqual(result, original[1:])

    def test_all_empty_entries_still_obey_list_limit(self):
        def empty(request, wire):
            if request.command in (Command.VALUES_FIRST, Command.VALUES_NEXT):
                return encode_frame(Frame(request.command, b'\x01'))
            return wire
        transport = MemoryTransport(wire_filter=empty)
        client = HeatingClient(ProtocolSession(transport))
        with self.assertRaises(ListLimitExceeded):
            client.get_value_specs(max_items=3)
        self.assertEqual(len(transport.requests), 5)  # CHECK, three entries, limit probe.
        self.assertTrue(client.session.broken)

    def test_silent_controller_gets_two_seconds_per_reply_not_five_minutes(self):
        class Clock:
            now = 0.
            def __call__(self):
                return self.now
        clock = Clock()
        class Silence(MemoryTransport):
            def read(self, max_bytes, timeout):
                data = super().read(max_bytes, timeout)
                if timeout and not data:
                    self.timeout = timeout
                    clock.now += timeout
                return data
        def silent_list(request, wire):
            return b'' if request.command == Command.VALUES_FIRST else wire
        transport = Silence(wire_filter=silent_list)
        client = HeatingClient(ProtocolSession(transport, clock=clock))
        with self.assertRaisesRegex(RequestTimeout, 'request 0x31, entry 1'):
            client.get_value_specs(timeout=300)
        self.assertEqual(clock.now, 2.)
        self.assertEqual(transport.timeout, 2.)

    def test_reply_deadline_does_not_restart_with_each_fragment(self):
        class Clock:
            now = 0.
            def __call__(self):
                return self.now
        clock = Clock()
        class Slow(MemoryTransport):
            def read(self, max_bytes, timeout):
                data = super().read(max_bytes, timeout)
                if timeout:
                    clock.now += min(.4, timeout)
                return data
        transport = Slow(read_chunk_size=1)
        # The CHECK exchange itself must obey the same two-second cap.
        with self.assertRaises(RequestTimeout):
            HeatingClient(ProtocolSession(transport, clock=clock)).get_menu(timeout=300)
        self.assertLessEqual(clock.now, 2.)

    def test_per_reply_deadline_keeps_long_complete_list_working(self):
        class Clock:
            now = 0.
            def __call__(self):
                return self.now
        clock = Clock()
        class Delayed(MemoryTransport):
            def read(self, max_bytes, timeout):
                data = super().read(max_bytes, timeout)
                if timeout:
                    clock.now += min(.8, timeout)
                return data
        client = HeatingClient(ProtocolSession(Delayed(), clock=clock))
        self.assertEqual(len(client.get_menu(timeout=300)), 4)
        self.assertGreater(clock.now, 2.)

    def test_runtime_logs_protocol_failure_phase_and_location(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = StandaloneRuntime(directory, lambda: None, autostart=False)
            def fail():
                runtime.phase = 'discovery:sensors'
                runtime.stop.set()
                raise RequestTimeout('list 0x31, request 0x32, entry 8: response timed out')
            runtime.discover_once = fail
            try:
                with self.assertLogs('froeling_bridge.standalone', level='WARNING') as logs:
                    runtime._run()
                failure = runtime.status()['last_failure']
                self.assertEqual(failure['phase'], 'discovery:sensors')
                self.assertEqual(failure['error_type'], 'RequestTimeout')
                self.assertIn('entry 8', failure['detail'])
                self.assertIn('discovery:sensors', logs.output[0])
            finally:
                runtime.close()

    def test_arbitrary_storage_exception_text_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = StandaloneRuntime(directory, lambda: None, autostart=False)
            def fail():
                runtime.stop.set()
                raise OSError('PRIVATE-CONNECTION-DETAILS')
            runtime.discover_once = fail
            try:
                with self.assertLogs('froeling_bridge.standalone', level='WARNING') as logs:
                    runtime._run()
                self.assertIsNone(runtime.status()['last_failure']['detail'])
                self.assertNotIn('PRIVATE-CONNECTION-DETAILS', str(logs.output))
            finally:
                runtime.close()


if __name__ == '__main__':
    unittest.main()
