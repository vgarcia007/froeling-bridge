"""Protocol tools and local web service; TTY access only in explicit hardware modes."""
import argparse
from dataclasses import asdict
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
import json
import sys

from . import __version__
from .client import HeatingClient
from .codec import Frame, decode_frame, encode_frame
from .errors import ProtocolError, ValidationError
from .messages import TimeRange
from .session import ProtocolSession
from .simulator import MemoryTransport


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex(" ").upper()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def demo():
    transport = MemoryTransport(read_chunk_size=1, max_write=2)
    client = HeatingClient(ProtocolSession(transport))
    status = client.get_status()
    specs = client.get_value_specs()
    measurements = [dict(address=f"0x{spec.address:04X}",
                         value=client.get_measurement(spec.address, spec.factor, spec.data_type),
                         unit=spec.unit) for spec in specs]
    menu = client.get_menu()
    before = client.get_parameter(0x1234)
    change = client.set_parameter(0x1234, Decimal("67.5"))
    times = client.set_time_range(0x38, 1, TimeRange(time(12), time(13)))
    return {
        "mode": "offline-simulator", "hardware_verified": False,
        "status": asdict(status), "firmware": asdict(client.get_firmware()),
        "measurements": measurements,
        "menu": [dict(type=item.item_type, parent=item.parent, child=item.child,
                      address=f"0x{item.address:04X}", title=item.description) for item in menu],
        "parameter_change": dict(address="0x1234", before=before.value,
                                 after=change.current.value, status=change.status),
        "time_program_change": dict(address="0x38", status=times.status,
                                    intervals=[asdict(r) for r in times.current.ranges]),
        "errors": [asdict(item) for item in client.get_errors()],
        "requests_sent_to_simulator": len(transport.requests),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fröling Bridge: protocol tools, collector, web menu and API")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="read and change fictional in-memory controller data")
    encoder = commands.add_parser("encode", help="encode a frame without sending it")
    encoder.add_argument("command_hex", help="hex command, for example 55")
    encoder.add_argument("payload_hex", nargs="?", default="", help="hex payload, for example '12 34'")
    decoder = commands.add_parser("decode", help="validate and decode exactly one hex frame")
    decoder.add_argument("wire_hex")
    server = commands.add_parser("serve", help="run web API and selected collector")
    server.add_argument("--mode", choices=("demo", "demo-db", "database", "hardware-read", "hardware-live", "standalone", "standalone-demo"), default="demo")
    server.add_argument("--config", help="local JSON database configuration")
    server.add_argument("--test-config", help="separate loopback test database (hardware-read only)")
    server.add_argument("--device", help="exclusive TTY device (hardware-read only)")
    server.add_argument("--trace-file", help="new private raw trace file (hardware-read only)")
    server.add_argument("--reply-profile", help="explicit JSON request-to-reply command mapping")
    server.add_argument("--state-dir", help="private persistent state directory (standalone modes)")
    server.add_argument("--history-config", help="optional MariaDB configuration; empty DB initialized automatically")
    server.add_argument("--write-validation", help="explicit hardware validation record for enabling heating writes")
    server.add_argument("--time-cache-file", help="persistent controller time cache")
    server.add_argument("--host", default="0.0.0.0", help="listen address (default: all IPv4 interfaces)")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--interval", type=float, default=60)
    setup = commands.add_parser("init-test-db", help="initialize an empty loopback test database")
    setup.add_argument("--config", required=True)
    setup.add_argument("--empty", action="store_true", help="create empty tables without simulator fixtures")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve" and args.mode in ("standalone", "standalone-demo"):
            from .standalone import serve_standalone
            return serve_standalone(args)
        if args.command in ("serve", "init-test-db"):
            return run_service(args)
        if args.command == "demo":
            print(json.dumps(demo(), default=json_value, ensure_ascii=False, indent=2))
        elif args.command == "encode":
            frame = Frame(int(args.command_hex, 16), bytes.fromhex(args.payload_hex))
            print(encode_frame(frame).hex(" ").upper())
        else:
            frame = decode_frame(bytes.fromhex(args.wire_hex))
            print(json.dumps(dict(command=f"{frame.command:02X}", payload=frame.payload.hex(" ").upper())))
    except (ProtocolError, ValidationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


def run_service(args):
    transport = None
    service = None
    try:
        from .storage import DatabaseConfig, ReadOnlyDatabase, TestDatabase, HardwareTestRepository, P4dDatabase
        if args.command == "init-test-db":
            from .testdb import initialize
            config = DatabaseConfig.load(args.config)
            config.require_test()
            initialize(config, seed=not args.empty)
            print("Synthetic test database initialized.")
            return 0
        from .api import create_app
        from .service import BridgeService
        from waitress import serve
        if not 1 <= args.port <= 65535:
            raise ValidationError("port must be 1..65535")
        if args.mode not in ("hardware-read", "hardware-live") and any((args.test_config, args.device, args.trace_file, args.reply_profile)):
            raise ValidationError("hardware options require hardware-read or hardware-live mode")
        client = None
        if args.mode in ("hardware-read", "hardware-live"):
            if not args.config or not args.device:
                raise ValidationError("hardware mode requires configuration and device")
            if args.mode == "hardware-read":
                if not args.test_config or not args.trace_file:
                    raise ValidationError("hardware-read requires test configuration and trace file")
                original = ReadOnlyDatabase(DatabaseConfig.load(args.config))
                target = TestDatabase(DatabaseConfig.load(args.test_config))
                repository = HardwareTestRepository(original, target)
                repository.sensors()
                target.history(0, "VA", datetime(2000, 1, 1), datetime(2000, 1, 2), limit=1)
            else:
                if args.test_config:
                    raise ValidationError("hardware-live records in the configured original database")
                repository = P4dDatabase(DatabaseConfig.load(args.config), allow_recording=True)
                repository.validate_schema()
            from .serial_transport import SerialTransport, TraceTransport, ReadOnlyTransport
            from .client import ReadOnlyHeatingClient
            transport = SerialTransport(args.device)
            if args.trace_file:
                transport = TraceTransport(transport, args.trace_file)
            transport = ReadOnlyTransport(transport)
            profile = {}
            if args.reply_profile:
                with open(args.reply_profile, encoding="utf-8") as stream:
                    profile = {int(k, 16): tuple(int(v, 16) for v in values) for k, values in json.load(stream).items()}
            client = ReadOnlyHeatingClient(ProtocolSession(transport), reply_commands=profile)
            client.get_status()
            client.get_firmware()
        elif args.mode == "demo":
            if args.config:
                raise ValidationError("demo mode does not use a database configuration")
            repository = None
        else:
            if not args.config:
                raise ValidationError("database mode requires --config")
            config = DatabaseConfig.load(args.config)
            repository = TestDatabase(config) if args.mode == "demo-db" else ReadOnlyDatabase(config)
        from pathlib import Path
        time_cache_file = Path(args.time_cache_file) if args.time_cache_file else (Path(args.trace_file).parent / "time-programs-cache.json" if args.trace_file else None)
        service = BridgeService(repository, args.mode, args.interval, client=client, time_cache_file=time_cache_file)
        service.read_connection_verified = args.mode in ("hardware-read", "hardware-live")
        try:
            print(f"Fröling Bridge: {args.mode} on http://{args.host}:{args.port}", flush=True)
            import signal
            previous = signal.getsignal(signal.SIGTERM)
            def terminate(signum, frame):
                raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM, terminate)
            try:
                if args.mode in ("hardware-read", "hardware-live"):
                    import os
                    from threading import Thread
                    def abort_test():
                        service.fatal.wait()
                        if service.fatal.is_set():
                            os.kill(os.getpid(), signal.SIGTERM)
                    Thread(target=abort_test, name="fatal-exit", daemon=True).start()
                serve(create_app(service), host=args.host, port=args.port, threads=4)
            finally:
                signal.signal(signal.SIGTERM, previous)
        finally:
            service.close()
        return 2 if service and service.fatal.is_set() else 0
    except ImportError:
        print('Service dependencies missing; install with pip install ".[service]"', file=sys.stderr)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        return 2 if service and service.fatal.is_set() else 0
    except Exception:
        print("Service/database operation failed; check local configuration and database availability.", file=sys.stderr)
    finally:
        if service is not None:
            service.close()
        if transport is not None:
            transport.close()
        if service is not None and args.trace_file and args.mode in ("hardware-read", "hardware-live"):
            # Keep a private summary even when OnFailure runs after HTTP exits.
            import os
            summary = dict(fatal_reason=service.fatal_reason, collector=service.collector_status())
            try:
                fd = os.open(args.trace_file + ".result.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as stream:
                    json.dump(summary, stream)
            except OSError:
                pass
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
