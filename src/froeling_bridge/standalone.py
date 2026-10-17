"""Independent live runtime: discovery, reconnect and optional historian."""

from datetime import datetime
import logging
from pathlib import Path
from threading import Event, Lock, Thread
import time

from .client import HeatingClient, ReadOnlyHeatingClient
from .discovery import discover
from .errors import ProtocolError
from .local_store import LocalRepository
from .messages import Command
from .service import BridgeService, public
from .session import ProtocolSession
from .storage import ZONE

logger = logging.getLogger(__name__)


class ReconnectingClient:
    """Called only by the heating worker. Never replay the failed operation."""

    def __init__(self, factory):
        self.factory = factory
        self.inner = None
        self.close_transport = None
        self.state = dict(connected=False, last_success=None, error=None)
        self.lock = Lock()

    def __getattr__(self, name):
        if not name.startswith(("get_", "set_")):
            raise AttributeError(name)

        def call(*args, **kwargs):
            try:
                if self.inner is None:
                    self.inner, self.close_transport = self.factory()
                result = getattr(self.inner, name)(*args, **kwargs)
                with self.lock:
                    self.state.update(
                        connected=True,
                        last_success=datetime.now(ZONE).isoformat(),
                        error=None,
                    )
                return result
            except (ProtocolError, OSError):
                with self.lock:
                    self.state.update(
                        connected=False, error="heating connection failed"
                    )
                self.close()
                raise

        return call

    def status(self):
        with self.lock:
            return dict(self.state)

    def close(self):
        close = self.close_transport
        self.inner = self.close_transport = None
        if close:
            try:
                close()
            except OSError:
                pass


def serial_factory(device, profile=None, allow_writes=False):
    def factory():
        from .serial_transport import SerialTransport, ReadOnlyTransport

        transport = SerialTransport(device)
        if not allow_writes:
            transport = ReadOnlyTransport(transport)
        cls = HeatingClient if allow_writes else ReadOnlyHeatingClient
        return cls(ProtocolSession(transport), reply_commands=profile), transport.close

    return factory


