"""Read-only hardware soak report. Polls cached HTTP state, never submits heating jobs."""

import argparse
from datetime import datetime, timezone
import json
import math
import uuid
import os
from pathlib import Path
import time
from urllib.request import build_opener, ProxyHandler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url", required=True, help="Bridge URL, e.g. http://SERVER-IP:8000"
    )
    parser.add_argument(
        "--report",
        required=True,
        help="private report file; no measurements or URL are included",
    )
    parser.add_argument("--seconds", type=float, default=86400)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("duration must be positive")
    opener = build_opener(ProxyHandler({}))

    def get(path):
        with opener.open(
            args.url.rstrip("/") + "/api/v1/" + path, timeout=5
        ) as response:
            return json.load(response)

    report = dict(
        started_at=datetime.now(timezone.utc).isoformat(),
        requested_seconds=args.seconds,
        elapsed_seconds=0,
        completed=False,
        healthy_polls=0,
        failed_polls=0,
        history_warning_polls=0,
        last_failure=None,
        last_poll=None,
    )
    target = Path(args.report)
    if target.exists():
        parser.error("existing report preserved; choose a new report filename")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save():
        temporary = target.with_name(target.name + ".new-" + uuid.uuid4().hex)
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(report, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    started = time.monotonic()
    try:
        while True:
            try:
                health = get("health")
                runtime = get("runtime")
                sensors = get("sensors")["items"]
                selected = [
                    s
                    for s in sensors
                    if s["supported"] and (s["active"] or s["recording"])
                ]
                measurements = [s for s in selected if s["type"] == "VA"]
                fresh = [
                    s
                    for s in measurements
                    if s["latest"]
                    and not s["latest"]["stale"]
                    and s["latest"]["origin"] == "controller"
                ]
                healthy = (
                    health["mode"] == "standalone"
                    and runtime["phase"] == "ready"
                    and runtime["connection"]["connected"]
                    and fresh
                    and not health["fatal_reason"]
                )
                if not healthy:
                    raise ValueError(
                        "hardware mode, connection or fresh measurement missing"
                    )
                report["healthy_polls"] += 1
                history = runtime["history"]
                if history["configured"] and not history["available"]:
                    report["history_warning_polls"] += 1
                report["last_poll"] = dict(
                    at=datetime.now(timezone.utc).isoformat(),
                    fresh_measurements=len(fresh),
                    stale_or_missing_selected=sum(
                        not s["latest"] or s["latest"]["stale"] for s in selected
                    ),
                    successful_cycles=runtime["collector"]["successful_cycles"],
                )
            except Exception as exc:
                report["failed_polls"] += 1
                report["last_failure"] = dict(
                    at=datetime.now(timezone.utc).isoformat(), kind=type(exc).__name__
                )
            report["elapsed_seconds"] = round(time.monotonic() - started, 1)
            report["completed"] = report["elapsed_seconds"] >= args.seconds
            save()
            if report["completed"]:
                break
            time.sleep(min(10, max(0.01, args.seconds - (time.monotonic() - started))))
    except KeyboardInterrupt:
        report["elapsed_seconds"] = round(time.monotonic() - started, 1)
        save()
    print(json.dumps(report, indent=2))
    return 0 if report["completed"] and not report["failed_polls"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
