"""p4d 0.10.2 repositories. Connections are private to each operation.

Only TestDatabase can write, and only to an explicitly named loopback test DB.
No repository creates or migrates tables on startup.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json
import re
from threading import RLock
from zoneinfo import ZoneInfo

from .errors import ValidationError

ZONE = ZoneInfo("Europe/Berlin")
MAX_ROWS = 1000


class DatabaseUnavailable(Exception):
    """Sanitized failure: driver exceptions may contain credentials or row data."""


@dataclass(frozen=True)
class DatabaseConfig:
    database: str
    user: str
    password: str = field(default="", repr=False)
    host: str = "127.0.0.1"
    port: int = 3306

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
            if set(data) - {"database", "user", "password", "host", "port"}:
                raise ValueError()
            result = cls(**data)
            if not all(isinstance(x, str) for x in (result.database, result.user,
                                                    result.password, result.host)):
                raise ValueError()
            if not result.database or not result.user or type(result.port) is not int or not 1 <= result.port <= 65535:
                raise ValueError()
            return result
        except (OSError, ValueError, TypeError):
            raise ValidationError("invalid database configuration file") from None

    def require_test(self):
        if self.host not in ("127.0.0.1", "localhost", "::1") or not re.fullmatch(
                r"froeling_bridge_test_[a-z0-9_]+", self.database):
            raise ValidationError("writes require a loopback database named froeling_bridge_test_<name>")

    def connect(self):
        import pymysql
        return pymysql.connect(host=self.host, port=self.port, user=self.user,
                               password=self.password, database=self.database,
                               charset="utf8mb3", autocommit=False,
                               cursorclass=pymysql.cursors.DictCursor,
                               connect_timeout=3, read_timeout=5, write_timeout=5,
                               local_infile=False)


def demo_sensors():
    from .simulator import demo_heater
    rows = [dict(address=s.address, type="VA", factor=s.factor, res1=s.data_type,
                 unit=s.unit, title=s.description, usrtitle=None, state="A", record="A")
            for s in demo_heater().value_specs]
    rows += [dict(address=a, type="UD", factor=1, res1=1, unit="", title=t,
                  usrtitle=None, state="A", record="A")
             for a, t in ((1, "Zustand"), (2, "Betriebsart"), (3, "Heizungszeit"))]
    return rows


def demo_menu():
    from .simulator import demo_heater
    return [dict(id=i, parent=m.parent, child=m.child, type=m.item_type,
                 address=m.address, title=m.description, value=None)
            for i, m in enumerate(demo_heater().menu, 1)]


def check_history(address, sensor_type, start, end, aggregate, limit):
    if type(address) is not int or not 0 <= address < 65535:
        raise ValidationError("invalid sensor address")
    if not isinstance(sensor_type, str) or not re.fullmatch(r"[A-Z0-9]{1,8}", sensor_type):
        raise ValidationError("invalid sensor type")
    if aggregate not in ("S", "A") or type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise ValidationError("aggregate must be S/A and limit 1..1000")
    if not all(isinstance(t, datetime) and t.tzinfo is None for t in (start, end)) or start >= end:
        raise ValidationError("history needs increasing local timestamps without timezone offsets")


class MemoryRepository:
    """Bounded ephemeral demo store, never seeded from real database contents."""
    source = "simulator"

    def __init__(self, max_samples=10000):
        self._lock = RLock()
        self.rows = {}
        self.peaks = {}
        self.max_samples = max_samples
        self.available = True

    def sensors(self):
        return demo_sensors()

    def menu(self, parent):
        return [m for m in demo_menu() if m["parent"] == parent]

    def menu_item(self, item_id):
        return next((m for m in demo_menu() if m["id"] == item_id), None)

    def history(self, address, sensor_type, start, end, aggregate="S", limit=1000):
        check_history(address, sensor_type, start, end, aggregate, limit)
        with self._lock:
            rows = [dict(r) for r in self.rows.values()
                    if r["address"] == address and r["type"] == sensor_type
                    and r["aggregate"] == aggregate and start <= r["time"] < end]
            return sorted(rows, key=lambda r: r["time"])[:limit]

    def store_cycle(self, samples, when, stamp):
        rows = prepare_samples(samples, when, stamp)
        with self._lock:
            for row in rows:
                key = (row["address"], row["type"], "S", when)
                row["inssp"] = self.rows.get(key, row)["inssp"]
                self.rows[key] = row
                peak_key = (row["address"], row["type"])
                low, high = self.peaks.get(peak_key, (row["value"], row["value"]))
                self.peaks[peak_key] = min(low, row["value"]), max(high, row["value"])
            while len(self.rows) > self.max_samples:
                del self.rows[next(iter(self.rows))]
        return len(rows)


def prepare_samples(samples, when, stamp):
    if when.tzinfo is not None or when.microsecond:
        raise ValidationError("storage timestamp must be local with second precision")
    rows = []
    for sample in samples:
        value = Decimal(str(sample["value"]))
        if not value.is_finite():
            raise ValidationError("sample must be finite")
        check_history(sample["address"], sample["type"], datetime(2000, 1, 1),
                      datetime(2000, 1, 2), "S", 1)
        text = sample.get("text") or None
        if text is not None and len(text) > 50:
            raise ValidationError("sample text exceeds p4d column length")
        rows.append(dict(address=sample["address"], type=sample["type"], aggregate="S",
                         time=when, inssp=stamp, updsp=stamp, value=value,
                         text=text, samples=1))
    return rows


class ReadOnlyDatabase:
    source = "p4d-database"

    def __init__(self, config):
        self.config = config
        self.available = None

    @contextmanager
    def transaction(self, writable=False):
        if writable and not isinstance(self, TestDatabase):
            raise ValidationError("repository is read-only")
        connection = None
        try:
            connection = self.config.connect()
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION max_statement_time=5")
                cursor.execute("START TRANSACTION" if writable else "START TRANSACTION READ ONLY")
                yield cursor
            if writable:
                connection.commit()
            else:
                connection.rollback()
            self.available = True
        except ValidationError:
            raise
        except Exception:
            self.available = False
            # Do not retry: commit may have completed before the connection failed.
            raise DatabaseUnavailable("database operation failed") from None
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
                connection.close()

    def sensors(self):
        with self.transaction() as cursor:
            cursor.execute("SELECT address,type,state,record,factor,res1,unit,title,usrtitle "
                           "FROM valuefacts ORDER BY type,address LIMIT 4097")
            rows = cursor.fetchall()
            if len(rows) > 4096:
                raise ValidationError("sensor catalogue exceeds 4096 entries")
            return rows

    def menu(self, parent):
        with self.transaction() as cursor:
            cursor.execute("SELECT id,parent,child,type,address,title,value,unit,digits,"
                           "min,max,def,factor,unknown1,unknown2,updsp FROM menu "
                           "WHERE parent=%s ORDER BY id LIMIT 4097", (parent,))
            rows = cursor.fetchall()
            if len(rows) > 4096:
                raise ValidationError("menu level exceeds 4096 entries")
            return rows

    def menu_item(self, item_id):
        with self.transaction() as cursor:
            cursor.execute("SELECT id,parent,child,type,address,title FROM menu WHERE id=%s", (item_id,))
            return cursor.fetchone()

    def history(self, address, sensor_type, start, end, aggregate="S", limit=1000):
        check_history(address, sensor_type, start, end, aggregate, limit)
        with self.transaction() as cursor:
            cursor.execute("SELECT address,type,aggregate,time,inssp,updsp,value,text,samples "
                           "FROM samples WHERE address=%s AND type=%s AND aggregate=%s "
                           "AND time >= %s AND time < %s ORDER BY time LIMIT %s",
                           (address, sensor_type, aggregate, start, end, limit))
            rows = cursor.fetchall()
            for row in rows:
                if row["value"] is not None:
                    row["value"] = Decimal(str(row["value"]))
            return rows


class TestDatabase(ReadOnlyDatabase):
    source = "simulator-test-database"

    def __init__(self, config):
        config.require_test()
        super().__init__(config)

    def store_cycle(self, samples, when, stamp):
        rows = prepare_samples(samples, when, stamp)
        with self.transaction(writable=True) as cursor:
            for row in rows:
                cursor.execute(
                    "INSERT INTO samples (address,type,aggregate,time,inssp,updsp,value,text,samples) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                    "updsp=VALUES(updsp),value=VALUES(value),text=VALUES(text),samples=VALUES(samples)",
                    tuple(row[k] for k in ("address", "type", "aggregate", "time", "inssp", "updsp", "value", "text", "samples")))
                cursor.execute(
                    "INSERT INTO peaks (address,type,inssp,updsp,minv,maxv) VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE updsp=IF(minv IS NULL OR maxv IS NULL OR "
                    "VALUES(minv)<minv OR VALUES(maxv)>maxv,VALUES(updsp),updsp),"
                    "minv=LEAST(COALESCE(minv,VALUES(minv)),VALUES(minv)),"
                    "maxv=GREATEST(COALESCE(maxv,VALUES(maxv)),VALUES(maxv))",
                    (row["address"], row["type"], stamp, stamp, row["value"], row["value"]))
        return len(rows)