class StandaloneRuntime:
    def __init__(
        self,
        state_dir,
        factory,
        *,
        interval=60,
        status_interval=10,
        allow_writes=False,
        simulator=False,
        database_config=None,
        initialize_history=False,
        autostart=True,
    ):
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.repository = LocalRepository(state_dir / "catalogue.sqlite3")
        if simulator:
            self.repository.source = "simulator-local-catalogue"
            if database_config:
                database_config.require_test()
        self.client = ReconnectingClient(factory)
        self.service = BridgeService(
            self.repository,
            mode="standalone-demo" if simulator else "standalone",
            interval=interval,
            client=self.client,
            autostart=False,
            time_cache_file=state_dir / "time-programs-cache.json",
        )
        self.service.can_write = allow_writes
        self.service.runtime = self
        self.service.values = {
            (r["address"], r["type"]): r for r in self.repository.latest_values()
        }
        self.phase = "starting"
        self.error = None
        self.last_failure = None
        self.stop = Event()
        self.status_interval = status_interval
        self.thread = None
        self.database_config = database_config
        self.initialize_history = initialize_history
        self.history_error = None
        self.persistence_error = None
        self.history_thread = None
        self.preferences_attempted = Event()
        if not database_config:
            self.preferences_attempted.set()
        if database_config:
            self.history_thread = Thread(
                target=self._history_setup, name="history-setup", daemon=True
            )
            self.history_thread.start()
        if autostart:
            self.thread = Thread(
                target=self._run, name="standalone-runtime", daemon=True
            )
            self.thread.start()

    def status(self):
        historian = self.repository.historian
        return dict(
            phase=self.phase,
            error=self.error,
            last_failure=self.last_failure,
            persistence_error=self.persistence_error,
            catalogue_recovered=self.repository.recovered,
            connection=self.client.status(),
            collector=self.service.collector_status(),
            controller_errors=self.controller_errors(),
            catalogue_ready=bool(self.repository.get_meta("discovered_at")),
            history=(
                historian.status()
                if historian
                else dict(
                    configured=bool(self.database_config),
                    available=False,
                    error=self.history_error,
                    stored=0,
                    pending_settings=len(self.repository.pending_changes()),
                )
            ),
        )

    def controller_errors(self):
        from .controller_errors import view
        return view(self.repository.get_meta("controller_errors"), self.service.interval)

    def errors_view(self, source="auto", limit=100, offset=0):
        from .controller_errors import check_page, page
        from .storage import ReadOnlyDatabase, DatabaseUnavailable
        check_page(limit, offset)
        if source not in ("auto", "history", "controller"):
            from .errors import ValidationError
            raise ValidationError("error source must be auto, history or controller")
        snapshot = self.controller_errors()
        configured = bool(self.database_config)
        snapshot.update(history_configured=configured, history_available=None,
                        history_error=None, fallback=False, read_at=None)
        historian = self.repository.historian
        snapshot["history_sync"] = historian.status().get("controller_errors") if historian else None
        if source != "controller" and configured:
            try:
                result = ReadOnlyDatabase(self.database_config).error_history(limit, offset)
                snapshot.update(result, source="p4d-database", available=True,
                                history_available=True, read_at=datetime.now(ZONE).isoformat())
                return snapshot
            except DatabaseUnavailable:
                if source == "history":
                    raise
                snapshot.update(history_available=False, fallback=True,
                                history_error="error history unavailable; showing controller memory only")
        elif source == "history":
            raise DatabaseUnavailable("error history database is not configured")
        items = snapshot["items"]
        snapshot.update(page(items[offset:offset + limit], len(items), limit, offset))
        return snapshot

    def _history_setup(self):
        from .history import initialize_database, Historian
        from .storage import P4dDatabase, ReadOnlyDatabase

        while not self.stop.is_set():
            try:
                if not self.repository.get_meta("preferences_imported"):
                    try:
                        original = ReadOnlyDatabase(self.database_config)
                        self.repository.import_preferences(original.sensors())
                    except Exception:
                        pass  # Empty/unavailable database must not block discovery.
                    else:
                        self.repository.set_meta("preferences_imported", True)
                    finally:
                        self.preferences_attempted.set()
                target = (
                    initialize_database(self.database_config, self.repository)
                    if self.initialize_history
                    else P4dDatabase(self.database_config, allow_recording=True)
                )
                target.validate_schema()
                if self.stop.is_set():
                    return
                historian = Historian(target, self.repository)
                self.repository.historian = historian
                self.history_error = None
                return
            except Exception:
                self.history_error = "history setup failed; check connection, schema and CREATE permissions"
                self.stop.wait(30)

    def discover_once(self):
        self.preferences_attempted.wait(10)

        def progress(stage):
            self.phase = "discovery:" + stage

        groups = self.service._wait(
            self.service.worker.submit(
                lambda: discover(self.client, self.repository, progress)
            )
        )
        self.service._store_time_cache(groups, datetime.now(ZONE).isoformat())
        self.service.read_connection_verified = True
        self.phase = "ready"
        self.error = None

    def refresh_status(self):
        status = self.service._wait(self.service.worker.submit(self.client.get_status))
        stamp = datetime.now(ZONE).isoformat()
        rows = []
        for address, value, text in (
            (1, status.state, status.state_text),
            (2, status.mode, status.mode_text),
        ):
            sensor = next(
                (
                    s
                    for s in self.repository.sensors()
                    if s["type"] == "UD" and s["address"] == address
                ),
                None,
            )
            if sensor:
                rows.append(
                    dict(
                        type="UD",
                        address=address,
                        value=str(value),
                        text=text,
                        unit=sensor["unit"],
                        title=sensor.get("usrtitle") or sensor["title"],
                        observed_at=stamp,
                        source=self.service.source,
                        origin="controller",
                    )
                )
        with self.service.lock:
            previous = self.service.values.get((1, "UD"), {}).get("value")
            for row in rows:
                self.service.values[(row["address"], row["type"])] = row
        try:
            self.repository.remember_values(rows)
            self.persistence_error = None
        except Exception:
            self.persistence_error = "latest values could not be persisted; readings remain in process memory"
        self.service.read_connection_verified = True
        return previous is not None and previous != str(status.state)

    def refresh_errors(self):
        from .controller_errors import events, merge_events
        previous = self.repository.get_meta("controller_errors", {})
        attempted = datetime.now(ZONE).isoformat()
        try:
            entries = self.service._wait(self.service.worker.submit(
                lambda: self.client.get_errors(timeout=30)))
            data = events(entries)
            merge_events(data)  # Reject unsupported interpretation before publishing/syncing.
            snapshot = dict(events=data, observed_at=datetime.now(ZONE).isoformat(),
                            last_attempt=attempted, error=None)
            self.repository.set_meta("controller_errors", snapshot)
        except Exception:
            previous.update(last_attempt=attempted, error="heating error memory could not be refreshed")
            self.repository.set_meta("controller_errors", previous)
            logger.warning("Heating error memory refresh failed; previous snapshot preserved")

    def _run(self):
        next_errors = 0
        next_values = next_status = 0
        failures = 0
        while not self.stop.is_set():
            try:
                if not self.repository.get_meta("discovered_at"):
                    self.discover_once()
                now = time.monotonic()
                changed = False
                if now >= next_status:
                    changed = self.refresh_status()
                    next_status = time.monotonic() + self.status_interval
                if now >= next_values or changed:
                    self.service.collect_once()
                    next_values = time.monotonic() + self.service.interval
                    # A broken transaction was not replayed; reconnect on the next status attempt.
                    if not self.client.status()["connected"]:
                        raise ProtocolError("connection lost during collection")
                if now >= next_errors or changed:
                    self.refresh_errors()
                    next_errors = time.monotonic() + self.service.interval
                self.phase, self.error, failures = "ready", None, 0
                self.stop.wait(
                    max(0.05, min(next_values, next_status) - time.monotonic())
                )
            except Exception as exc:
                failures += 1
                # Protocol errors contain bounded diagnostics generated by us.
                # Never expose arbitrary OS/SQLite/DB exception strings.
                detail = str(exc)[:300] if isinstance(exc, ProtocolError) else None
                self.last_failure = dict(
                    phase=self.phase,
                    error_type=type(exc).__name__,
                    detail=detail,
                    occurred_at=datetime.now(ZONE).isoformat(),
                )
                logger.warning(
                    "Heating worker failed during %s (%s)%s",
                    self.phase, type(exc).__name__,
                    ": " + detail if detail else "",
                )
                self.error = (
                    "heating/local storage unavailable; retrying read connection"
                )
                self.phase = "reconnecting"
                self.stop.wait(min(30, 2 ** min(failures - 1, 5)))

    def close(self):
        self.stop.set()
        self.service.close()
        if self.thread:
            self.thread.join(timeout=6)
        self.client.close()
        if self.history_thread:
            self.history_thread.join(timeout=6)
        if self.repository.historian:
            self.repository.historian.close()


