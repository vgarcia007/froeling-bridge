"""Linux byte transport with deadlines, exclusive TTY ownership and read-only TX.

Opening never flushes RX. TIOCEXCL protects against subsequent non-root opens;
flock coordinates cooperating bridge processes. The host coordinator must stop
p4d and verify existing holders *before* opening: TIOCEXCL cannot evict them.
"""

import fcntl
import math
import os
import select
import stat
import termios
import time

from .codec import StreamDecoder
from .errors import RequestTimeout, TransportError, ValidationError
from .messages import Command

READ_COMMANDS = frozenset(
    (
        Command.CHECK,
        Command.VALUE,
        Command.VALUES_FIRST,
        Command.VALUES_NEXT,
        Command.MENU_FIRST,
        Command.MENU_NEXT,
        Command.VERSION,
        Command.TIMES_FIRST,
        Command.TIMES_NEXT,
        Command.DIGITAL_OUT,
        Command.ANALOG_OUT,
        Command.DIGITAL_IN,
        Command.ERRORS_FIRST,
        Command.ERRORS_NEXT,
        Command.STATE,
        Command.PARAMETER,
    )
)


class ReadOnlyTransport:
    """Validate complete outbound frames before the first byte reaches the TTY.

    Buffering supports partial writes from ProtocolSession. A physical write
    exception makes this wrapper unusable; it never retries ambiguous output.
    """

    def __init__(self, transport):
        self.transport = transport
        self._decoder = StreamDecoder()
        self._outgoing = bytearray()
        self._failed = False

    def read(self, max_bytes, timeout):
        return self.transport.read(max_bytes, timeout)

    def write(self, data, timeout):
        if self._failed:
            raise TransportError("read-only transport is unusable")
        deadline = time.monotonic() + timeout
        try:
            frames = self._decoder.feed(bytes(data))
            self._outgoing.extend(data)
            if len(self._outgoing) > 1024:
                raise ValidationError("outbound frame exceeds test limit")
            # ProtocolSession sends one frame at a time. Refuse concatenations,
            # including read+write, without transmitting the leading read.
            if len(frames) > 1 or (frames and self._decoder.has_partial):
                raise ValidationError("exactly one outbound frame is required")
            if frames:
                if frames[0].command not in READ_COMMANDS:
                    raise ValidationError(
                        "heating writes are disabled in hardware-read mode"
                    )
                frame = frames[0]
                addressed = {
                    Command.VALUE,
                    Command.DIGITAL_OUT,
                    Command.DIGITAL_IN,
                    Command.ANALOG_OUT,
                    Command.PARAMETER,
                }
                if len(frame.payload) != (2 if frame.command in addressed else 0):
                    raise ValidationError("unexpected payload for read-only command")
                offset = 0
                while offset < len(self._outgoing):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RequestTimeout("outbound deadline exceeded")
                    count = self.transport.write(
                        bytes(self._outgoing[offset:]), remaining
                    )
                    if (
                        type(count) is not int
                        or not 0 < count <= len(self._outgoing) - offset
                    ):
                        raise TransportError("invalid physical write count")
                    offset += count
                self._outgoing.clear()
            return len(data)
        except BaseException:
            self._failed = True
            raise

    def close(self):
        self.transport.close()


class SerialTransport:
    def __init__(self, path):
        self.fd = None
        self.original = None
        fd = None
        exclusive = False
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
            if not stat.S_ISCHR(os.fstat(fd).st_mode) or not os.isatty(fd):
                raise ValidationError("serial path must be a TTY character device")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(fd, termios.TIOCEXCL)
            exclusive = True
            self.original = termios.tcgetattr(fd)
            settings = termios.tcgetattr(fd)
            settings[0] = termios.IGNPAR
            settings[1] = 0
            settings[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
            settings[3] = 0
            settings[4] = settings[5] = termios.B57600
            settings[6][termios.VMIN] = 0
            settings[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            self.fd = fd
        except BaseException as exc:
            if fd is not None:
                try:
                    if self.original is not None:
                        termios.tcsetattr(fd, termios.TCSANOW, self.original)
                except (OSError, termios.error):
                    pass
                finally:
                    try:
                        if exclusive:
                            fcntl.ioctl(fd, termios.TIOCNXCL)
                    except (OSError, termios.error):
                        pass
                    os.close(fd)
            if isinstance(exc, ValidationError):
                raise
            if not isinstance(exc, Exception):
                raise
            raise TransportError(
                "serial device could not be opened exclusively"
            ) from None

    def _wait(self, timeout, writing=False):
        if self.fd is None:
            raise TransportError("serial device is closed")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValidationError("invalid serial timeout")
        deadline = time.monotonic() + timeout
        while True:
            try:
                ready = select.select(
                    [] if writing else [self.fd],
                    [self.fd] if writing else [],
                    [],
                    max(0, deadline - time.monotonic()),
                )
                return bool(ready[1] if writing else ready[0])
            except InterruptedError:
                if time.monotonic() >= deadline:
                    return False
            except (OSError, ValueError):
                raise TransportError("serial wait failed") from None

    def read(self, max_bytes, timeout):
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValidationError("read size must be positive")
        if not self._wait(timeout):
            return b""
        try:
            data = os.read(self.fd, max_bytes)
            if not data:
                raise TransportError("serial device disconnected")
            return data
        except BlockingIOError:
            return b""
        except (OSError, termios.error):
            raise TransportError("serial read failed") from None

    def write(self, data, timeout):
        if not self._wait(timeout, writing=True):
            raise RequestTimeout("serial write timed out")
        try:
            return os.write(self.fd, data)
        except (OSError, termios.error):
            raise TransportError("serial write failed") from None

    def close(self):
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            termios.tcsetattr(fd, termios.TCSANOW, self.original)
        except (OSError, termios.error):
            pass  # A disconnected adapter must still be closed.
        finally:
            try:
                fcntl.ioctl(fd, termios.TIOCNXCL)
            except (OSError, termios.error):
                pass
            os.close(fd)


class TraceTransport:
    """Bounded, private raw diagnostic trace; never included in API results."""

    def __init__(self, transport, path, limit=262144):
        self.transport = transport
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.stream = os.fdopen(fd, "wb")
        self.remaining = limit

    def _record(self, direction, data):
        if not data or self.remaining <= 0:
            return
        record = (f"{time.monotonic():.6f} {direction} {data.hex()}\n").encode("ascii")
        if len(record) > self.remaining:
            self.remaining = 0
            return
        self.stream.write(record)
        self.stream.flush()
        self.remaining -= len(record)

    def read(self, size, timeout):
        data = self.transport.read(size, timeout)
        self._record("RX", data)
        return data

    def write(self, data, timeout):
        count = self.transport.write(data, timeout)
        self._record("TX", data[:count])
        return count

    def close(self):
        try:
            self.transport.close()
        finally:
            self.stream.close()
