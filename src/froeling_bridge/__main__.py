"""Offline protocol tools and local simulator/database API. No TTY access."""
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
    parser = argparse.ArgumentParser(description="Fröling Bridge: protocol tools, simulator collector and local API (no hardware access)")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="read and change fictional in-memory controller data")
    encoder = commands.add_parser("encode", help="encode a frame without sending it")
    encoder.add_argument("command_hex", help="hex command, for example 55")
    encoder.add_argument("payload_hex", nargs="?", default="", help="hex payload, for example '12 34'")
    decoder = commands.add_parser("decode", help="validate and decode exactly one hex frame")
    decoder.add_argument("wire_hex")
    server = commands.add_parser("serve", help="run local API and simulated collector")
    server.add_argument("--mode", choices=("demo", "demo-db", "database"), default="demo")
    server.add_argument("--config", help="local JSON database configuration")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--interval", type=float, default=60)
    setup = commands.add_parser("init-test-db", help="initialize an empty loopback test database")
    setup.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    try:
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
    try:
        from .storage import DatabaseConfig, ReadOnlyDatabase, TestDatabase
        if args.command == "init-test-db":
            from .testdb import initialize
            config = DatabaseConfig.load(args.config)
            config.require_test()
            initialize(config)
            print("Synthetic test database initialized.")
            return 0
        from .api import create_app
        from .service import BridgeService
        from waitress import serve
        if not 1 <= args.port <= 65535:
            raise ValidationError("port must be 1..65535")
        if args.mode == "demo":
            if args.config:
                raise ValidationError("demo mode does not use a database configuration")
            repository = None
        else:
            if not args.config:
                raise ValidationError("database mode requires --config")
            config = DatabaseConfig.load(args.config)
            repository = TestDatabase(config) if args.mode == "demo-db" else ReadOnlyDatabase(config)
        service = BridgeService(repository, args.mode, args.interval)
        try:
            print(f"Fröling Bridge: {args.mode} on http://127.0.0.1:{args.port}", flush=True)
            import signal
            previous = signal.getsignal(signal.SIGTERM)
            def terminate(signum, frame):
                raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM, terminate)
            try:
                serve(create_app(service), host="127.0.0.1", port=args.port, threads=4)
            finally:
                signal.signal(signal.SIGTERM, previous)
        finally:
            service.close()
        return 0
    except ImportError:
        print('Service dependencies missing; install with pip install ".[service]"', file=sys.stderr)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Service/database operation failed; check local configuration and database availability.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
