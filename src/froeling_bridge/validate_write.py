"""Explicit, reversible hardware validation. Never called by normal startup or HTTP.

Requires the normal serial owner to be stopped. Simulation never issues a hardware proof.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path

from .client import HeatingClient
from .errors import ValidationError, WriteOutcomeUnknown, WriteVerificationError
from .host_test import atomic_json
from .local_store import LocalRepository
from .messages import ParameterType, TimeRange, parse_time
from .session import ProtocolSession
from .storage import ZONE


def validate_parameter(client, address, value, kind):
    before = client.get_parameter(address)
    # Validate both forward and restore inputs before attempting either write.
    if kind == ParameterType.BOOLEAN:
        restore_value = bool(before.raw_value)
    elif kind == ParameterType.TIME:
        restore_value = f"{before.raw_value // 60:02d}:{before.raw_value % 60:02d}"
    else:
        restore_value = before.value
    before.target_raw(restore_value, kind)
    target = before.target_raw(value, kind)
    if target == before.raw_value:
        raise ValidationError(
            "choose a different approved value so the hardware write path is exercised"
        )
    changed = client.set_parameter(address, value, kind, timeout=10)
    # Restore only after a fully confirmed forward write; never guess after outcome_unknown.
    restored = client.set_parameter(address, restore_value, kind, timeout=10)
    if restored.current.raw_value != before.raw_value:
        raise ValidationError("original parameter was not restored")
    return "write_parameter"


def validate_time(client, address, index, start, end):
    groups = client.get_time_ranges(timeout=30)
    group = next((g for g in groups if g.address == address), None)
    if (
        group is None
        or not 0 <= index <= 3
        or not isinstance(group.ranges[index], TimeRange)
    ):
        raise ValidationError(
            "validation requires a discovered, normally editable original interval"
        )
    target = TimeRange(
        parse_time(start) if start else None, parse_time(end) if end else None
    )
    previous = group.ranges[index]
    if target == previous:
        raise ValidationError("choose a different approved interval")
    client.set_time_range(address, index, target, timeout=30)
    client.set_time_range(address, index, previous, timeout=30)
    verified = next(
        g for g in client.get_time_ranges(timeout=30) if g.address == address
    )
    if verified.values_bytes() != group.values_bytes():
        raise ValidationError("original time-program group was not restored exactly")
    return "write_time_range"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Explicit chosen-value validation; normal heating services must be stopped"
    )
    parser.add_argument("--device")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--proof-file", required=True)
    parser.add_argument("--reply-profile")
    sub = parser.add_subparsers(dest="operation", required=True)
    parameter = sub.add_parser("parameter")
    parameter.add_argument("--address", type=lambda s: int(s, 0), required=True)
    parameter.add_argument("--value", required=True)
    parameter.add_argument(
        "--kind", choices=("number", "boolean", "time"), default="number"
    )
    ranges = sub.add_parser("time-range")
    ranges.add_argument("--address", type=lambda s: int(s, 0), required=True)
    ranges.add_argument("--index", type=int, required=True)
    ranges.add_argument("--start", required=True)
    ranges.add_argument("--end", required=True)
    args = parser.parse_args(argv)
    if not args.simulate and not args.device:
        raise ValidationError("select the physical device explicitly")
    if args.simulate and Path(args.proof_file).exists():
        raise ValidationError("simulation cannot replace a hardware proof")
    if args.simulate:
        from .simulator import MemoryTransport

        transport = MemoryTransport()
    else:
        from .serial_transport import SerialTransport

        transport = SerialTransport(args.device)
    profile = {}
    if args.reply_profile:
        profile = {
            int(k, 16): tuple(int(v, 16) for v in values)
            for k, values in json.loads(Path(args.reply_profile).read_text()).items()
        }
    client = HeatingClient(ProtocolSession(transport), reply_commands=profile)
    local = LocalRepository(Path(args.state_dir) / "catalogue.sqlite3")
    identifier = "validation-" + datetime.now(ZONE).strftime("%Y%m%dT%H%M%S%f")
    try:
        firmware = client.get_firmware().version_text
        local.audit_write(
            identifier,
            dict(state="attempting", operation=args.operation, address=args.address),
        )
        if args.operation == "parameter":
            kind = {
                "number": ParameterType.NUMBER,
                "boolean": ParameterType.BOOLEAN,
                "time": ParameterType.TIME,
            }[args.kind]
            value = args.value
            if kind == ParameterType.BOOLEAN:
                if value.lower() not in ("true", "false"):
                    raise ValidationError("boolean value must be true or false")
                value = value.lower() == "true"
            operation = validate_parameter(client, args.address, value, kind)
        else:
            operation = validate_time(
                client, args.address, args.index, args.start, args.end
            )
        local.audit_write(
            identifier,
            dict(state="restored", operation=operation, address=args.address),
        )
        proof = dict(
            validated=not args.simulate,
            device=args.device,
            firmware=firmware,
            operations=[operation],
            observed_at=datetime.now(ZONE).isoformat(),
        )
        path = Path(args.proof_file)
        if path.exists():
            old = json.loads(path.read_text())
            if (old.get("device"), old.get("firmware"), old.get("validated")) != (
                proof["device"],
                firmware,
                True,
            ):
                raise ValidationError("existing proof differs; preserved")
            proof["operations"] = sorted(set(old["operations"]) | {operation})
        atomic_json(path, proof, mode=0o640)
        print(
            "Change and restoration verified. "
            + (
                "Simulation only; no hardware authorization."
                if args.simulate
                else "Hardware validation record written; enable it explicitly in service configuration."
            )
        )
        return 0
    except Exception as exc:
        local.audit_write(
            identifier,
            dict(
                state="failed",
                error=type(exc).__name__,
                manual_readback_required=isinstance(
                    exc, (WriteOutcomeUnknown, WriteVerificationError)
                ),
            ),
        )
        print(
            "Validation did not complete. Do not repeat automatically; inspect and read back the chosen setting.",
            file=__import__("sys").stderr,
        )
        return 2
    finally:
        close = getattr(transport, "close", None)
        if close:
            close()


if __name__ == "__main__":
    raise SystemExit(main())
