"""Fixed root lifecycle for continuous recording in the existing p4d database."""
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import stat
import sys
import time
from urllib.request import build_opener, ProxyHandler

from .host_test import System, TestControlError, locked, atomic_json, P4D, TEST, TIMER, ROLLBACK, DEVICE, CONFIG, STATE
from .storage import DatabaseConfig, P4dDatabase, ZONE

LIVE = "froeling-bridge.service"
GUARD = "froeling-bridge-activation.timer"
PREVIEW = "froeling-bridge-preview.service"


class ProductionSystem(System):
    def enable(self, unit):
        self.run(["/usr/bin/systemctl", "enable", unit])

    def disable(self, unit):
        self.run(["/usr/bin/systemctl", "disable", unit])

    def preflight_live(self):
        if any(self.active(unit) for unit in (TEST, TIMER, ROLLBACK, "froeling-bridge-fallback.service")):
            raise TestControlError("finish the hardware test before going live")
        if not self.active(P4D) or not self.enabled(P4D):
            raise TestControlError("original p4d must be running and enabled before activation")
        if not os.path.exists(DEVICE) or not stat.S_ISCHR(os.stat(DEVICE).st_mode):
            raise TestControlError("heating adapter unavailable")
        self.device_free()  # Check fuser availability before stopping p4d.
        repo = P4dDatabase(DatabaseConfig.load(CONFIG / "source-db.json"), allow_recording=True)
        repo.validate_schema()  # Read-only inspection, no initialization or migration.
        if not any(s["record"] == "A" and s["type"] in ("VA", "UD", "DO", "DI", "AO") for s in repo.sensors()):
            raise TestControlError("no supported recorded sensors")

    def http(self, route):
        opener = build_opener(ProxyHandler({}))
        with opener.open("http://127.0.0.1:8000/api/v1/" + route, timeout=2) as response:
            return json.load(response)

    def live_ready(self, after):
        deadline = time.monotonic() + 150
        repo = P4dDatabase(DatabaseConfig.load(CONFIG / "source-db.json"), allow_recording=True)
        sensor = next(s for s in repo.sensors() if s["record"] == "A" and s["type"] == "VA")
        while time.monotonic() < deadline:
            if not self.active(LIVE):
                raise TestControlError("live service stopped during activation")
            try:
                health, collector = self.http("health"), self.http("collector")
                if health.get("fatal_reason") or collector.get("errors"):
                    raise TestControlError("live collection failed during activation")
                if health.get("mode") == "hardware-live" and collector.get("successful_cycles", 0) >= 2:
                    with repo.transaction() as cursor:
                        cursor.execute("SELECT time FROM samples WHERE address=%s AND type=%s AND aggregate='S' AND time>=%s ORDER BY time DESC LIMIT 1", (sensor["address"], sensor["type"], after))
                        if cursor.fetchone():
                            return collector
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise TestControlError("live recording did not become ready")

    def port_free(self):
        with socket.socket() as sock:
            try:
                sock.bind(("0.0.0.0", 8000))
            except OSError:
                raise TestControlError("HTTP port 8000 is occupied") from None


class Production:
    def __init__(self, system, state_dir=STATE):
        self.system = system
        self.path = state_dir / "production.json"

    def write(self, phase, **details):
        atomic_json(self.path, dict(phase=phase, observed_at=datetime.now(ZONE).isoformat(), **details))

    def status(self):
        return dict(live_active=self.system.active(LIVE), live_enabled=self.system.enabled(LIVE),
                    p4d_active=self.system.active(P4D), p4d_enabled=self.system.enabled(P4D),
                    activation_guard=self.system.active(GUARD))

    def start(self):
        if self.system.active(LIVE):
            return self.status()
        self.system.preflight_live()
        self.write("activating")
        self.system.stop(GUARD)
        self.system.start(GUARD)
        if not self.system.active(GUARD):
            raise TestControlError("activation fallback not armed")
        try:
            self.system.stop(PREVIEW)
            self.system.port_free()
            self.system.stop(TIMER)
            self.system.stop(P4D)
            if self.system.active(P4D) or not self.system.device_free():
                raise TestControlError("serial device not released")
            after = datetime.now(ZONE).replace(tzinfo=None, microsecond=0)
            self.system.disable(P4D)
            self.system.enable(LIVE)
            self.system.start(LIVE)
            collector = self.system.live_ready(after)
            self.write("running", collector=collector)
            self.system.stop(GUARD)
            return self.status()
        except BaseException:
            self.rollback()
            raise

    def rollback(self):
        self.write("restoring")
        self.system.stop(LIVE)
        self.system.stop(TEST)
        self.system.disable(LIVE)
        if not self.system.active(P4D) and not self.system.device_free():
            raise TestControlError("serial device still occupied; p4d not started concurrently")
        after = datetime.now(ZONE).replace(tzinfo=None, microsecond=0)
        self.system.enable(P4D)
        self.system.start(P4D)
        resumed = self.system.resumed_recording(after)
        self.system.stop(GUARD)
        self.system.stop(TIMER)
        self.write("returned" if resumed else "returned_without_recording_confirmation", recording_resumed=resumed)
        if not resumed:
            raise TestControlError("p4d started but recording not yet confirmed")
        return self.status()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if os.geteuid() != 0 or len(args) != 1 or args[0] not in ("start", "rollback", "status"):
        print("Use the installed root helper with start, rollback or status.", file=sys.stderr)
        return 2
    try:
        with locked():
            control = Production(ProductionSystem())
            result = getattr(control, args[0])()
            print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(str(exc) if isinstance(exc, TestControlError) else "production control failed; inspect service journal", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
