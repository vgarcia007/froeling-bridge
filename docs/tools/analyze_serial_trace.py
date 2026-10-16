#!/usr/bin/env python3
"""Summarize a private read-test trace without printing controller values."""
import argparse
from collections import Counter, deque
import json
from pathlib import Path

from froeling_bridge.codec import StreamDecoder


def analyze(path):
    if path.stat().st_size > 262144:
        raise ValueError("trace exceeds capture limit")
    decoders = {name: StreamDecoder() for name in ("TX", "RX")}
    counts = {name: Counter() for name in decoders}
    pending = deque()
    findings = []
    writes = 0
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        stamp, direction, encoded = line.split()
        float(stamp)
        if direction not in decoders:
            raise ValueError("invalid trace direction")
        frames = decoders[direction].feed(bytes.fromhex(encoded))
        for frame in frames:
            counts[direction][f"{frame.command:02X}"] += 1
            if direction == "TX":
                writes += frame.command in (0x39, 0x50, 0x54, 0x58, 0x59, 0x5A, 0x7E)
                pending.append(frame)
                continue
            if not pending:
                findings.append(
                    dict(
                        line=number,
                        problem="unsolicited_response",
                        received=f"{frame.command:02X}",
                    )
                )
                continue
            request = pending.popleft()
            if request.command != frame.command:
                findings.append(
                    dict(
                        line=number,
                        problem="reply_command",
                        expected=f"{request.command:02X}",
                        received=f"{frame.command:02X}",
                    )
                )
            if request.command == frame.command == 0x55 and len(frame.payload) >= 3:
                expected = int.from_bytes(request.payload, "big")
                received = int.from_bytes(frame.payload[1:3], "big")
                if expected != received:
                    findings.append(
                        dict(
                            line=number,
                            problem="parameter_address",
                            expected=f"{expected:04X}",
                            received=f"{received:04X}",
                        )
                    )
    return dict(
        commands={name: dict(values) for name, values in counts.items()},
        heating_write_frames=writes,
        findings=findings,
        unanswered=len(pending),
        partial_frames={
            name: decoder.has_partial for name, decoder in decoders.items()
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.trace), indent=2))