def serve_standalone(args):
    import json
    import signal
    import os
    import stat
    from .errors import ValidationError
    from .storage import DatabaseConfig
    from .api import create_app
    from waitress import serve

    if not args.state_dir or not 1 <= args.port <= 65535:
        raise ValidationError("standalone requires --state-dir and port 1..65535")
    simulator = args.mode == "standalone-demo"
    allow_writes = simulator
    allowed_operations = (
        set(("write_parameter", "write_time_range")) if simulator else set()
    )
    validated_firmware = None
    if args.write_validation:
        if simulator:
            raise ValidationError("hardware validation is not used by the simulator")
        path = Path(args.write_validation)
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o022:
            raise ValidationError("hardware validation record must be protected")
        data = json.loads(path.read_text())
        if data.get("validated") is not True or data.get("device") != args.device:
            raise ValidationError(
                "hardware validation does not match the configured device"
            )
        validated_firmware = data.get("firmware")
        if not isinstance(validated_firmware, str) or not validated_firmware:
            raise ValidationError(
                "hardware validation requires an observed firmware version"
            )
        allowed_operations = set(data.get("operations", ()))
        if not allowed_operations or allowed_operations - {
            "write_parameter",
            "write_time_range",
        }:
            raise ValidationError("invalid hardware validation operations")
        allow_writes = True
    if simulator:
        from .simulator import MemoryTransport

        def factory():
            return HeatingClient(ProtocolSession(MemoryTransport())), lambda: None

    else:
        if not args.device:
            raise ValidationError("standalone requires --device")
        profile = {}
        if args.reply_profile:
            profile = {
                int(k, 16): tuple(int(c, 16) for c in v)
                for k, v in json.loads(Path(args.reply_profile).read_text()).items()
            }
        base_factory = serial_factory(args.device, profile, allow_writes)

        def factory():
            client, close = base_factory()
            if validated_firmware:
                try:
                    if client.get_firmware().version_text != validated_firmware:
                        raise ValidationError(
                            "controller firmware differs from the hardware validation record"
                        )
                except BaseException:
                    close()
                    raise
            return client, close

    if simulator and args.history_config:
        # Prevent fictional measurements from entering a production database.
        DatabaseConfig.load(args.history_config).require_test()
    runtime = StandaloneRuntime(
        args.state_dir,
        factory,
        interval=args.interval,
        allow_writes=allow_writes,
        simulator=simulator,
        database_config=(
            DatabaseConfig.load(args.history_config) if args.history_config else None
        ),
        initialize_history=True,
    )
    runtime.service.allowed_write_operations = allowed_operations
    previous = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, terminate)
    try:
        print(
            f"Fröling Bridge: {args.mode} on http://{args.host}:{args.port}", flush=True
        )
        serve(create_app(runtime.service), host=args.host, port=args.port, threads=4)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        runtime.close()
    return 0
