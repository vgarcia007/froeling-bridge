"""Optional p4d-compatible historian. No SQL operation runs on the heating worker."""

from dataclasses import replace
from datetime import datetime, timedelta
from importlib.resources import files
import json
import re
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
import time

from .errors import ValidationError
from .storage import (
    P4dDatabase,
    ReadOnlyDatabase,
    DatabaseUnavailable,
    ZONE,
    prepare_samples,
)


def initialize_database(config, local):
    """Explicit setup of empty databases only; own interrupted DDL can be resumed."""
    if not re.fullmatch(r"[A-Za-z0-9_$-]{1,64}", config.database):
        raise ValidationError(
            "database name must contain 1..64 letters, digits, _, $, or -"
        )
    schema = json.loads(
        files("froeling_bridge").joinpath("production-schema.json").read_text()
    )
    identity = [config.host, config.port, config.database, config.user]
    connection = None
    try:
        connection = replace(config, database="").connect()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
                (config.database,),
            )
            exists = cursor.fetchone() is not None
            owned = local.get_meta("database_initialization") == identity
            if exists:
                cursor.execute("USE `" + config.database + "`")
                cursor.execute("SHOW TABLES")
                present = {next(iter(row.values())) for row in cursor.fetchall()}
            else:
                present = set()
            if present and (
                not owned
                or local.get_meta("database_initialization_complete") == identity
            ):
                # Existing p4d database: inspect only, never "repair" unknown structures.
                repo = P4dDatabase(config, allow_recording=True)
                repo.validate_schema()
                return repo
            if present - set(schema):
                raise ValidationError("unexpected tables in interrupted database setup")
            local.set_meta("database_initialization", identity)
            if not exists:
                cursor.execute(
                    "CREATE DATABASE `" + config.database + "` CHARACTER SET utf8mb3"
                )
                cursor.execute("USE `" + config.database + "`")
            for table, columns in schema.items():
                if table in present:
                    cursor.execute("SHOW COLUMNS FROM `" + table + "`")
                    if {r["Field"] for r in cursor.fetchall()} != {
                        c["name"] for c in columns
                    }:
                        raise ValidationError(
                            "interrupted database schema differs; preserved"
                        )
                    continue
                definitions = [
                    f"`{c['name']}` {c['type']} {'NULL' if c['nullable'] else 'NOT NULL'} {'AUTO_INCREMENT' if c['auto_increment'] else ''}"
                    for c in columns
                ]
                definitions.append(
                    "PRIMARY KEY ("
                    + ",".join("`" + c["name"] + "`" for c in columns if c["primary"])
                    + ")"
                )
                if table == "samples":
                    definitions += [
                        "INDEX time (`time`)",
                        "INDEX aggregate (`aggregate`)",
                        "INDEX addr_type_time (address,type,time)",
                    ]
                cursor.execute(
                    "CREATE TABLE `"
                    + table
                    + "` ("
                    + ",".join(definitions)
                    + ") ENGINE=InnoDB"
                )
        connection.commit()
        local.set_meta("database_initialization_complete", identity)
        repo = P4dDatabase(config, allow_recording=True)
        repo.validate_schema()
        return repo
    except (ValidationError, DatabaseUnavailable):
        raise
    except Exception:
        raise DatabaseUnavailable(
            "database setup failed; check connectivity and CREATE permissions"
        ) from None
    finally:
        if connection:
            connection.close()


