"""Deterministic, in-memory S3200 substitute using entirely fictional data.

Reply codes echo requests as a simulator convention. Two SET_PARAMETER replies
are emitted; their real-world meaning/timing remains unvalidated. No file,
network, database or TTY is opened by this module.
"""
from dataclasses import replace
from datetime import datetime, time
import struct

from .codec import Frame, StreamDecoder, encode_frame
from .errors import MalformedPayload, ValidationError
from .messages import (
    Command, ErrorEntry, MenuItem, Parameter, Status, TimeRange, TimeRanges,
    ValueSpec, exact, parse_parameter_ack, parse_range, parse_word,
)


class HeaterSimulator:
    def __init__(self, parameters=None, measurements=None, value_specs=(), menu=(),
                 time_programs=(), errors=(), status=None, io_states=None):
        self.parameters = dict(parameters or {})
        self.measurements = dict(measurements or {})
        self.value_specs = tuple(value_specs)
        self.menu = tuple(menu)
        self.errors = tuple(errors)
        self.time_programs = {item.address: item for item in time_programs}
        if 0xDF not in self.time_programs:
            self.time_programs[0xDF] = TimeRanges(0xDF, (TimeRange(),) * 4)
        self.status = status or Status(0, 0, "Automatik", "Bereit")
        self.io_states = dict(io_states or {})
        self.firmware = (0, 0, 0, 1)
        self.local_time = datetime(2024, 1, 15, 12, 0, 0)
        self._cursors = {}
        self.parameter_write_count = 0
        self.time_write_count = 0

    def _entry(self, key, first, values, serialize):
        index = 0 if first else self._cursors.get(key, 0)
        if index >= len(values):
            return b"\x00"
        self._cursors[key] = index + 1
        return serialize(values[index])

    def handle(self, request: Frame):
        command = request.command
        payload = request.payload
        if command == Command.CHECK:
            return (Frame(command, payload),)
        if command == Command.VALUE:
            address = parse_word(payload)
            if address not in self.measurements:
                raise MalformedPayload("simulator has no measurement at that address")
            result = (self.measurements[address] & 0xFFFF).to_bytes(2, "big")
        elif command == Command.PARAMETER:
            address = parse_word(payload)
            if address not in self.parameters:
                raise MalformedPayload("simulator has no parameter at that address")
            result = self.parameters[address].to_payload()
        elif command == Command.SET_PARAMETER:
            ack = parse_parameter_ack(payload)
            if ack.address not in self.parameters:
                raise MalformedPayload("simulator has no writable parameter at that address")
            self.parameters[ack.address] = replace(self.parameters[ack.address], raw_value=ack.raw_value)
            self.parameter_write_count += 1
            # The simulator models the observed layout, not the unexplained ack semantics.
            return (Frame(command, payload), Frame(command, payload))
        elif command in (Command.VALUES_FIRST, Command.VALUES_NEXT):
            exact(payload, 0, "value-list request")
            result = self._entry("values", command == Command.VALUES_FIRST,
                                 self.value_specs, lambda item: item.to_payload())
        elif command in (Command.MENU_FIRST, Command.MENU_NEXT):
            exact(payload, 0, "menu-list request")
            result = self._entry("menu", command == Command.MENU_FIRST,
                                 self.menu, lambda item: item.to_payload())
        elif command in (Command.TIMES_FIRST, Command.TIMES_NEXT):
            exact(payload, 0, "time-list request")
            values = tuple(self.time_programs[key] for key in sorted(self.time_programs) if key <= 0xDF)
            result = self._entry("times", command == Command.TIMES_FIRST, values,
                                 lambda item: item.list_payload())
        elif command == Command.SET_TIMES:
            exact(payload, 10, "time-program write")
            address = int.from_bytes(payload[:2], "big")
            if address not in self.time_programs:
                raise MalformedPayload("simulator has no time program at that address")
            ranges = tuple(parse_range(payload[i:i+2]) for i in range(2, 10, 2))
            self.time_programs[address] = replace(self.time_programs[address], ranges=ranges)
            self.time_write_count += 1
            result = b"\x00" + payload
        elif command == Command.STATE:
            exact(payload, 0, "state request")
            result = bytes([self.status.mode, self.status.state])
            result += (self.status.mode_text + ";" + self.status.state_text).encode("latin-1")
        elif command == Command.VERSION:
            exact(payload, 0, "version request")
            t = self.local_time
            result = bytes(self.firmware) + bytes([
                t.second, t.minute, t.hour, t.day, t.month, t.isoweekday() % 7, t.year - 2000,
            ])
        elif command in (Command.DIGITAL_IN, Command.DIGITAL_OUT, Command.ANALOG_OUT):
            address = parse_word(payload)
            mode, state = self.io_states.get((command, address), (0xFF, 0))
            result = bytes([mode, state])
        elif command in (Command.ERRORS_FIRST, Command.ERRORS_NEXT):
            exact(payload, 0, "error-list request")
            def error_payload(item):
                t = item.local_time
                return (b"\x01" + struct.pack(">HBB", item.number, item.info, item.state)
                        + bytes([t.second, t.minute, t.hour, t.day, t.month, t.year - 2000])
                        + item.description_raw)
            result = self._entry("errors", command == Command.ERRORS_FIRST, self.errors, error_payload)
        else:
            raise MalformedPayload(f"simulator does not implement command 0x{command:02X}")
        return (Frame(command, result),)


