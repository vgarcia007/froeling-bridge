"""High-level offline client with complete serialized transactions.

Default reply codes echo requests ONLY AS A SIMULATION PROFILE. p4d does not
validate most reply codes; real hardware mapping remains unconfirmed. The
client accepts an explicit command-to-reply-sequence mapping for future logs.
"""
from dataclasses import dataclass, replace
from enum import Enum
from typing import Tuple

from .codec import Frame, uint
from .errors import (
    ListLimitExceeded, MalformedPayload, ProtocolError, UnexpectedReply,
    ValidationError, WriteOutcomeUnknown, WriteVerificationError,
)
from .messages import (
    Command, Parameter, ParameterAck, ParameterType, TimeRange, TimeRanges,
    address_bytes, measurement, parse_error, parse_firmware, parse_io,
    parse_menu_item, parse_parameter, parse_parameter_ack, parse_status,
    parse_time_ranges, parse_value_spec, parse_word,
)
from .session import ProtocolSession


class WriteStatus(str, Enum):
    UNCHANGED = "unchanged"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class ParameterWriteResult:
    status: WriteStatus
    previous: Parameter
    current: Parameter
    requested_raw: int
    acknowledgements: Tuple[ParameterAck, ...] = ()


@dataclass(frozen=True)
class TimeWriteResult:
    status: WriteStatus
    previous: TimeRanges
    current: TimeRanges


