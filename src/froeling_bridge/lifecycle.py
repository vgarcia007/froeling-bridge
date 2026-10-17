"""Root-only fixed native-service actions, including optional original-p4d fallback."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

from .host_test import System, TestControlError, atomic_json

LIVE = "froeling-bridge.service"
GUARD = "froeling-bridge-startup.timer"
P4D = "p4d.service"
STATE = Path("/var/lib/froeling-bridge-installer")


class NativeSystem(System):
    def enabled(self, unit):
        return (
            self.run(
                ["/usr/bin/systemctl", "is-enabled", "--quiet", unit],
                accepted=(0, 1, 3, 4),
            ).returncode
            == 0
        )

    def boot(self, unit, enabled):
        self.run(["/usr/bin/systemctl", "enable" if enabled else "disable", unit])

    def port_free(self, port):
        import socket

        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                raise TestControlError(
                    "HTTP port is occupied; original heating service not stopped"
                ) from None

    def free(self, device):
        binary = "/usr/bin/fuser" if Path("/usr/bin/fuser").exists() else "/bin/fuser"
        result = self.run([binary, device], accepted=(0, 1))
        if result.returncode == 1 and result.stderr.strip():
            raise TestControlError("cannot determine serial device owner")
        return result.returncode == 1


def control(action, system=None):
    system = system or NativeSystem()
    state = json.loads((STATE / "installation.json").read_text())
    if action == "status":
        return dict(
            bridge_active=system.active(LIVE),
            p4d_active=system.active(P4D),
            bridge_enabled=system.enabled(LIVE),
            startup_guard=system.active(GUARD),
        )
    if action == "rescue":
        if not state["p4d_fallback"]:
            return control("status", system)
        action = "rollback"
    if action == "rollback":
        system.stop(LIVE)
        system.boot(LIVE, False)
        if state["p4d_fallback"]:
            if not system.active(P4D) and not system.free(state["device"]):
                raise TestControlError(
                    "serial port still occupied; original not started concurrently"
                )
            system.boot(P4D, state["p4d_enabled"])
            system.start(P4D)
        system.stop(GUARD)
        return control("status", system)
    if action != "start":
        raise TestControlError("unsupported native service action")
    if system.active(LIVE):
        return control("status", system)
    if system.active("froeling-bridge-preview.service"):
        system.stop("froeling-bridge-preview.service")
    system.port_free(state["port"])
    system.free(state["device"])  # Validate fuser while the original is still running.
    # Only an original installation needs an independent restoration deadline.
    if state["p4d_fallback"]:
        system.stop(GUARD)
        system.start(GUARD)
        if not system.active(GUARD):
            raise TestControlError("startup guard not armed")
    try:
        if system.active(P4D):
            system.stop(P4D)
        if not system.free(state["device"]):
            raise TestControlError("serial adapter is already owned by another process")
        for unit in (
            "froeling-bridge-preview.service",
            "froeling-bridge-hardware-test.service",
            "froeling-bridge-rollback.timer",
        ):
            if system.active(unit):
                system.stop(unit)
        if state["p4d_fallback"]:
            system.boot(P4D, False)
        system.boot(LIVE, True)
        system.start(LIVE)
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 700
        while time.monotonic() < deadline:
            if not system.active(LIVE):
                raise TestControlError("bridge stopped during startup")
            try:
                with opener.open(
                    f"http://127.0.0.1:{state['port']}/api/v1/runtime", timeout=2
                ) as response:
                    runtime = json.load(response)
                if (
                    runtime["phase"] == "ready"
                    and runtime["connection"]["connected"]
                    and runtime["catalogue_ready"]
                    and runtime.get("collector", {}).get("successful_cycles", 0) >= 1
                ):
                    system.stop(GUARD)
                    return control("status", system)
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise TestControlError("discovery/connection startup deadline exceeded")
    except BaseException:
        if state["p4d_fallback"]:
            control("rollback", system)
        raise


def main():
    import fcntl

    if os.geteuid() != 0 or sys.argv[1:] not in (
        ["start"],
        ["rollback"],
        ["status"],
        ["rescue"],
    ):
        print("Use installed helper: start, rollback or status.", file=sys.stderr)
        return 2
    try:
        with open(STATE / "control.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(control(sys.argv[1]), indent=2))
        return 0
    except Exception as exc:
        print(
            (
                str(exc)
                if isinstance(exc, TestControlError)
                else "native lifecycle operation failed; inspect service journal"
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
