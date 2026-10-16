"""Typed payloads for the layouts read by p4d 0.10.2.

Unknown metadata is preserved. Parameter limits deliberately follow p4d's
unscaled min/max/default interpretation, pending hardware validation.
"""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation, localcontext
from enum import IntEnum
import re
import struct
from typing import Optional, Tuple

from .codec import uint
from .errors import MalformedPayload, ValidationError


class Command(IntEnum):
    CHECK = 0x22
    VALUE = 0x30
    VALUES_FIRST = 0x31
    VALUES_NEXT = 0x32
    MENU_FIRST = 0x37
    MENU_NEXT = 0x38
    SET_PARAMETER = 0x39
    VERSION = 0x41
    TIMES_FIRST = 0x42
    TIMES_NEXT = 0x43
    DIGITAL_OUT = 0x44
    ANALOG_OUT = 0x45
    DIGITAL_IN = 0x46
    ERRORS_FIRST = 0x47
    ERRORS_NEXT = 0x48
    SET_TIMES = 0x50
    STATE = 0x51
    PARAMETER = 0x55


class ParameterType(IntEnum):
    NUMBER = 0x07
    BOOLEAN = 0x08
    TIME = 0x0A
    NUMBER_SET = 0x32
    NUMBER_SET_1 = 0x39
    NUMBER_SET_2 = 0x40


def address_bytes(address: int) -> bytes:
    uint(address, 16, "address")
    if address == 0xFFFF:
        raise ValidationError("FFFF is not a usable request address")
    return address.to_bytes(2, "big")


def exact(payload, size, name):
    if len(payload) != size:
        raise MalformedPayload(f"{name} payload must contain {size} bytes")


def text(raw: bytes) -> str:
    return bytes(b for b in raw if b not in (0, 1, 2, 3)).decode("latin-1")


def unit(raw: bytes) -> str:
    result = text(raw).strip()
    return "°C" if result == "°" else result


def parse_word(payload: bytes) -> int:
    exact(payload, 2, "word")
    return int.from_bytes(payload, "big")


def measurement(word: int, factor: int, data_type: int) -> Decimal:
    uint(word, 16, "raw measurement")
    uint(factor, 16, "measurement factor")
    uint(data_type, 16, "measurement type")
    if not factor:
        raise ValidationError("measurement factor must not be zero")
    value = word if data_type == 1 or word < 32768 else word - 65536
    return Decimal(value) / Decimal(factor)


@dataclass(frozen=True)
class Parameter:
    address: int
    raw_value: int
    minimum: int
    maximum: int
    default: int
    factor: int
    digits: int
    unit_raw: bytes
    unknown1: int = 0
    unknown2: int = 0
    unknown_word: int = 0
    unknown3: int = 0

    def __post_init__(self):
        uint(self.address, 16, "parameter address")
        for name in ("raw_value", "minimum", "maximum", "default", "unknown_word"):
            value = getattr(self, name)
            if type(value) is not int or not -32768 <= value <= 32767:
                raise ValidationError(f"{name} must be signed 16-bit")
        for name in ("factor", "digits", "unknown1", "unknown2", "unknown3"):
            uint(getattr(self, name), 8, name)
        if not isinstance(self.unit_raw, bytes) or len(self.unit_raw) != 1:
            raise ValidationError("parameter unit must be one raw byte")

    @property
    def effective_factor(self):
        return self.factor or 1

    @property
    def value(self) -> Decimal:
        return Decimal(self.raw_value) / Decimal(self.effective_factor)

    @property
    def unit(self):
        return unit(self.unit_raw)

    def target_raw(self, value, parameter_type=ParameterType.NUMBER):
        try:
            kind = ParameterType(parameter_type)
        except (ValueError, TypeError):
            raise ValidationError("unsupported editable parameter type") from None
        if self.minimum > self.maximum:
            raise ValidationError("invalid parameter limits")
        if kind == ParameterType.BOOLEAN:
            if type(value) is not bool:
                raise ValidationError("boolean parameter requires true or false")
            numeric = Decimal(int(value))
            raw = numeric
        elif kind == ParameterType.TIME:
            t = parse_time(value)
            numeric = Decimal(t.hour * 60 + t.minute)
            raw = numeric
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
                raise ValidationError("numeric parameter requires a number")
            try:
                numeric = Decimal(str(value))
            except InvalidOperation:
                raise ValidationError("invalid decimal number") from None
            if not numeric.is_finite():
                raise ValidationError("number must be finite")
            if not self.minimum <= numeric <= self.maximum:
                raise ValidationError("parameter value is outside controller limits")
            with localcontext() as context:
                context.prec = max(40, len(numeric.as_tuple().digits) + self.digits + 10)
                if numeric != numeric.quantize(Decimal(1).scaleb(-self.digits)):
                    raise ValidationError("value exceeds parameter display precision")
                raw = numeric * self.effective_factor
                if raw != raw.to_integral_value():
                    raise ValidationError("value is not representable with controller factor")
        if not self.minimum <= numeric <= self.maximum:
            raise ValidationError("parameter value is outside controller limits")
        if not -32768 <= raw <= 32767:
            raise ValidationError("scaled value does not fit signed 16-bit")
        return int(raw)

    def to_payload(self):
        return struct.pack(
            ">BHcBBBhhhhhB", self.unknown1, self.address, self.unit_raw,
            self.digits, self.unknown2, self.factor, self.raw_value,
            self.minimum, self.maximum, self.default, self.unknown_word, self.unknown3,
        )


