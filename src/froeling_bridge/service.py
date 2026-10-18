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
import logging
import time
import uuid

from .client import HeatingClient
from .errors import ReadOnlyViolation, ValidationError, WriteOutcomeUnknown, WriteVerificationError, ProtocolError
from .messages import Command, ParameterType, TimeRange, parse_time
from .session import ProtocolSession
from .simulator import MemoryTransport
from .storage import ZONE, DatabaseUnavailable, MemoryRepository
from .recording import automatic_recording


class QueueBusy(Exception):
    pass


class ServiceStopped(Exception):
    pass


def public(value):
    """Exact decimals, HH:MM endpoints and JSON-safe protocol metadata."""
    if is_dataclass(value):
        result = {f.name: public(getattr(value, f.name)) for f in fields(value)}
        # Parameter.value and .unit are properties, not dataclass fields.
        for name in ("description", "unit", "version_text", "start", "end"):
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
                 queue_capacity=64, job_limit=1000, autostart=True, max_cycle_seconds=120, time_cache_file=None):
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValidationError("interval must be a finite positive number of seconds")
        if mode not in ("demo", "demo-db", "database", "hardware-read", "hardware-live", "standalone", "standalone-demo"):
            raise ValidationError("unknown service mode")
        if mode in ("hardware-read", "hardware-live", "standalone", "standalone-demo") and client is None:
            raise ValidationError("hardware-read requires an explicit physical read-only client")
        self.mode = mode
        self.source = "heating" if mode in ("hardware-read", "hardware-live", "standalone") else ("p4d-database" if mode == "database" else "simulator")
        self.can_write = mode in ("demo", "demo-db")
        self.fatal = Event()
        self.fatal_reason = None
        self.read_connection_verified = False
        self.max_cycle_seconds = max_cycle_seconds
        self.cycle_started = None
        self.watchdog = None
        self.repository = repository or MemoryRepository()
        self.client = None if mode == "database" else (client or HeatingClient(ProtocolSession(MemoryTransport())))
        self.worker = None if mode == "database" else HeatingWorker(queue_capacity)
        self.interval = interval
        self.job_limit = job_limit
        self.lock = Lock()
        self.cycle_lock = Lock()
        self.jobs = {}
        self.values = {}
        self.time_cache_file = time_cache_file
        self.time_items = []
        self.time_groups = ()
        self.time_observed_at = None
        self.time_refresh_job_id = None
        from .time_cache import load
        cached = load(time_cache_file)
        if cached:
            items, stamp = cached
            self.time_items = public(items)
            self.time_groups = items
            self.time_observed_at = stamp.isoformat()
        self.stop = Event()
        from .plant import PlantOverview
        self.plant = PlantOverview(self)
        self.collector = None
        self.collector_state = dict(enabled=mode != "database", interval_seconds=interval,
                                    running=False, last_cycle=None, last_successful_store=None,
                                    stored=0, errors=[], skipped=[], successful_cycles=0)
        if mode in ("hardware-read", "hardware-live"):
            self.watchdog = Thread(target=self._watch_cycles, name="test-watchdog", daemon=True)
            self.watchdog.start()
        if autostart and self.worker:
            self.collector = Thread(target=self._collect_loop, name="collector", daemon=True)
            self.collector.start()

    def abort(self, reason):
        with self.lock:
            if not self.fatal.is_set():
                self.fatal_reason = reason
                self.fatal.set()
        self.stop.set()

    def _watch_cycles(self):
        while not self.stop.wait(0.1):
            with self.lock:
                started = self.cycle_started
            if started is not None and time.monotonic() - started > self.max_cycle_seconds:
                self.abort("collector_deadline")

    def close(self):
        self.stop.set()
        self.plant.close()
        if self.watchdog:
            self.watchdog.join(timeout=1)
        if self.collector:
            self.collector.join(timeout=6)
        if self.worker:
            self.worker.close()
        if self.collector and self.collector.is_alive():
            self.collector.join(timeout=6)

    def collector_status(self):
        with self.lock:
            result = deepcopy(self.collector_state)
        historian = getattr(self.repository, 'historian', None)
        if historian:
            result['last_successful_store'] = historian.status()['last_success']
        return result

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
            self.cycle_started = time.monotonic()
        stored = 0
        try:
            sensors = self.repository.sensors()
            # Drop removed entries; retain last success of selected but failing sensors.
            selected = {(s["address"], s["type"]) for s in sensors
                        if s["state"] == "A" or s["record"] == "A"}
            if self.mode in ('standalone', 'standalone-demo'):
                selected = {(s['address'], s['type']) for s in sensors}
            with self.lock:
                self.values = {k: v for k, v in self.values.items() if k in selected}
            consecutive_protocol_errors = 0
            for sensor in sensors:
                if self.stop.is_set():
                    break
                mandatory_recording = automatic_recording(sensor, self.mode)
                if sensor["state"] != "A" and sensor["record"] != "A" and not mandatory_recording:
                    continue
                identity = dict(address=sensor["address"], type=sensor["type"])
                if sensor["type"] not in ("VA", "DO", "DI", "AO", "UD") or (
                        sensor["type"] == "UD" and sensor["address"] not in (1, 2, 3)):
                    skipped.append(dict(**identity, reason="unsupported"))
                    continue
                try:
                    sample = self._wait(self.worker.submit(lambda s=sensor: self.read_sensor(s)))
                    consecutive_protocol_errors = 0
                    observed_at = datetime.now(ZONE).isoformat()
                    with self.lock:
                        self.values[(sensor["address"], sensor["type"])] = public(dict(
                            **sample, observed_at=observed_at, source=self.source, origin="controller", unit=sensor["unit"], title=sensor.get("usrtitle") or sensor.get("title")))
                    if sensor["record"] == "A" or mandatory_recording:
                        samples.append(sample)
                except ServiceStopped:
                    break
                except Exception as exc:
                    errors.append(dict(**identity, error=failure(exc)))
                    if self.mode in ("standalone", "standalone-demo") and isinstance(exc, ProtocolError):
                        consecutive_protocol_errors += 1
                        if consecutive_protocol_errors >= 3:
                            break
                        continue  # The reconnecting client opens a clean session before the next read.
                    if self.mode in ("hardware-read", "hardware-live"):
                        if isinstance(exc, ProtocolError):
                            logging.getLogger(__name__).error("Heating read failed: %s", exc)
                        self.abort(type(exc).__name__)
                        break
            if samples and not self.stop.is_set():
                stamp = int(time.time())
                when = datetime.fromtimestamp(stamp, ZONE).replace(tzinfo=None)
                stored = self.repository.store_cycle(samples, when, stamp)
                if not hasattr(self.repository, "historian"):
                    with self.lock:
                        self.collector_state["last_successful_store"] = datetime.now(ZONE).isoformat()
        except Exception as exc:
            errors.append(dict(error=failure(exc)))
            if self.mode in ("hardware-read", "hardware-live"):
                self.abort(type(exc).__name__)
        finally:
            if hasattr(self.repository, 'remember_values'):
                try:
                    self.repository.remember_values(self.cached_values())
                except DatabaseUnavailable:
                    errors.append(dict(error=dict(code='local_storage_unavailable', message='latest values could not be persisted')))
            with self.lock:
                self.collector_state.update(running=False, stored=stored, errors=errors, skipped=skipped)
                self.cycle_started = None
                if (stored or self.mode in ("standalone", "standalone-demo")) and not errors:
                    self.collector_state["successful_cycles"] += 1
            self.cycle_lock.release()

    def _store_time_cache(self, items, stamp):
        from .time_cache import save
        try:
            save(self.time_cache_file, items, stamp)
        except OSError:
            logging.getLogger(__name__).error("Time-program cache could not be persisted")
        with self.lock:
            self.time_groups = tuple(items)
            self.time_items = public(items)
            self.time_observed_at = stamp

    def time_program_cache(self):
        with self.lock:
            stamp = self.time_observed_at
            return dict(available=stamp is not None, items=deepcopy(self.time_items),
                        observed_at=stamp, source=self.source,
                        age_seconds=max(0,(datetime.now(ZONE)-datetime.fromisoformat(stamp)).total_seconds()) if stamp else None,
                        refreshing=self.time_refresh_job_id is not None,
                        refresh_job_id=self.time_refresh_job_id)

    def _job_action(self, data):
        if not self.worker:
            raise ValidationError("controller operations unavailable in database mode")
        if not isinstance(data, dict) or not isinstance(data.get("operation"), str):
            raise ValidationError("job requires an operation")
        operation = data["operation"]
        if operation in ("write_parameter", "write_time_range") and (not self.can_write or operation not in getattr(self, "allowed_write_operations", ("write_parameter", "write_time_range"))):
            raise ReadOnlyViolation("heating writes are disabled in hardware modes")
        simple = {"status": self.client.get_status, "firmware": self.client.get_firmware,
                  "discover_menu": lambda: self.client.get_menu(timeout=10),
                  "time_ranges": lambda: self.client.get_time_ranges(timeout=10)}
        if operation in simple:
            if set(data) != {"operation"}:
                raise ValidationError("unexpected job fields")
            return simple[operation]
        if operation == "read_menu_value":
            from .menu import readable_menu
            if set(data) != {"operation", "menu_id"} or type(data["menu_id"]) is not int:
                raise ValidationError("menu-value read requires a menu_id")
            item = self.repository.menu_item(data["menu_id"])
            if not item or not readable_menu(item):
                raise ValidationError("menu item has no readable controller value")
            kind, address = item["type"], item["address"]
            if kind == 22:
                return lambda: dict(value=self.client.get_firmware().version_text, unit="")
            if kind in (3,70):
                sensor = next((s for s in self.repository.sensors() if s["type"] == "VA" and s["address"] == address), None)
                if not sensor:
                    raise ValidationError("measurement metadata unavailable")
                return lambda: dict(self.read_sensor(sensor), unit=sensor["unit"])
            if kind in (17,18,19):
                command = {17:Command.DIGITAL_OUT,18:Command.ANALOG_OUT,19:Command.DIGITAL_IN}[kind]
                def read_io():
                    value = self.client.get_io(address,command)
                    if kind == 18:
                        display = f"{value.state} ({'A' if value.mode == 255 else value.mode})"
                    else:
                        display = f"{'on' if value.state else 'off'} ({chr(value.mode)})"
                    return dict(value=value.state,mode=value.mode,display=display,unit="")
                return read_io
            def read_other_parameter():
                parameter = self.client.get_parameter(address)
                return dict(value=parameter.value,unit=parameter.unit)
            return read_other_parameter
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
        if self.fatal.is_set() or self.stop.is_set():
            raise ServiceStopped()
        if isinstance(data, dict) and data.get('operation') == 'refresh_component':
            return self.plant.submit(data)
        action = self._job_action(data)
        identifier = uuid.uuid4().hex
        with self.lock:
            if data["operation"] == "time_ranges" and self.time_refresh_job_id:
                return self.time_refresh_job_id
            if len(self.jobs) >= self.job_limit:
                oldest = next((k for k, v in self.jobs.items() if v["state"] in ("completed", "failed")), None)
                if oldest is None:
                    raise QueueBusy()
                del self.jobs[oldest]
            self.jobs[identifier] = dict(id=identifier, state="queued", operation=data["operation"],
                                         source=self.source, created_at=datetime.now(ZONE).isoformat())
            if data["operation"] == "time_ranges":
                self.time_refresh_job_id = identifier
        def execute():
            with self.lock:
                self.jobs[identifier]["state"] = "running"
            if data["operation"] in ("write_parameter", "write_time_range") and hasattr(self.repository, 'audit_write'):
                self.repository.audit_write(identifier, dict(state='attempting', request=data))
            return action()
        try:
            future = self.worker.submit(execute)
        except Exception:
            with self.lock:
                del self.jobs[identifier]
                if self.time_refresh_job_id == identifier:
                    self.time_refresh_job_id = None
            raise
        def complete(future):
            try:
                raw_result = future.result()
                result = public(raw_result)
                update = dict(state="completed", result=result)
                if data['operation'] in ('read_parameter', 'write_parameter'):
                    try:
                        self.plant.remember_parameter(data['menu_id'], raw_result if data['operation'] == 'read_parameter' else raw_result.current)
                    except DatabaseUnavailable:
                        logging.getLogger(__name__).warning('Plant parameter cache unavailable')
                if data["operation"] in ("write_parameter", "write_time_range") and hasattr(self.repository, 'audit_write'):
                    self.repository.audit_write(identifier, dict(state='completed', request=data, result=result))
                if data["operation"] == "time_ranges":
                    self._store_time_cache(raw_result, datetime.now(ZONE).isoformat())
                elif data["operation"] == "write_time_range":
                    with self.lock:
                        groups, stamp = self.time_groups, self.time_observed_at
                    if any(item.address == raw_result.current.address for item in groups):
                        updated = tuple(raw_result.current if item.address == raw_result.current.address else item for item in groups)
                        # Only one day was freshly verified; keep the full-list observation time.
                        self._store_time_cache(updated, stamp)
            except Exception as exc:
                update = dict(state="failed", error=failure(exc))
                if data["operation"] in ("write_parameter", "write_time_range") and hasattr(self.repository, 'audit_write'):
                    try:
                        self.repository.audit_write(identifier, dict(state='failed', request=data, error=failure(exc)))
                    except DatabaseUnavailable:
                        pass
                if self.mode in ("hardware-read", "hardware-live") and isinstance(exc, (ProtocolError, DatabaseUnavailable)):
                    if isinstance(exc, ProtocolError):
                        logging.getLogger(__name__).error("Heating read job failed: %s", exc)
                    self.abort(type(exc).__name__)
            with self.lock:
                self.jobs[identifier].update(update, finished_at=datetime.now(ZONE).isoformat())
                if self.time_refresh_job_id == identifier:
                    self.time_refresh_job_id = None
        future.add_done_callback(complete)
        return identifier

    def get_job(self, identifier):
        with self.lock:
            return deepcopy(self.jobs.get(identifier))
