from dataclasses import replace
from datetime import time
from decimal import Decimal
import threading
import unittest

from froeling_bridge.client import HeatingClient, WriteStatus
from froeling_bridge.codec import Frame, StreamDecoder, encode_frame
from froeling_bridge.errors import (
    ChecksumError, ListLimitExceeded, MalformedPayload, RequestTimeout,
    SessionBroken, TransportError, UnexpectedData, UnexpectedReply,
    ValidationError, WriteOutcomeUnknown, WriteVerificationError,
)
from froeling_bridge.messages import Command, ParameterType, TimeRange
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater


def frames(wire):
    decoder = StreamDecoder()
    result = decoder.feed(wire)
    decoder.finish()
    return result


def change_reply(wire, transform):
    return b"".join(encode_frame(transform(frame)) for frame in frames(wire))


class ClientTests(unittest.TestCase):
    def make_client(self, **kwargs):
        transport = MemoryTransport(**kwargs)
        return HeatingClient(ProtocolSession(transport)), transport

    def test_reads_status_firmware_specs_menu_io_errors_and_measurements(self):
        client, transport = self.make_client(read_chunk_size=1, max_write=1)
        self.assertEqual(client.get_status().state_text, "Bereit")
        self.assertEqual(client.get_firmware().version_text, "00.00.00.01")
        self.assertEqual(client.get_measurement(0x2B, 10, 2), Decimal("-1.2"))
        self.assertEqual(client.get_measurement(0x100, 1, 1), 60000)
        self.assertEqual(client.get_io(1).state, 0)
        self.assertEqual(len(client.get_menu()), 4)
        self.assertEqual(len(client.get_value_specs()), 2)
        self.assertEqual(len(client.get_errors()), 1)
        # List cursors are restarted on each new First call.
        self.assertEqual(client.get_menu(), client.get_menu())
        self.assertFalse(client.session.broken)

    def test_parameter_write_uses_fresh_metadata_two_acks_and_readback(self):
        client, transport = self.make_client(read_chunk_size=1, max_write=2)
        result = client.set_parameter(0x1234, "67.5")
        self.assertEqual(result.status, WriteStatus.CONFIRMED)
        self.assertEqual(result.previous.value, 65)
        self.assertEqual(result.current.value, Decimal("67.5"))
        self.assertEqual(len(result.acknowledgements), 2)
        self.assertEqual([r.command for r in transport.requests], [0x55, 0x39, 0x55])
        self.assertEqual(transport.requests[1].payload, bytes.fromhex("12 34 02 A3"))
        self.assertEqual(transport.heater.parameter_write_count, 1)

    def test_unchanged_parameter_does_not_send_write(self):
        client, transport = self.make_client()
        result = client.set_parameter(0x1234, 65)
        self.assertEqual(result.status, WriteStatus.UNCHANGED)
        self.assertEqual([r.command for r in transport.requests], [0x55])
        self.assertEqual(transport.heater.parameter_write_count, 0)

    def test_rejected_input_does_not_send_write_and_session_stays_usable(self):
        client, transport = self.make_client()
        for value in [91, "65.05", True, "NaN", "65,5"]:
            with self.assertRaises(ValidationError):
                client.set_parameter(0x1234, value)
        self.assertEqual(transport.heater.parameter_write_count, 0)
        self.assertFalse(client.session.broken)
        self.assertEqual(client.get_parameter(0x1234).value, 65)

    def test_bool_and_single_time_writes(self):
        client, transport = self.make_client()
        self.assertEqual(client.set_parameter(0x2B, False, ParameterType.BOOLEAN).current.raw_value, 0)
        self.assertEqual(client.set_parameter(0x200, "06:19", ParameterType.TIME).current.raw_value, 379)
        self.assertEqual(transport.heater.parameter_write_count, 2)

    def test_validation_before_request_for_bad_address_or_measurement_factor(self):
        client, transport = self.make_client()
        with self.assertRaises(ValidationError):
            client.get_parameter(0xFFFF)
        with self.assertRaises(ValidationError):
            client.get_measurement(1, 0, 1)
        self.assertEqual(transport.requests, [])

    def test_mismatched_parameter_address_prevents_write(self):
        def fault(request, wire):
            if request.command == Command.PARAMETER:
                return change_reply(wire, lambda f: Frame(f.command, f.payload[:1] + b"\x00\x01" + f.payload[3:]))
            return wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(UnexpectedReply):
            client.set_parameter(0x1234, 66)
        self.assertEqual(transport.heater.parameter_write_count, 0)
        self.assertTrue(client.session.broken)

    def test_failed_metadata_read_prevents_write(self):
        client, transport = self.make_client(wire_filter=lambda request, wire: b"")
        with self.assertRaises(RequestTimeout):
            client.set_parameter(0x1234, 66)
        self.assertEqual(transport.heater.parameter_write_count, 0)

    def test_missing_second_ack_is_unknown_even_if_simulator_applied_value(self):
        def fault(request, wire):
            return encode_frame(frames(wire)[0]) if request.command == Command.SET_PARAMETER else wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertIsInstance(raised.exception.__cause__, RequestTimeout)
        self.assertEqual(transport.heater.parameters[0x1234].raw_value, 660)
        self.assertEqual(transport.heater.parameter_write_count, 1)
        with self.assertRaises(SessionBroken):
            client.set_parameter(0x1234, 66)
        self.assertEqual(transport.heater.parameter_write_count, 1)

    def test_stale_data_detected_before_write_is_not_an_uncertain_write(self):
        def fault(request, wire):
            if request.command == Command.PARAMETER:
                return wire + encode_frame(Frame(0x39, bytes.fromhex("12 34 02 A3")))
            return wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(UnexpectedData):
            client.set_parameter(0x1234, 66)
        self.assertEqual(transport.heater.parameter_write_count, 0)

    def test_extra_data_at_write_transaction_exit_is_not_false_success(self):
        heater = demo_heater()
        def fault(request, wire):
            if request.command == Command.PARAMETER and heater.parameter_write_count:
                return wire + encode_frame(Frame(0x39, bytes.fromhex("12 34 02 A3")))
            return wire
        client, _ = self.make_client(heater=heater, wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertEqual(raised.exception.stage, "transaction completion")
        self.assertIsInstance(raised.exception.__cause__, UnexpectedData)

    def test_wrong_ack_address_is_not_accepted(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                return change_reply(wire, lambda f: Frame(f.command, b"\x00\x01" + f.payload[2:]))
            return wire
        client, _ = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertIsInstance(raised.exception.__cause__, UnexpectedReply)

    def test_ack_values_do_not_replace_readback_or_invent_ack_meaning(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                return change_reply(wire, lambda f: Frame(f.command, f.payload[:2] + (650).to_bytes(2, "big")))
            return wire
        client, _ = self.make_client(wire_filter=fault)
        result = client.set_parameter(0x1234, 66)
        self.assertEqual(result.status, WriteStatus.CONFIRMED)
        self.assertEqual(result.current.raw_value, 660)
        self.assertEqual(result.acknowledgements[0].raw_value, 650)

    def test_missing_readback_is_unknown_not_success(self):
        heater = demo_heater()
        def fault(request, wire):
            if request.command == Command.PARAMETER and heater.parameter_write_count:
                return b""
            return wire
        client, _ = self.make_client(heater=heater, wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertEqual(raised.exception.stage, "readback")

    def test_wrong_readback_is_known_verification_failure(self):
        heater = demo_heater()
        def fault(request, wire):
            if request.command == Command.PARAMETER and heater.parameter_write_count:
                return encode_frame(Frame(request.command, replace(heater.parameters[0x1234], raw_value=650).to_payload()))
            return wire
        client, transport = self.make_client(heater=heater, wire_filter=fault)
        with self.assertRaises(WriteVerificationError) as raised:
            client.set_parameter(0x1234, 66)
        self.assertEqual(raised.exception.actual.raw_value, 650)
        self.assertEqual(transport.heater.parameter_write_count, 1)
        self.assertTrue(client.session.broken)

    def test_changed_factor_cannot_falsely_confirm_display_value(self):
        heater = demo_heater()
        def fault(request, wire):
            if request.command == Command.PARAMETER and heater.parameter_write_count:
                return encode_frame(Frame(request.command, replace(heater.parameters[0x1234], factor=20).to_payload()))
            return wire
        client, _ = self.make_client(heater=heater, wire_filter=fault)
        with self.assertRaises(WriteVerificationError):
            client.set_parameter(0x1234, 66)

    def test_bad_checksum_during_write_is_unknown(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                data = bytearray(wire)
                data[-1] ^= 0x80
                return bytes(data)
            return wire
        client, _ = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertIsInstance(raised.exception.__cause__, ChecksumError)

    def test_transport_failure_after_processing_write_is_unknown(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                raise OSError("simulated disconnect")
            return wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown):
            client.set_parameter(0x1234, 66)
        self.assertEqual(transport.heater.parameter_write_count, 1)

    def test_unexpected_transport_exception_after_write_is_unknown(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                raise RuntimeError("unexpected transport failure")
            return wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown) as raised:
            client.set_parameter(0x1234, 66)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertTrue(client.session.broken)
        self.assertEqual(transport.heater.parameter_write_count, 1)

    def test_keyboard_interrupt_preserves_cancellation_and_breaks_session(self):
        def fault(request, wire):
            if request.command == Command.SET_PARAMETER:
                raise KeyboardInterrupt()
            return wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(KeyboardInterrupt):
            client.set_parameter(0x1234, 66)
        self.assertTrue(client.session.broken)
        self.assertEqual(transport.heater.parameter_write_count, 1)
        with self.assertRaises(SessionBroken):
            client.get_status()

    def test_write_reply_is_rejected_during_status_read(self):
        def fault(request, wire):
            return encode_frame(Frame(0x39, bytes.fromhex("12 34 02 A3")))
        client, _ = self.make_client(wire_filter=fault)
        with self.assertRaises(UnexpectedReply):
            client.get_status()
        self.assertTrue(client.session.broken)

    def test_unsolicited_bytes_before_request_are_rejected_without_send(self):
        client, transport = self.make_client()
        transport.inject(encode_frame(Frame(0x39, bytes.fromhex("12 34 02 A3"))))
        with self.assertRaises(UnexpectedData):
            client.get_status()
        self.assertEqual(transport.requests, [])

    def test_extra_or_partial_response_prevents_success(self):
        for extra in [encode_frame(Frame(0x39, bytes.fromhex("12 34 02 A3"))), b"\x02"]:
            with self.subTest(extra=extra):
                client, _ = self.make_client(wire_filter=lambda request, wire: wire + extra)
                with self.assertRaises(UnexpectedData):
                    client.get_parameter(0x1234)
                self.assertTrue(client.session.broken)

    def test_timeout_invalidates_session_and_late_reply_cannot_be_next_result(self):
        client, transport = self.make_client(wire_filter=lambda request, wire: b"")
        with self.assertRaises(RequestTimeout):
            client.get_status()
        transport.inject(encode_frame(Frame(0x51, b"\x00\x00Auto;Bereit")))
        with self.assertRaises(SessionBroken):
            client.get_status()
        self.assertEqual(len(transport.requests), 1)

    def test_list_limit_does_not_return_partial_discovery(self):
        client, _ = self.make_client()
        with self.assertRaises(ListLimitExceeded):
            client.get_menu(max_items=2)
        self.assertTrue(client.session.broken)

    def test_list_capacity_can_equal_exact_count(self):
        client, _ = self.make_client()
        self.assertEqual(len(client.get_value_specs(max_items=2)), 2)

    def test_time_update_preserves_other_fresh_intervals_and_verifies(self):
        heater = demo_heater()
        # Represents a change made outside an old cache, before the transaction starts.
        old = heater.time_programs[0x38]
        interval = TimeRange(time(15), time(16))
        heater.time_programs[0x38] = replace(old, ranges=old.ranges[:2] + (interval,) + old.ranges[3:])
        client, transport = self.make_client(heater=heater, read_chunk_size=1)
        result = client.set_time_range(0x38, 1, TimeRange(time(12), time(13)))
        self.assertEqual(result.status, WriteStatus.CONFIRMED)
        self.assertEqual(result.current.ranges[2], interval)
        self.assertEqual(result.current.ranges[0], old.ranges[0])
        self.assertEqual([r.command for r in transport.requests], [0x42, 0x43, 0x50, 0x42, 0x43])
        self.assertEqual(transport.heater.time_write_count, 1)

    def test_clear_and_unchanged_time_interval(self):
        client, transport = self.make_client()
        self.assertEqual(client.set_time_range(0x38, 1, TimeRange()).status, WriteStatus.UNCHANGED)
        self.assertEqual(transport.heater.time_write_count, 0)
        self.assertEqual(client.set_time_range(0x38, 0, TimeRange()).status, WriteStatus.CONFIRMED)
        self.assertEqual(transport.heater.time_programs[0x38].values_bytes(), b"\xff" * 8)

    def test_invalid_time_index_does_not_read_or_write(self):
        client, transport = self.make_client()
        for index in [-1, 4, True]:
            with self.assertRaises(ValidationError):
                client.set_time_range(0x38, index, TimeRange())
        self.assertEqual(transport.requests, [])

    def test_failed_time_ack_is_unknown_and_not_success(self):
        def fault(request, wire):
            return b"" if request.command == Command.SET_TIMES else wire
        client, transport = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown):
            client.set_time_range(0x38, 0, TimeRange())
        self.assertEqual(transport.heater.time_write_count, 1)

    def test_time_reply_wrong_address_is_unknown(self):
        def fault(request, wire):
            if request.command == Command.SET_TIMES:
                return change_reply(wire, lambda f: Frame(f.command, b"\x00\x00\x39" + f.payload[3:]))
            return wire
        client, _ = self.make_client(wire_filter=fault)
        with self.assertRaises(WriteOutcomeUnknown):
            client.set_time_range(0x38, 0, TimeRange())

    def test_time_readback_mismatch_fails(self):
        heater = demo_heater()
        original = heater.time_programs[0x38]
        def fault(request, wire):
            if request.command == Command.TIMES_FIRST and heater.time_write_count:
                return encode_frame(Frame(request.command, original.list_payload()))
            return wire
        client, _ = self.make_client(heater=heater, wire_filter=fault)
        with self.assertRaises(WriteVerificationError):
            client.set_time_range(0x38, 0, TimeRange())

    def test_time_list_without_terminal_address_fails(self):
        def fault(request, wire):
            if request.command == Command.TIMES_NEXT:
                return change_reply(wire, lambda f: Frame(f.command, f.payload[:2] + b"\x38" + f.payload[3:]))
            return wire
        client, _ = self.make_client(wire_filter=fault)
        with self.assertRaises(MalformedPayload):
            client.get_time_ranges()

    def test_explicit_reply_profile_can_override_unverified_echo_convention(self):
        def fault(request, wire):
            return change_reply(wire, lambda f: Frame(0xA5, f.payload))
        transport = MemoryTransport(wire_filter=fault)
        client = HeatingClient(ProtocolSession(transport), {0x55: (0xA5,)})
        self.assertEqual(client.get_parameter(0x1234).value, 65)
        with self.assertRaises(ValidationError):
            HeatingClient(client.session, {0x39: (0x39,)})


class SessionTests(unittest.TestCase):
    def test_transaction_deadline_is_not_restarted_for_each_byte(self):
        class Clock:
            now = 0.0
            def __call__(self):
                return self.now
        clock = Clock()
        class SlowBytes(MemoryTransport):
            def read(self, max_bytes, timeout):
                result = super().read(max_bytes, timeout)
                if timeout > 0:
                    clock.now += 0.4
                return result
        transport = SlowBytes(read_chunk_size=1)
        session = ProtocolSession(transport, clock=clock)
        with self.assertRaises(RequestTimeout):
            HeatingClient(session).get_status(timeout=1)
        self.assertLess(clock.now, 2)
        self.assertTrue(session.broken)

    def test_validation_error_cannot_leave_an_unconsumed_request_usable(self):
        session = ProtocolSession(MemoryTransport())
        with self.assertRaises(UnexpectedData):
            with session.transaction() as tx:
                tx.send(Frame(Command.STATE))
                raise ValidationError("synthetic interrupted operation")
        self.assertTrue(session.broken)

    def test_deadline_also_applies_when_finishing_a_transaction(self):
        class Clock:
            now = 0.0
            def __call__(self):
                return self.now
        clock = Clock()
        session = ProtocolSession(MemoryTransport(), clock=clock)
        with self.assertRaises(RequestTimeout):
            with session.transaction(1):
                clock.now = 2
        self.assertTrue(session.broken)

    def test_invalid_timeout_does_not_send(self):
        transport = MemoryTransport()
        client = HeatingClient(ProtocolSession(transport))
        for timeout in [0, -1, True, float("nan"), float("inf")]:
            with self.assertRaises(ValidationError):
                client.get_status(timeout=timeout)
        self.assertEqual(transport.requests, [])

    def test_zero_or_invalid_partial_write_marks_session_broken(self):
        class BadWriter(MemoryTransport):
            def write(self, data, timeout):
                return 0
        session = ProtocolSession(BadWriter())
        with self.assertRaises(TransportError):
            HeatingClient(session).get_status()
        self.assertTrue(session.broken)

    def test_invalid_transport_read_type_is_a_fatal_contract_error(self):
        class BadReader(MemoryTransport):
            def read(self, max_bytes, timeout):
                return None
        session = ProtocolSession(BadReader())
        with self.assertRaises(TransportError):
            HeatingClient(session).get_status()
        self.assertTrue(session.broken)

    def test_lock_timeout_does_not_break_another_active_transaction(self):
        entered = threading.Event()
        release = threading.Event()
        failures = []
        class PausedTransport(MemoryTransport):
            def write(self, data, timeout):
                count = super().write(data, timeout)
                if self.requests and self.requests[-1].command == Command.PARAMETER and len(self.requests) == 1:
                    entered.set()
                    if not release.wait(1):
                        raise OSError("test coordination timeout")
                return count
        transport = PausedTransport()
        session = ProtocolSession(transport)
        client = HeatingClient(session)
        def writer():
            try:
                client.set_parameter(0x1234, 66)
            except Exception as exc:
                failures.append(exc)
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(RequestTimeout):
                client.get_status(timeout=0.01)
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertFalse(session.broken)
        self.assertEqual([r.command for r in transport.requests], [0x55, 0x39, 0x55])