def parse_parameter(payload: bytes) -> Parameter:
    exact(payload, 18, "parameter")
    ub1, addr, raw_unit, digits, ub2, factor, value, low, high, default, uw, ub3 = struct.unpack(
        ">BHcBBBhhhhhB", payload
    )
    return Parameter(addr, value, low, high, default, factor, digits, raw_unit,
                     ub1, ub2, uw, ub3)


@dataclass(frozen=True)
class ParameterAck:
    address: int
    raw_value: int


def parse_parameter_ack(payload):
    exact(payload, 4, "parameter acknowledgement")
    return ParameterAck(*struct.unpack(">Hh", payload))


@dataclass(frozen=True)
class ValueSpec:
    address: int
    factor: int
    data_type: int
    unit_raw: bytes
    description_raw: bytes
    terminator: int = 0

    def __post_init__(self):
        for name in ("address", "factor", "data_type"):
            uint(getattr(self, name), 16, name)
        uint(self.terminator, 8, "value-spec terminator")
        if not isinstance(self.unit_raw, bytes) or len(self.unit_raw) != 2:
            raise ValidationError("value-spec unit must contain two raw bytes")
        if not isinstance(self.description_raw, bytes):
            raise ValidationError("value-spec description must contain raw bytes")

    @property
    def unit(self):
        result = unit(self.unit_raw)
        if not result:
            match = re.search(r"\[([^]]+)\]", self.description)
            return unit(match.group(1).encode("latin-1")) if match else ""
        return result

    @property
    def description(self):
        return text(self.description_raw)

    def to_payload(self):
        return b"\x01" + struct.pack(">HH2sH", self.factor, self.data_type,
                                      self.unit_raw, self.address) + self.description_raw + bytes([self.terminator])


def parse_value_spec(payload) -> Optional[ValueSpec]:
    if payload == b"\x00":
        return None
    if len(payload) < 10 or payload[0] == 0:
        raise MalformedPayload("invalid value-definition list entry")
    factor, kind, raw_unit, address = struct.unpack(">HH2sH", payload[1:9])
    return ValueSpec(address, factor, kind, raw_unit, payload[9:-1], payload[-1])


@dataclass(frozen=True)
class MenuItem:
    item_type: int
    parent: int
    child: int
    address: int
    description_raw: bytes
    unknown1: int = 0
    reserved: bytes = bytes(18)
    unknown2: int = 0
    terminator: int = 0

    def __post_init__(self):
        for name in ("item_type", "unknown1", "terminator"):
            uint(getattr(self, name), 8, name)
        for name in ("parent", "child", "address", "unknown2"):
            uint(getattr(self, name), 16, name)
        if not isinstance(self.description_raw, bytes):
            raise ValidationError("menu description must contain raw bytes")
        if not isinstance(self.reserved, bytes) or len(self.reserved) != 18:
            raise ValidationError("menu reserved metadata must contain 18 raw bytes")

    @property
    def description(self):
        return text(self.description_raw)

    def to_payload(self):
        if len(self.reserved) != 18:
            raise ValidationError("menu reserved metadata must contain 18 bytes")
        return (b"\x01" + struct.pack(">BBHH", self.item_type, self.unknown1,
                                      self.parent, self.child) + self.reserved
                + struct.pack(">HH", self.address, self.unknown2)
                + self.description_raw + bytes([self.terminator]))


def parse_menu_item(payload) -> Optional[MenuItem]:
    if payload == b"\x00":
        return None
    if len(payload) < 30 or payload[0] == 0:
        raise MalformedPayload("invalid menu list entry")
    kind, unknown1, parent, child = struct.unpack(">BBHH", payload[1:7])
    address, unknown2 = struct.unpack(">HH", payload[25:29])
    return MenuItem(kind, parent, child, address, payload[29:-1], unknown1,
                    payload[7:25], unknown2, payload[-1])


@dataclass(frozen=True)
class Status:
    mode: int
    state: int
    mode_text: str
    state_text: str


def parse_status(payload) -> Status:
    if len(payload) < 3:
        raise MalformedPayload("status payload is too short")
    left, separator, right = text(payload[2:]).partition(";")
    if not separator:
        raise MalformedPayload("status text lacks mode/state separator")
    return Status(payload[0], payload[1], left, right)


