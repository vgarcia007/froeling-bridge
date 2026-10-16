import os
import pty
from pathlib import Path
import select
import tempfile
import termios
from threading import Thread
import time
import unittest

from froeling_bridge.client import ReadOnlyHeatingClient
from froeling_bridge.codec import Frame, StreamDecoder, encode_frame
from froeling_bridge.errors import (
    ValidationError,
    ReadOnlyViolation,
    TransportError,
    RequestTimeout,
)
from froeling_bridge.messages import Command
from froeling_bridge.serial_transport import (
    SerialTransport,
    ReadOnlyTransport,
    TraceTransport,
    READ_COMMANDS,
)
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import demo_heater, MemoryTransport


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.original = termios.tcgetattr(self.slave)
        self.transport = SerialTransport(self.path)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.transport.close()
        for name in ("master", "slave"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)

    def test_configuration_nonblocking_read_and_restore(self):
        settings = termios.tcgetattr(self.slave)
        self.assertEqual(settings[4:6], [termios.B57600, termios.B57600])
        self.assertEqual(settings[2] & termios.CSIZE, termios.CS8)
        self.assertFalse(
            settings[2] & (termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
        )
        start = time.monotonic()
        self.assertEqual(self.transport.read(32, 0), b"")
        self.assertLess(time.monotonic() - start, 0.1)
        self.transport.close()
        self.assertEqual(termios.tcgetattr(self.slave), self.original)
        self.transport.close()

    def test_existing_bytes_not_flushed_on_open(self):
        self.transport.close()
        # Keep raw input while writing a framed controller response.
        settings = termios.tcgetattr(self.slave)
        settings[3] = 0
        termios.tcsetattr(self.slave, termios.TCSANOW, settings)
        os.write(self.master, b"pending")
        self.transport = SerialTransport(self.path)
        self.assertEqual(self.transport.read(32, 0.2), b"pending")

    def test_fragmented_real_pty_request_response(self):
        heater = demo_heater()

        def respond():
            decoder = StreamDecoder()
            while True:
                data = os.read(self.master, 1)
                frames = decoder.feed(data)
                if frames:
                    wire = b"".join(
                        encode_frame(frame) for frame in heater.handle(frames[0])
                    )
                    for byte in wire:
                        os.write(self.master, bytes([byte]))
                    return

        thread = Thread(target=respond)
        thread.start()
        client = ReadOnlyHeatingClient(
            ProtocolSession(ReadOnlyTransport(self.transport))
        )
        self.assertEqual(client.get_status().mode_text, "Automatik")
        thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_timeout_disconnect_and_exclusive_reopen(self):
        started = time.monotonic()
        self.assertEqual(self.transport.read(1, 0.02), b"")
        self.assertLess(time.monotonic() - started, 0.2)
        # TIOCEXCL is bypassable by privileged processes. flock still protects
        # another bridge opener even on hosts running tests with CAP_SYS_ADMIN.
        with self.assertRaises(TransportError):
            SerialTransport(self.path)
        os.close(self.master)
        self.master = None
        with self.assertRaises(TransportError):
            self.transport.read(32, 0.1)
        self.transport.close()

    def test_non_tty_rejected(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(ValidationError):
                SerialTransport(tmp.name)


class ReadOnlyTests(unittest.TestCase):
    def test_every_non_read_command_blocked_without_transmission(self):
        for command in range(256):
            if command in READ_COMMANDS:
                continue
            memory = MemoryTransport()
            guard = ReadOnlyTransport(memory)
            with self.assertRaises(ValidationError):
                guard.write(encode_frame(Frame(command, b"")), 1)
            self.assertEqual(memory.requests, [])

    def test_concatenated_frames_and_mutating_payload_rejected_atomically(self):
        for wire in (
            encode_frame(Frame(Command.STATE))
            + encode_frame(Frame(Command.SET_PARAMETER, b"\x12\x34\x00\x01")),
            encode_frame(Frame(Command.DIGITAL_OUT, b"\x00\x01\x01")),
        ):
            memory = MemoryTransport()
            guard = ReadOnlyTransport(memory)
            with self.assertRaises(ValidationError):
                guard.write(wire, 1)
            self.assertEqual(memory.requests, [])

    def test_fragmented_outbound_frame_has_no_early_transmission(self):
        memory = MemoryTransport(max_write=1)
        guard = ReadOnlyTransport(memory)
        wire = encode_frame(Frame(Command.STATE))
        for byte in wire[:-1]:
            guard.write(bytes([byte]), 1)
        self.assertEqual(memory.requests, [])
        guard.write(wire[-1:], 1)
        self.assertEqual(len(memory.requests), 1)

    def test_client_write_methods_fail_before_metadata(self):
        memory = MemoryTransport()
        client = ReadOnlyHeatingClient(ProtocolSession(ReadOnlyTransport(memory)))
        with self.assertRaises(ReadOnlyViolation):
            client.set_parameter(4660, "67.5")
        with self.assertRaises(ReadOnlyViolation):
            client.set_time_range(56, 0, None)
        self.assertEqual(memory.requests, [])

    def test_trace_private_bounded_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace"

            class Transport(MemoryTransport):
                def close(self):
                    pass

            trace = TraceTransport(Transport(), path, limit=100)
            trace.write(encode_frame(Frame(Command.STATE)), 1)
            trace.read(512, 1)
            self.assertLessEqual(path.stat().st_size, 100)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            trace.close()
            with self.assertRaises(FileExistsError):
                TraceTransport(Transport(), path)