class HeatingClient:
    def __init__(self, session: ProtocolSession, reply_commands=None):
        self.session = session
        self.reply_commands = {}
        for command, codes in (reply_commands or {}).items():
            uint(command, 8, "request command")
            codes = tuple(codes)
            count = 2 if command == Command.SET_PARAMETER else 1
            if len(codes) != count:
                raise ValidationError(f"command 0x{command:02X} needs {count} reply code(s)")
            for code in codes:
                uint(code, 8, "reply command")
            self.reply_commands[command] = codes

    def _codes(self, command):
        return self.reply_commands.get(command, (command, command) if command == Command.SET_PARAMETER else (command,))

    def _request(self, tx, command, payload=b"", timeout=None):
        return tx.exchange(Frame(command, payload), self._codes(command), timeout=timeout)[0]

    def get_status(self, timeout=2.0):
        with self.session.transaction(timeout) as tx:
            return parse_status(self._request(tx, Command.STATE).payload)

    def get_firmware(self, timeout=2.0):
        with self.session.transaction(timeout) as tx:
            return parse_firmware(self._request(tx, Command.VERSION).payload)

    def get_measurement(self, address, factor, data_type, timeout=2.0):
        payload = address_bytes(address)
        # Reject invalid metadata before asking for a measurement.
        measurement(0, factor, data_type)
        with self.session.transaction(timeout) as tx:
            return measurement(parse_word(self._request(tx, Command.VALUE, payload).payload), factor, data_type)

    def get_io(self, address, command=Command.DIGITAL_IN, timeout=2.0):
        if command not in (Command.DIGITAL_IN, Command.DIGITAL_OUT, Command.ANALOG_OUT):
            raise ValidationError("command is not an I/O read")
        payload = address_bytes(address)
        with self.session.transaction(timeout) as tx:
            return parse_io(self._request(tx, command, payload).payload)

    def _parameter(self, tx, address):
        result = parse_parameter(self._request(tx, Command.PARAMETER, address_bytes(address)).payload)
        if result.address != address:
            raise UnexpectedReply("parameter reply contains a different address")
        return result

    def get_parameter(self, address, timeout=2.0):
        address_bytes(address)
        with self.session.transaction(timeout) as tx:
            return self._parameter(tx, address)

    def set_parameter(self, address, value, parameter_type=ParameterType.NUMBER, timeout=2.0):
        address_bytes(address)
        attempted = False
        stage = "metadata"
        try:
            with self.session.transaction(timeout) as tx:
                before = self._parameter(tx, address)
                target = before.target_raw(value, parameter_type)
                if target == before.raw_value:
                    return ParameterWriteResult(WriteStatus.UNCHANGED, before, before, target)
                payload = address_bytes(address) + target.to_bytes(2, "big", signed=True)
                stage = "send/acknowledgements"
                try:
                    replies = tx.exchange(Frame(Command.SET_PARAMETER, payload), self._codes(Command.SET_PARAMETER))
                finally:
                    attempted = tx.send_attempted
                acks = tuple(parse_parameter_ack(reply.payload) for reply in replies)
                if any(ack.address != address for ack in acks):
                    raise UnexpectedReply("write acknowledgement contains a different address")
                # Ack values are preserved, not assigned an unproven semantic meaning.
                stage = "readback"
                after = self._parameter(tx, address)
                try:
                    readback_target = after.target_raw(value, parameter_type)
                except ValidationError:
                    raise WriteVerificationError("parameter write", address, after) from None
                if after.raw_value != target or readback_target != target:
                    raise WriteVerificationError("parameter write", address, after)
                stage = "transaction completion"
                return ParameterWriteResult(WriteStatus.CONFIRMED, before, after, target, acks)
        except WriteVerificationError:
            raise
        except Exception as exc:
            if attempted:
                raise WriteOutcomeUnknown("parameter write", address, stage) from exc
            raise

    def _list(self, tx, first, next_command, parser, max_items, min_payload=0):
        if type(max_items) is not int or max_items <= 0:
            raise ValidationError("max_items must be positive")
        result = []
        command = first
        entries = 0
        while True:
            # p4d reads these First/Next lists without checking the header command.
            # Accept the same-list First response on Next, without accepting unrelated replies.
            try:
                if command == next_command and command not in self.reply_commands:
                    reply = tx.exchange(Frame(command), (frozenset((first, next_command)),), timeout=2.0)[0]
                else:
                    reply = self._request(tx, command, timeout=2.0)
            except ProtocolError as exc:
                raise type(exc)(
                    f"list 0x{first:02X}, request 0x{command:02X}, entry {entries + 1}: {exc}"
                ) from exc
            # p4d skips short, nonterminal entries (wrnEmpty/wrnSkip).
            # Count skipped entries too, so an all-empty list remains bounded.
            if reply.payload and reply.payload[0] and len(reply.payload) < min_payload:
                if entries == max_items:
                    raise ListLimitExceeded("controller list did not terminate within item limit")
                entries += 1
                command = next_command
                continue
            item = parser(reply.payload)
            if item is None:
                return tuple(result)
            if entries == max_items:
                raise ListLimitExceeded("controller list did not terminate within item limit")
            result.append(item)
            entries += 1
            command = next_command

    def get_value_specs(self, timeout=2.0, max_items=4096):
        with self.session.transaction(timeout) as tx:
            self._request(tx, Command.CHECK, b"Tescht ;-)", timeout=2.0)
            return self._list(tx, Command.VALUES_FIRST, Command.VALUES_NEXT, parse_value_spec, max_items, min_payload=11)

    def get_menu(self, timeout=2.0, max_items=4096):
        with self.session.transaction(timeout) as tx:
            self._request(tx, Command.CHECK, b"Tescht ;-)", timeout=2.0)
            return self._list(tx, Command.MENU_FIRST, Command.MENU_NEXT, parse_menu_item, max_items, min_payload=30)

    def get_errors(self, timeout=2.0, max_items=4096):
        with self.session.transaction(timeout) as tx:
            return self._list(tx, Command.ERRORS_FIRST, Command.ERRORS_NEXT, parse_error, max_items)

    def _times(self, tx):
        # p4d stores each entry by address, replacing an earlier entry for the
        # same address. Stop at DF, with a deadline/reply cap for a stuck list.
        result = {}
        command = Command.TIMES_FIRST
        for _ in range(255):
            item = parse_time_ranges(self._request(tx, command).payload)
            result[item.address] = item
            if item.address == 0xDF:
                return tuple(result.values())
            command = Command.TIMES_NEXT
        raise ListLimitExceeded("time-program list lacks final address DF")

    def get_time_ranges(self, timeout=2.0):
        with self.session.transaction(timeout) as tx:
            # Same read-only check used by p4d before updateTimeRangeData.
            self._request(tx, Command.CHECK, b"Tescht ;-)")
            return self._times(tx)

    def set_time_range(self, address, index, interval: TimeRange, timeout=2.0):
        uint(address, 8, "time-program address")
        if address == 255 or type(index) is not int or not 0 <= index < 4:
            raise ValidationError("time-program address/index is invalid (index must be 0..3)")
        if not isinstance(interval, TimeRange):
            raise ValidationError("interval must be a TimeRange")
        attempted = False
        stage = "metadata"
        try:
            with self.session.transaction(timeout) as tx:
                before = next((item for item in self._times(tx) if item.address == address), None)
                if before is None:
                    raise ValidationError("time-program address was not discovered")
                values = list(before.ranges)
                values[index] = interval
                target = replace(before, ranges=tuple(values))
                if target.values_bytes() == before.values_bytes():
                    return TimeWriteResult(WriteStatus.UNCHANGED, before, before)
                stage = "send/acknowledgement"
                try:
                    raw_reply = self._request(tx, Command.SET_TIMES, target.write_payload())
                finally:
                    attempted = tx.send_attempted
                reply = parse_time_ranges(raw_reply.payload, True)
                if reply.address != address:
                    raise UnexpectedReply("time-program acknowledgement address differs")
                stage = "readback"
                after = next((item for item in self._times(tx) if item.address == address), None)
                if after is None or after.values_bytes() != target.values_bytes():
                    raise WriteVerificationError("time-program write", address, after)
                stage = "transaction completion"
                return TimeWriteResult(WriteStatus.CONFIRMED, before, after)
        except WriteVerificationError:
            raise
        except Exception as exc:
            if attempted:
                raise WriteOutcomeUnknown("time-program write", address, stage) from exc
            raise


class ReadOnlyHeatingClient(HeatingClient):
    """Defence in depth: reject writes even when bypassing the HTTP API."""
    def set_parameter(self, *args, **kwargs):
        from .errors import ReadOnlyViolation
        raise ReadOnlyViolation("heating writes are disabled in hardware-read mode")

    def set_time_range(self, *args, **kwargs):
        from .errors import ReadOnlyViolation
        raise ReadOnlyViolation("heating writes are disabled in hardware-read mode")
