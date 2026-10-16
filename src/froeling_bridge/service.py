"""One controller owner, bounded jobs and a separate periodic collector.

The collector waits for each individual read through the same FIFO as jobs,
allowing user work between sensors. Database work never runs on that worker.
"""
from concurrent.futures import Future, TimeoutError as FutureTimeout
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime, time as dt_time
from decimal import Decimal
from enum import Enum
from queue import Queue, Full, Empty
from threading import Event, Lock, Thread
import math
import time
import uuid

from .client import HeatingClient
from .errors import ValidationError, WriteOutcomeUnknown, WriteVerificationError, ProtocolError
from .messages import Command, ParameterType, TimeRange, parse_time
from .session import ProtocolSession
from .simulator import MemoryTransport
from .storage import ZONE, DatabaseUnavailable, MemoryRepository


class QueueBusy(Exception):
    pass


class ServiceStopped(Exception):
    pass


def public(value):
    """Exact decimals, HH:MM endpoints and JSON-safe protocol metadata."""
    if is_dataclass(value):
        result = {f.name: public(getattr(value, f.name)) for f in fields(value)}
        # Parameter.value and .unit are properties, not dataclass fields.
        for name in ("description", "unit", "version_text"):
            if hasattr(value, name):
                result[name] = public(getattr(value, name))
        if hasattr(value, "effective_factor"):
            result.update(value=str(value.value), unit=value.unit)
        return result
    if isinstance(value, dict):
        return {str(k): public(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [public(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")
    if isinstance(value, bytes):
        return value.hex()
    return value


def failure(exc):
    if isinstance(exc, WriteOutcomeUnknown):
        return dict(code="outcome_unknown", message="write confirmation incomplete", stage=exc.stage)
    if isinstance(exc, WriteVerificationError):
        return dict(code="verification_failed", message="readback differs from requested value", actual=public(exc.actual))
    if isinstance(exc, ValidationError):
        return dict(code="validation_error", message=str(exc))
    if isinstance(exc, ProtocolError):
        return dict(code=type(exc).__name__, message="controller transaction failed")
    if isinstance(exc, DatabaseUnavailable):
        return dict(code="database_unavailable", message="database operation failed")
    return dict(code=type(exc).__name__, message="operation failed")


class HeatingWorker:
    def __init__(self, capacity=64):
        self.queue = Queue(capacity)
        self.stop = Event()
        self.lock = Lock()
        self.thread = Thread(target=self._run, name="heating-worker", daemon=True)
        self.thread.start()

    def submit(self, function):
        future = Future()
        with self.lock:
            if self.stop.is_set():
                raise ServiceStopped()
            try:
                self.queue.put_nowait((future, function))
            except Full:
                raise QueueBusy() from None
        return future

    def _run(self):
        while not self.stop.is_set():
            try:
                future, function = self.queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function())
                    except Exception as exc:
                        future.set_exception(exc)
            finally:
                self.queue.task_done()

    def close(self):
        with self.lock:
            self.stop.set()
            while True:
                try:
                    future, _ = self.queue.get_nowait()
                except Empty:
                    break
                future.set_exception(ServiceStopped())
                self.queue.task_done()
        self.thread.join(timeout=6)


class BridgeService:
    def __init__(self, repository=None, mode="demo", interval=60, client=None,
                 queue_capacity=64, job_limit=1000, autostart=True):
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValidationError("interval must be a finite positive number of seconds")
        if mode not in ("demo", "demo-db", "database"):
            raise ValidationError("unknown service mode")
        self.mode = mode
        self.repository = repository or MemoryRepository()
        self.client = None if mode == "database" else (client or HeatingClient(ProtocolSession(MemoryTransport())))
        self.worker = None if mode == "database" else HeatingWorker(queue_capacity)
        self.interval = interval
        self.job_limit = job_limit
        self.lock = Lock()
        self.cycle_lock = Lock()
        self.jobs = {}
        self.values = {}
        self.stop = Event()
        self.collector = None
        self.collector_state = dict(enabled=mode != "database", interval_seconds=interval,
                                    running=False, last_cycle=None, last_successful_store=None,
                                    stored=0, errors=[], skipped=[])
        if autostart and self.worker:
            self.collector = Thread(target=self._collect_loop, name="collector", daemon=True)
            self.collector.start()

    def close(self):
        self.stop.set()
        if self.collector:
            self.collector.join(timeout=6)
        if self.worker:
            self.worker.close()
        if self.collector and self.collector.is_alive():
            self.collector.join(timeout=6)

    def collector_status(self):
        with self.lock:
            return deepcopy(self.collector_state)

    def cached_values(self):
        with self.lock:
            return deepcopy(list(self.values.values()))

    def _collect_loop(self):
        while not self.stop.is_set():
            start = time.monotonic()
            self.collect_once()
            # Slow cycles skip missed intervals; do not spin to catch up.
            slots = max(1, math.floor((time.monotonic() - start) / self.interval) + 1)
            self.stop.wait(max(0, start + slots * self.interval - time.monotonic()))

    def _wait(self, future):
        while True:
            try:
                return future.result(timeout=0.1)
            except FutureTimeout:
                if future.done():
                    raise
                if self.stop.is_set():
                    future.cancel()
                    raise ServiceStopped()

    def read_sensor(self, sensor):
        address, kind = sensor["address"], sensor["type"]
        text = None
        if kind == "VA":
            value = self.client.get_measurement(address, sensor["factor"], sensor["res1"])
        elif kind in ("DO", "DI", "AO"):
            command = {"DO": Command.DIGITAL_OUT, "DI": Command.DIGITAL_IN, "AO": Command.ANALOG_OUT}[kind]
            state = self.client.get_io(address, command).state
            value = Decimal(state if kind == "AO" else int(bool(state)))
        elif kind == "UD" and address in (1, 2):
            status = self.client.get_status()
            value = Decimal(status.state if address == 1 else status.mode)
            text = status.state_text if address == 1 else status.mode_text
        elif kind == "UD" and address == 3:
            local = self.client.get_firmware().local_time
            value = Decimal(int(local.replace(tzinfo=ZONE).timestamp()))
            text = local.strftime("%Y-%m-%d %H:%M:%S")
        else:
            raise ValidationError("unsupported sensor type/address")
        return dict(address=address, type=kind, value=value, text=text)

    def collect_once(self):
        if not self.worker or self.stop.is_set():
            return
        if not self.cycle_lock.acquire(blocking=False):
            raise QueueBusy()
        errors, skipped, samples = [], [], []
        stamp = int(time.time())
        when = datetime.fromtimestamp(stamp, ZONE).replace(tzinfo=None)
        with self.lock:
            self.collector_state.update(running=True, last_cycle=when.isoformat())
        stored = 0
        try:
            sensors = self.repository.sensors()
            # Drop removed entries; retain last success of selected but failing sensors.
            selected = {(s["address"], s["type"]) for s in sensors
                        if s["state"] == "A" or s["record"] == "A"}
            with self.lock:
                self.values = {k: v for k, v in self.values.items() if k in selected}
            for sensor in sensors:
                if self.stop.is_set():
                    break
                if sensor["state"] != "A" and sensor["record"] != "A":
                    continue
                identity = dict(address=sensor["address"], type=sensor["type"])
                if sensor["type"] not in ("VA", "DO", "DI", "AO", "UD") or (
                        sensor["type"] == "UD" and sensor["address"] not in (1, 2, 3)):
                    skipped.append(dict(**identity, reason="unsupported"))
                    continue
                try:
                    sample = self._wait(self.worker.submit(lambda s=sensor: self.read_sensor(s)))
                    observed_at = datetime.now(ZONE).isoformat()
                    with self.lock:
                        self.values[(sensor["address"], sensor["type"])] = public(dict(
                            **sample, observed_at=observed_at, source="simulator", unit=sensor["unit"]))
                    if sensor["record"] == "A":
                        samples.append(sample)
                except ServiceStopped:
                    break
                except Exception as exc:
                    errors.append(dict(**identity, error=failure(exc)))
            if samples and not self.stop.is_set():
                stamp = int(time.time())
                when = datetime.fromtimestamp(stamp, ZONE).replace(tzinfo=None)
                stored = self.repository.store_cycle(samples, when, stamp)
                with self.lock:
                    self.collector_state["last_successful_store"] = datetime.now(ZONE).isoformat()
        except Exception as exc:
            errors.append(dict(error=failure(exc)))
        finally:
            with self.lock:
                self.collector_state.update(running=False, stored=stored, errors=errors, skipped=skipped)
            self.cycle_lock.release()

    def _job_action(self, data):
        if not self.worker:
            raise ValidationError("controller operations unavailable in database mode")
        if not isinstance(data, dict) or not isinstance(data.get("operation"), str):
            raise ValidationError("job requires an operation")
        operation = data["operation"]
        simple = {"status": self.client.get_status, "firmware": self.client.get_firmware,
                  "discover_menu": lambda: self.client.get_menu(timeout=10),
                  "time_ranges": lambda: self.client.get_time_ranges(timeout=10)}
        if operation in simple:
            if set(data) != {"operation"}:
                raise ValidationError("unexpected job fields")
            return simple[operation]
        if operation in ("read_parameter", "write_parameter"):
            expected = {"operation", "menu_id"} | ({"value"} if operation == "write_parameter" else set())
            if set(data) != expected or type(data["menu_id"]) is not int or data["menu_id"] < 1:
                raise ValidationError("parameter job requires a valid menu_id and matching fields")
            item = self.repository.menu_item(data["menu_id"])
            if not item:
                raise ValidationError("unknown menu item")
            try:
                kind = ParameterType(item["type"])
            except ValueError:
                raise ValidationError("menu item is not an editable parameter") from None
            if operation == "read_parameter":
                return lambda: self.client.get_parameter(item["address"])
            value = data["value"]
            if kind == ParameterType.BOOLEAN:
                if type(value) is not bool:
                    raise ValidationError("boolean parameter requires a JSON boolean")
            elif kind == ParameterType.TIME:
                parse_time(value)
            else:
                if not isinstance(value, str):
                    raise ValidationError("numeric parameter requires a decimal string")
                try:
                    numeric = Decimal(value)
                    if not numeric.is_finite():
                        raise ValueError()
                except (ValueError, ArithmeticError):
                    raise ValidationError("invalid decimal string") from None
            return lambda: self.client.set_parameter(item["address"], value, kind)
        if operation == "measurement":
            if set(data) != {"operation", "address", "type"} or type(data["address"]) is not int:
                raise ValidationError("measurement requires address and type")
            sensor = next((s for s in self.repository.sensors()
                           if s["address"] == data["address"] and s["type"] == data["type"]), None)
            if not sensor:
                raise ValidationError("unknown sensor")
            return lambda: self.read_sensor(sensor)
        if operation == "write_time_range":
            if set(data) != {"operation", "address", "index", "start", "end"}:
                raise ValidationError("time-range job requires address/index/start/end")
            if type(data["address"]) is not int or not 0 <= data["address"] <= 254 or type(data["index"]) is not int or not 0 <= data["index"] < 4:
                raise ValidationError("invalid time-program address/index")
            interval = TimeRange(None if data["start"] is None else parse_time(data["start"]),
                                 None if data["end"] is None else parse_time(data["end"]))
            return lambda: self.client.set_time_range(data["address"], data["index"], interval, timeout=10)
        raise ValidationError("unknown operation")

    def submit_job(self, data):
        action = self._job_action(data)
        identifier = uuid.uuid4().hex
        with self.lock:
            if len(self.jobs) >= self.job_limit:
                oldest = next((k for k, v in self.jobs.items() if v["state"] in ("completed", "failed")), None)
                if oldest is None:
                    raise QueueBusy()
                del self.jobs[oldest]
            self.jobs[identifier] = dict(id=identifier, state="queued", operation=data["operation"],
                                         source="simulator", created_at=datetime.now(ZONE).isoformat())
        def execute():
            with self.lock:
                self.jobs[identifier]["state"] = "running"
            return action()
        try:
            future = self.worker.submit(execute)
        except Exception:
            with self.lock:
                del self.jobs[identifier]
            raise
        def complete(future):
            try:
                result = public(future.result())
                update = dict(state="completed", result=result)
            except Exception as exc:
                update = dict(state="failed", error=failure(exc))
            with self.lock:
                self.jobs[identifier].update(update, finished_at=datetime.now(ZONE).isoformat())
        future.add_done_callback(complete)
        return identifier

    def get_job(self, identifier):
        with self.lock:
            return deepcopy(self.jobs.get(identifier))
