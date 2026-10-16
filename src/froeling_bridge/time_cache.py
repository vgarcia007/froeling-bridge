"""Private, optional persistence for the last fully read time-program list."""

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from .messages import parse_time_ranges


def load(path):
    if path is None:
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            import stat

            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return None
            data = json.load(stream)
        stamp = datetime.fromisoformat(data["observed_at"])
        if stamp.tzinfo is None or not 1 <= len(data["items"]) <= 255:
            return None
        items = tuple(
            parse_time_ranges(bytes.fromhex(value)) for value in data["items"]
        )
        if items[-1].address != 0xDF or len({i.address for i in items}) != len(items):
            return None
        return items, stamp
    except (OSError, ValueError, KeyError, TypeError):
        return None
    except Exception:
        # A malformed diagnostic cache must not stop the controller collector.
        return None


def save(path, items, stamp):
    if path is None:
        return
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".time-cache-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(
                dict(observed_at=stamp, items=[i.list_payload().hex() for i in items]),
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