class Historian:
    def __init__(self, repository, local, queue_size=4, autostart=True):
        self.repository, self.local = repository, local
        self.queue = Queue(queue_size)
        self.stop = Event()
        self.lock = Lock()
        self.state = dict(
            configured=True,
            available=None,
            error=None,
            stored=0,
            dropped_cycles=0,
            last_success=None,
            pending_settings=0,
            aggregation=dict(
                running=False, last_success=None, error=None, processed=0, conflicts=0
            ),
        )
        self.history_days = 91
        self.aggregate_minutes = 30
        self._settings_loaded = False
        self._catalogue_stamp = None
        self.next_aggregation = self._next_run()
        self.thread = (
            Thread(target=self._run, name="historian", daemon=True)
            if autostart
            else None
        )
        if self.thread:
            self.thread.start()

    @staticmethod
    def _next_run():
        now = datetime.now(ZONE)
        result = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if result <= now:
            result = (now + timedelta(days=1)).replace(
                hour=1, minute=0, second=0, microsecond=0
            )
        return result

    def status(self):
        from copy import deepcopy

        with self.lock:
            return dict(
                deepcopy(self.state),
                history_days=self.history_days,
                aggregate_minutes=self.aggregate_minutes,
                next_aggregation=self.next_aggregation.isoformat(),
            )

    def enqueue(self, samples, when, stamp):
        # Validate before accepting; this count is queued, not a database commit acknowledgement.
        prepare_samples(samples, when, stamp)
        with self.lock:
            if self.state["available"] is False:
                self.state["dropped_cycles"] += 1
                return 0
        try:
            self.queue.put_nowait((list(samples), when, stamp))
        except Full:
            with self.lock:
                self.state["dropped_cycles"] += 1
            return 0
        return len(samples)

    def _settings(self):
        if self._settings_loaded:
            return
        with self.repository.transaction() as cursor:
            cursor.execute(
                "SELECT name,value FROM config WHERE owner='p4d' AND name IN ('aggregateHistory','aggregateInterval')"
            )
            values = {r["name"]: r["value"] for r in cursor.fetchall()}
        try:
            days, minutes = int(values.get("aggregateHistory", 91)), int(
                values.get("aggregateInterval", 30)
            )
            if not 0 <= days <= 36500 or minutes not in (
                1,
                2,
                3,
                5,
                6,
                10,
                12,
                15,
                20,
                30,
                60,
            ):
                raise ValueError()
        except (TypeError, ValueError):
            days, minutes = 0, 30
            with self.lock:
                self.state["aggregation"][
                    "error"
                ] = "unsupported aggregation settings; history recording remains enabled"
        self.history_days, self.aggregate_minutes = days, minutes
        self._settings_loaded = True

    def sync_catalogue(self):
        stamp = self.local.get_meta("discovered_at")
        if not stamp or stamp == self._catalogue_stamp:
            return
        # Preserve existing selection/custom titles; new entries use discovered defaults.
        with self.repository.transaction(writable=True) as cursor:
            for row in self.local.sensors():
                now = int(time.time())
                cursor.execute(
                    "INSERT INTO valuefacts (address,type,inssp,updsp,state,record,unit,factor,res1,title,usrtitle) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE factor=VALUES(factor),res1=VALUES(res1)",
                    (
                        row["address"],
                        row["type"],
                        now,
                        now,
                        row["state"],
                        row["record"],
                        row["unit"],
                        row["factor"],
                        row["res1"],
                        row["title"],
                        row.get("usrtitle"),
                    ),
                )
            cursor.execute("SELECT id FROM menu LIMIT 1")
            if not cursor.fetchone():
                for row in self.local.menu_catalog():
                    cursor.execute(
                        "INSERT INTO menu (id,parent,child,type,address,title,unit,unknown1,unknown2) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        tuple(
                            row.get(k)
                            for k in (
                                "id",
                                "parent",
                                "child",
                                "type",
                                "address",
                                "title",
                                "unit",
                                "unknown1",
                                "unknown2",
                            )
                        ),
                    )
        self._catalogue_stamp = stamp

    def sync_flags(self):
        changes = self.local.pending_changes()
        with self.lock:
            self.state["pending_settings"] = len(changes)
        for change in changes:
            with self.repository.transaction(writable=True) as cursor:
                for key, field in (("record", "record"), ("active", "state")):
                    if key in change["changes"]:
                        cursor.execute(
                            "UPDATE valuefacts SET "
                            + field
                            + "=%s,updsp=%s WHERE type=%s AND address=%s",
                            (
                                "A" if change["changes"][key] else "D",
                                int(time.time()),
                                change["type"],
                                change["address"],
                            ),
                        )
            self.local.acknowledge_change(change)
        with self.lock:
            self.state["pending_settings"] = len(self.local.pending_changes())

    def aggregate(self, now=None, max_days=7):
        """One transaction/day. Existing A buckets are never overwritten or double-counted."""
        now = now or datetime.now(ZONE)
        if not self.history_days:
            return
        cutoff = datetime.fromtimestamp(
            now.timestamp() - self.history_days * 86400, ZONE
        ).replace(tzinfo=None, second=0, microsecond=0)
        cutoff = cutoff.replace(
            minute=(cutoff.minute // self.aggregate_minutes) * self.aggregate_minutes
        )
        with self.lock:
            self.state["aggregation"].update(
                running=True, error=None, processed=0, conflicts=0
            )
        try:
            # Scan each day once, including conflict-only days, with bounded work per run.
            saved_cursor = self.local.get_meta("aggregation_cursor")
            lower = (
                datetime.fromisoformat(saved_cursor)
                if saved_cursor
                else datetime(1970, 1, 1)
            )
            for _ in range(max_days):
                if self.stop.is_set():
                    break
                with self.repository.transaction() as cursor:
                    cursor.execute(
                        "SELECT time FROM samples WHERE aggregate='S' AND time>=%s AND time<%s ORDER BY time LIMIT 1",
                        (lower, cutoff),
                    )
                    first = cursor.fetchone()
                if not first:
                    self.local.set_meta("aggregation_cursor", None)
                    break
                start = first["time"].replace(hour=0, minute=0, second=0, microsecond=0)
                end = min(start + timedelta(days=1), cutoff)
                width = self.aggregate_minutes * 60
                with self.repository.transaction(writable=True) as cursor:
                    cursor.execute(
                        "SELECT address,type,TIMESTAMP(DATE(time),SEC_TO_TIME((TIME_TO_SEC(TIME(time)) DIV %s)*%s))+INTERVAL %s MINUTE AS bucket, ROUND(SUM(value)/COUNT(*),2) AS mean,COUNT(*) AS n,MAX(time) AS last_time FROM samples WHERE aggregate='S' AND time>=%s AND time<%s GROUP BY address,type,bucket",
                        (width, width, self.aggregate_minutes, start, end),
                    )
                    groups = cursor.fetchall()
                    processed, conflicts = 0, 0
                    for group in groups:
                        a, t, bucket = group["address"], group["type"], group["bucket"]
                        cursor.execute(
                            "SELECT time FROM samples WHERE address=%s AND type=%s AND aggregate='A' AND time=%s",
                            (a, t, bucket),
                        )
                        if cursor.fetchone():
                            conflicts += 1
                            continue
                        begin = bucket - timedelta(minutes=self.aggregate_minutes)
                        cursor.execute(
                            "SELECT text FROM samples WHERE address=%s AND type=%s AND aggregate='S' AND time=%s",
                            (a, t, group["last_time"]),
                        )
                        text = cursor.fetchone()["text"]
                        stamp = int(now.timestamp())
                        cursor.execute(
                            "INSERT INTO samples (address,type,aggregate,time,inssp,updsp,value,text,samples) VALUES (%s,%s,'A',%s,%s,%s,%s,%s,%s)",
                            (
                                a,
                                t,
                                bucket,
                                stamp,
                                stamp,
                                group["mean"],
                                text,
                                group["n"],
                            ),
                        )
                        cursor.execute(
                            "DELETE FROM samples WHERE address=%s AND type=%s AND aggregate='S' AND time>=%s AND time<%s",
                            (a, t, begin, bucket),
                        )
                        processed += group["n"]
                with self.lock:
                    self.state["aggregation"]["processed"] += processed
                    self.state["aggregation"]["conflicts"] += conflicts
                lower = start + timedelta(days=1)
                self.local.set_meta("aggregation_cursor", lower.isoformat())
            with self.lock:
                self.state["aggregation"]["last_success"] = datetime.now(
                    ZONE
                ).isoformat()
        except Exception:
            with self.lock:
                self.state["aggregation"][
                    "error"
                ] = "aggregation failed; current transaction rolled back"
            raise
        finally:
            with self.lock:
                self.state["aggregation"]["running"] = False

    def _run(self):
        while not self.stop.is_set():
            item = None
            try:
                item = self.queue.get(timeout=1)
            except Empty:
                pass
            try:
                self._settings()
                self.sync_catalogue()
                self.sync_flags()
                if item:
                    samples, when, stamp = item
                    stored = self.repository.store_cycle(samples, when, stamp)
                    with self.lock:
                        self.state.update(
                            stored=stored, last_success=datetime.now(ZONE).isoformat()
                        )
                with self.lock:
                    self.state.update(available=True, error=None)
                if datetime.now(ZONE) >= self.next_aggregation:
                    try:
                        self.aggregate()
                    finally:
                        self.next_aggregation = self._next_run()
            except Exception:
                with self.lock:
                    self.state.update(
                        available=False,
                        error="history database unavailable or incompatible",
                    )
                    if item:
                        self.state["dropped_cycles"] += 1
                self.stop.wait(5)
            finally:
                if item:
                    self.queue.task_done()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=15)
