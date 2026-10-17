"""Private, durable working catalogue; MariaDB is an optional history sink."""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
import uuid

from .errors import ValidationError
from .storage import DatabaseUnavailable, ZONE, check_history


def supported(sensor):
    return (
        sensor["type"] in ("VA", "DO", "DI", "AO")
        or sensor["type"] == "UD"
        and sensor["address"] in (1, 2, 3)
    )


class LocalRepository:
    source = "heating-local-catalogue"
    configurable = True

    def __init__(self, path, historian=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (
            self.path.is_symlink()
            or self.path.exists()
            and not stat.S_ISREG(self.path.stat().st_mode)
        ):
            raise ValidationError("local catalogue must be a regular file")
        self.lock = RLock()
        self.historian = historian
        self.available = True
        self.recovered = False
        try:
            self._initialize()
        except sqlite3.DatabaseError:
            # Preserve damaged data for diagnosis/recovery, never silently erase it.
            backup = self.path.with_name(
                self.path.name + ".damaged-" + uuid.uuid4().hex
            )
            for suffix in ("", "-wal", "-shm"):
                source = Path(str(self.path) + suffix)
                if source.exists():
                    source.rename(Path(str(backup) + suffix))
            self.recovered = True
            self._initialize()

    def _initialize(self):
        with sqlite3.connect(self.path) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("corrupt catalogue")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValidationError(
                    "local catalogue belongs to an unsupported version"
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sensor (type TEXT NOT NULL,address INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(type,address));
                CREATE TABLE IF NOT EXISTS menu (id INTEGER PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS latest (type TEXT NOT NULL,address INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(type,address));
                CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pending (type TEXT NOT NULL,address INTEGER NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(type,address));
                CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY,data TEXT NOT NULL);
                PRAGMA user_version=1;
            """
            )
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                with sqlite3.connect(self.path, timeout=5) as db:
                    yield db
                self.available = True
            except sqlite3.Error:
                self.available = False
                raise DatabaseUnavailable("local catalogue operation failed") from None

    def get_meta(self, name, default=None):
        with self.transaction() as db:
            row = db.execute("SELECT data FROM meta WHERE name=?", (name,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_meta(self, name, value):
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?)", (name, json.dumps(value))
            )

    def sensors(self):
        with self.transaction() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT data FROM sensor ORDER BY type,address")
            ]

    def menu_catalog(self):
        with self.transaction() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT data FROM menu ORDER BY id")
            ]

    def menu(self, parent):
        return [row for row in self.menu_catalog() if row["parent"] == parent]

    def menu_item(self, item_id):
        with self.transaction() as db:
            row = db.execute("SELECT data FROM menu WHERE id=?", (item_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def search_menu(self, query):
        from .menu import menu_paths, named_search

        rows = self.menu_catalog()
        return named_search(
            [row for row in rows if query.casefold() in row["title"].casefold()][:100],
            menu_paths(rows),
        )

    def time_programs(self):
        from .menu import time_program_catalog

        return time_program_catalog(self.menu_catalog())

    def replace_catalogue(self, sensors, menu, *, firmware=None):
        """Only called with a fully received catalogue; preferences survive rediscovery."""
        from .service import public

        if not sensors or not menu or len(sensors) > 4096 or len(menu) > 4096:
            raise ValidationError("empty or oversized discovery catalogue")
        sensors, menu = public(sensors), public(menu)
        with self.transaction() as db:
            old = {
                (t, a): json.loads(data)
                for t, a, data in db.execute("SELECT type,address,data FROM sensor")
            }
            db.execute("DELETE FROM sensor")
            db.execute("DELETE FROM menu")
            for row in sensors:
                row = dict(row)
                previous = old.get((row["type"], row["address"]), {})
                for field in ("state", "record", "usrtitle"):
                    if field in previous:
                        row[field] = previous[field]
                db.execute(
                    "INSERT INTO sensor VALUES (?,?,?)",
                    (row["type"], row["address"], json.dumps(row)),
                )
            for row in menu:
                db.execute(
                    "INSERT INTO menu VALUES (?,?)", (row["id"], json.dumps(row))
                )
            db.execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?)",
                ("discovered_at", json.dumps(datetime.now(ZONE).isoformat())),
            )
            db.execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?)",
                ("firmware", json.dumps(firmware)),
            )

    def import_preferences(self, sensors):
        """Store preferences before first discovery, including inactive/unseen legacy sensors."""
        from .service import public

        with self.transaction() as db:
            for row in public(sensors):
                found = db.execute(
                    "SELECT data FROM sensor WHERE type=? AND address=?",
                    (row["type"], row["address"]),
                ).fetchone()
                pending = db.execute(
                    "SELECT 1 FROM pending WHERE type=? AND address=?",
                    (row["type"], row["address"]),
                ).fetchone()
                if found and not pending:
                    current = json.loads(found[0])
                    current.update(
                        {key: row.get(key) for key in ("state", "record", "usrtitle")}
                    )
                    db.execute(
                        "UPDATE sensor SET data=? WHERE type=? AND address=?",
                        (json.dumps(current), row["type"], row["address"]),
                    )
                elif not found:
                    db.execute(
                        "INSERT INTO sensor VALUES (?,?,?)",
                        (row["type"], row["address"], json.dumps(row)),
                    )

    def patch_sensor(self, sensor_type, address, changes):
        if (
            not isinstance(changes, dict)
            or not changes
            or set(changes) - {"record", "active"}
            or any(type(v) is not bool for v in changes.values())
        ):
            raise ValidationError("sensor changes require record/active booleans")
        with self.transaction() as db:
            found = db.execute(
                "SELECT data FROM sensor WHERE type=? AND address=?",
                (sensor_type, address),
            ).fetchone()
            if not found:
                raise ValidationError("unknown sensor")
            row = json.loads(found[0])
            if any(changes.values()) and not supported(row):
                raise ValidationError("sensor type is not supported for collection")
            for key, field in (("record", "record"), ("active", "state")):
                if key in changes:
                    row[field] = "A" if changes[key] else "D"
            db.execute(
                "UPDATE sensor SET data=? WHERE type=? AND address=?",
                (json.dumps(row), sensor_type, address),
            )
            old = db.execute(
                "SELECT version,data FROM pending WHERE type=? AND address=?",
                (sensor_type, address),
            ).fetchone()
            pending = json.loads(old[1]) if old else {}
            pending.update(changes)
            db.execute(
                "INSERT OR REPLACE INTO pending VALUES (?,?,?,?)",
                (sensor_type, address, old[0] + 1 if old else 1, json.dumps(pending)),
            )
            return row

    def pending_changes(self):
        with self.transaction() as db:
            return [
                dict(type=t, address=a, version=v, changes=json.loads(data))
                for t, a, v, data in db.execute(
                    "SELECT type,address,version,data FROM pending"
                )
            ]

    def acknowledge_change(self, change):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM pending WHERE type=? AND address=? AND version=?",
                (change["type"], change["address"], change["version"]),
            )

    def remember_values(self, values):
        from .service import public

        with self.transaction() as db:
            for row in public(values):
                db.execute(
                    "INSERT OR REPLACE INTO latest VALUES (?,?,?)",
                    (row["type"], row["address"], json.dumps(row)),
                )

    def latest_values(self):
        with self.transaction() as db:
            return [
                dict(json.loads(data), origin="local-persisted")
                for data, in db.execute("SELECT data FROM latest")
            ]

    def audit_write(self, identifier, data):
        from .service import public

        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO audit VALUES (?,?)",
                (identifier, json.dumps(public(data))),
            )

    def store_cycle(self, samples, when, stamp):
        return self.historian.enqueue(samples, when, stamp) if self.historian else 0

    def history(self, address, sensor_type, start, end, aggregate="S", limit=1000):
        check_history(address, sensor_type, start, end, aggregate, limit)
        if not self.historian:
            raise DatabaseUnavailable("history database not configured")
        return self.historian.repository.history(
            address, sensor_type, start, end, aggregate, limit
        )
