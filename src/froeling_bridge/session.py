"""A single owner for complete exchanges, with bounded deadlines and no retries."""
from collections import deque
from contextlib import contextmanager
import math
import threading
import time
from typing import Protocol

from .codec import Frame, StreamDecoder, encode_frame
from .errors import (
    RequestTimeout, SessionBroken, TransportError,
    UnexpectedData, UnexpectedReply, ValidationError,
)


class ByteTransport(Protocol):
    """Contract for a future transport; no physical adapter is supplied here.

    read(max_bytes, timeout) returns available bytes, or b'' on timeout.
    timeout=0 must never block. write(data, timeout) returns bytes accepted;
    partial writes are supported. Both operations must honour their deadline.
    """

    def read(self, max_bytes: int, timeout: float) -> bytes:
        ...

    def write(self, data: bytes, timeout: float) -> int:
        ...


class ProtocolSession:
    def __init__(self, transport: ByteTransport, clock=time.monotonic):
        self.transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        self._broken = False
        self._decoder = StreamDecoder()
        self._pending = deque()

    @property
    def broken(self):
        return self._broken

    @contextmanager
    def transaction(self, timeout=2.0):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValidationError("timeout must be finite and positive")
        deadline = self._clock() + timeout
        if not self._lock.acquire(timeout=timeout):
            raise RequestTimeout("timed out waiting for session ownership")
        try:
            if self._broken:
                raise SessionBroken("session requires a new clean transport")
            tx = _Transaction(self, deadline)
            tx.ensure_idle()
            yield tx
            tx.ensure_idle()
            tx.remaining()
        except ValidationError:
            # Invalid input may follow a complete metadata read. Keep the
            # session usable only if no response bytes remain outstanding.
            try:
                tx.ensure_idle()
            except BaseException:
                self._broken = True
                raise
            raise
        except BaseException:
            # Cancellation/programming failures can interrupt an exchange too.
            self._broken = True
            raise
        finally:
            self._lock.release()


class _Transaction:
    def __init__(self, session, deadline):
        self.session = session
        self.deadline = deadline
        self.send_attempted = False

    def remaining(self):
        duration = self.deadline - self.session._clock()
        if duration <= 0:
            raise RequestTimeout("transaction deadline exceeded")
        return duration

    def read(self, timeout):
        data = self.session.transport.read(512, timeout)
        if not isinstance(data, bytes) or len(data) > 512:
            raise TransportError("transport violated byte-read contract")
        return data

    def ensure_idle(self):
        if self.session._pending or self.session._decoder.has_partial:
            raise UnexpectedData("unconsumed response data; session is not idle")
        data = self.read(0.0)
        if data:
            raise UnexpectedData("unsolicited data before/after a request")

    def send(self, frame: Frame):
        self.send_attempted = False
        self.ensure_idle()
        data = encode_frame(frame)
        offset = 0
        while offset < len(data):
            remaining = self.remaining()
            self.send_attempted = True
            count = self.session.transport.write(data[offset:], remaining)
            if type(count) is not int or not 0 < count <= len(data) - offset:
                raise TransportError("transport did not accept a valid number of bytes")
            offset += count

    def receive(self, command):
        while not self.session._pending:
            data = self.read(self.remaining())
            if not data:
                raise RequestTimeout("response timed out")
            self.session._pending.extend(self.session._decoder.feed(data))
        self.remaining()
        frame = self.session._pending.popleft()
        if frame.command != command:
            raise UnexpectedReply(f"expected command 0x{command:02X}, received 0x{frame.command:02X}")
        return frame

    def exchange(self, frame: Frame, commands):
        self.send(frame)
        return tuple(self.receive(command) for command in commands)
