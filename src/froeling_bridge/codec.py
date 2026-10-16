"""COM1 framing derived from p4d p4io.c and lib/common.c.

Length includes payload and checksum, but excludes the command/header.
The parser is strict: it never silently skips bytes or malformed frames.
"""
from dataclasses import dataclass

from .errors import (
    ChecksumError, InvalidEscape, InvalidLength, InvalidStart,
    TruncatedFrame, ValidationError,
)

START = b"\x02\xfd"
MAX_PAYLOAD = 254
_ESCAPES = {2: b"\x02\x00", 43: b"\x2b\x00", 254: b"\xfe\x00",
            17: b"\xfe\x12", 19: b"\xfe\x14"}
_UNESCAPES = {(2, 0): 2, (43, 0): 43, (254, 0): 254,
              (254, 18): 17, (254, 20): 19}


def uint(value, bits, name="value"):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < (1 << bits):
        raise ValidationError(f"{name} must be an unsigned {bits}-bit integer")
    return value


def checksum(data: bytes) -> int:
    result = 0
    for byte in data:
        result ^= byte ^ ((byte << 1) & 255)
    return result


@dataclass(frozen=True)
class Frame:
    command: int
    payload: bytes = b""

    def __post_init__(self):
        uint(self.command, 8, "command")
        if not isinstance(self.payload, bytes):
            raise ValidationError("payload must be immutable bytes")
        if len(self.payload) > MAX_PAYLOAD:
            raise ValidationError("payload exceeds 254 bytes")


def encode_frame(frame: Frame) -> bytes:
    logical = START + (len(frame.payload) + 1).to_bytes(2, "big")
    logical += bytes([frame.command]) + frame.payload
    body = logical[2:] + bytes([checksum(logical)])
    return START + b"".join(_ESCAPES.get(b, bytes([b])) for b in body)


class StreamDecoder:
    """Incremental, bounded parser supporting arbitrary chunk boundaries.

    On error all partial state is reset and the error is raised. The caller
    must invalidate its exchange; this is not a resynchronisation mechanism.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._prefix = bytearray()
        self._body = bytearray()
        self._escape = None
        self._length = None

    @property
    def has_partial(self) -> bool:
        return bool(self._prefix)

    def feed(self, chunk: bytes):
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise ValidationError("chunk must contain bytes")
        frames = []
        try:
            for byte in bytes(chunk):
                if len(self._prefix) < 2:
                    if byte != START[len(self._prefix)]:
                        raise InvalidStart("expected frame start 02 FD")
                    self._prefix.append(byte)
                    continue
                if self._escape is not None:
                    pair = (self._escape, byte)
                    if pair not in _UNESCAPES:
                        raise InvalidEscape("invalid escape sequence")
                    byte = _UNESCAPES[pair]
                    self._escape = None
                elif byte in (2, 43, 254):
                    self._escape = byte
                    continue
                self._body.append(byte)
                if len(self._body) == 2:
                    self._length = int.from_bytes(self._body, "big")
                    if not 1 <= self._length <= MAX_PAYLOAD + 1:
                        raise InvalidLength("length must be between 1 and 255")
                if self._length is not None and len(self._body) == self._length + 3:
                    if checksum(START + self._body[:-1]) != self._body[-1]:
                        raise ChecksumError("frame checksum mismatch")
                    frames.append(Frame(self._body[2], bytes(self._body[3:-1])))
                    self.reset()
        except (InvalidStart, InvalidEscape, InvalidLength, ChecksumError):
            self.reset()
            raise
        return frames

    def finish(self):
        if self.has_partial:
            self.reset()
            raise TruncatedFrame("incomplete frame or escape sequence")


def decode_frame(data: bytes) -> Frame:
    decoder = StreamDecoder()
    frames = decoder.feed(data)
    decoder.finish()
    if len(frames) != 1:
        raise InvalidLength("expected exactly one frame")
    return frames[0]