class MemoryTransport:
    """Virtual-time byte transport; empty reads act as deterministic timeouts.

    read_chunk_size/max_write exercise fragmented RX/TX. wire_filter can inject
    faults after the virtual controller has processed a request. requests is a
    trace of complete sent frames, including writes that received no reply.
    """

    def __init__(self, heater=None, read_chunk_size=512, max_write=512, wire_filter=None):
        if type(read_chunk_size) is not int or type(max_write) is not int or min(read_chunk_size, max_write) < 1:
            raise ValidationError("transport chunk sizes must be positive integers")
        self.heater = heater or demo_heater()
        self.read_chunk_size = read_chunk_size
        self.max_write = max_write
        self.wire_filter = wire_filter
        self.requests = []
        self._decoder = StreamDecoder()
        self._incoming = bytearray()

    def inject(self, data: bytes):
        self._incoming.extend(data)

    def read(self, max_bytes, timeout):
        count = min(max_bytes, self.read_chunk_size, len(self._incoming))
        result = bytes(self._incoming[:count])
        del self._incoming[:count]
        return result

    def write(self, data, timeout):
        accepted = bytes(data[:self.max_write])
        for request in self._decoder.feed(accepted):
            self.requests.append(request)
            replies = self.heater.handle(request)
            wire = b"".join(encode_frame(reply) for reply in replies)
            if self.wire_filter:
                wire = self.wire_filter(request, wire)
            self._incoming.extend(wire)
        return len(accepted)


def demo_heater():
    """Fictional fixtures; no values originate from the user's installation."""
    parameters = {
        0x1234: Parameter(0x1234, 650, 20, 90, 60, 10, 1, b"\xb0"),
        0x002B: Parameter(0x002B, 1, 0, 1, 0, 1, 0, b" "),
        0x0200: Parameter(0x0200, 360, 0, 1439, 360, 1, 0, b" "),
    }
    return HeaterSimulator(
        parameters=parameters,
        measurements={0x002B: -12, 0x0100: 60000},
        value_specs=(ValueSpec(0x002B, 10, 2, b"\xb0 ", b"Fiktive Temperatur"),
                     ValueSpec(0x0100, 1, 1, b"  ", b"Fiktiver Zaehler")),
        menu=(MenuItem(1, 1, 10, 0, b"Demo-Heizung"),
              MenuItem(7, 10, 0, 0x1234, b"Fiktiver Sollwert"),
              MenuItem(8, 10, 0, 0x002B, b"Fiktive Freigabe"),
              MenuItem(10, 10, 0, 0x0200, b"Fiktive Uhrzeit")),
        time_programs=(TimeRanges(0x38, (TimeRange(time(6), time(8)), TimeRange(), TimeRange(), TimeRange())),),
        errors=(ErrorEntry(1, 0, 4, datetime(2024, 1, 15, 10), b"Fiktive Testmeldung"),),
    )