def parse_datetime(raw: bytes, extended=False) -> datetime:
    exact(raw, 7 if extended else 6, "date/time")
    sec, minute, hour, day, month = raw[:5]
    year = raw[6] if extended else raw[5]
    try:
        return datetime(2000 + year, month, day, hour, minute, sec)
    except ValueError as exc:
        raise MalformedPayload("invalid controller date/time") from exc


@dataclass(frozen=True)
class FirmwareInfo:
    version: Tuple[int, int, int, int]
    local_time: datetime
    weekday: int
    extra: bytes

    @property
    def version_text(self):
        return ".".join(f"{part:02x}" for part in self.version)


def parse_firmware(payload) -> FirmwareInfo:
    if len(payload) < 11:
        raise MalformedPayload("version payload is too short")
    return FirmwareInfo(tuple(payload[:4]), parse_datetime(payload[4:11], True),
                        payload[9], payload[11:])


@dataclass(frozen=True)
class IOState:
    mode: int
    state: int


def parse_io(payload) -> IOState:
    exact(payload, 2, "I/O")
    return IOState(*payload)


@dataclass(frozen=True)
class ErrorEntry:
    number: int
    info: int
    state: int
    local_time: datetime
    description_raw: bytes

    @property
    def description(self):
        return text(self.description_raw)


def parse_error(payload) -> Optional[ErrorEntry]:
    if payload == b"\x00":
        return None
    if len(payload) < 11 or payload[0] == 0:
        raise MalformedPayload("invalid error list entry")
    return ErrorEntry(int.from_bytes(payload[1:3], "big"), payload[3], payload[4],
                      parse_datetime(payload[5:11]), payload[11:])


def parse_time(value) -> time:
    if isinstance(value, time):
        if value.second or value.microsecond or value.tzinfo is not None:
            raise ValidationError("time must be local HH:MM without seconds")
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise ValidationError("time must be HH:MM")
    try:
        return time(int(value[:2]), int(value[3:]))
    except ValueError:
        raise ValidationError("invalid time") from None


@dataclass(frozen=True)
class TimeRange:
    start: Optional[time] = None
    end: Optional[time] = None

    def __post_init__(self):
        if (self.start is None) != (self.end is None):
            raise ValidationError("both time endpoints must be set or unset")
        if self.start is not None:
            for value in (self.start, self.end):
                t = parse_time(value)
                if t.minute % 10:
                    raise ValidationError("time programs require ten-minute steps")
                if not isinstance(value, time):
                    raise ValidationError("TimeRange endpoints must be datetime.time objects")

    def to_bytes(self):
        if self.start is None:
            return b"\xff\xff"
        return bytes([self.start.hour * 10 + self.start.minute // 10,
                      self.end.hour * 10 + self.end.minute // 10])


def parse_range(raw: bytes) -> TimeRange:
    exact(raw, 2, "time range")
    if raw == b"\xff\xff":
        return TimeRange()
    if any(value > 235 or value % 10 > 5 for value in raw):
        raise MalformedPayload("invalid time-program endpoint or mixed unset pair")
    return TimeRange(*(time(value // 10, (value % 10) * 10) for value in raw))


@dataclass(frozen=True)
class TimeRanges:
    address: int
    ranges: Tuple[TimeRange, TimeRange, TimeRange, TimeRange]
    unknown_prefix: int = 0x0100

    def __post_init__(self):
        uint(self.address, 8, "time-program address")
        if self.address == 255:
            raise ValidationError("FF is not a usable time-program address")
        uint(self.unknown_prefix, 16, "time-program prefix")
        if not isinstance(self.ranges, tuple) or len(self.ranges) != 4 or not all(
            isinstance(r, TimeRange) for r in self.ranges
        ):
            raise ValidationError("time program requires exactly four immutable ranges")

    def values_bytes(self):
        return b"".join(r.to_bytes() for r in self.ranges)

    def write_payload(self):
        return self.address.to_bytes(2, "big") + self.values_bytes()

    def list_payload(self):
        return self.unknown_prefix.to_bytes(2, "big") + bytes([self.address]) + self.values_bytes()


def parse_time_ranges(payload, write_reply=False) -> TimeRanges:
    exact(payload, 11, "time program")
    if write_reply:
        address = int.from_bytes(payload[1:3], "big")
        if address > 254:
            raise MalformedPayload("time-program reply address is out of range")
        prefix = payload[0]
    else:
        prefix = int.from_bytes(payload[:2], "big")
        address = payload[2]
        if address == 255:
            raise MalformedPayload("invalid time-program address FF")
    return TimeRanges(address, tuple(parse_range(payload[i:i+2]) for i in range(3, 11, 2)), prefix)
