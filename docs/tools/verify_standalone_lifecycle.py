"""Real systemd checks using only uniquely named spare services and a fake ready HTTP endpoint."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from froeling_bridge import lifecycle as native

NAMES = (
    native.LIVE,
    native.GUARD,
    native.P4D,
    "froeling-bridge-rescue.service",
    "froeling-bridge-preview.service",
    "froeling-bridge-hardware-test.service",
    "froeling-bridge-rollback.timer",
)


class Spares(native.NativeSystem):
    def __init__(self, base):
        self.mapping = {
            name: base
            + "-"
            + str(i)
            + (".timer" if name.endswith(".timer") else ".service")
            for i, name in enumerate(NAMES)
        }

    def run(self, command, **kwargs):
        assert command[0] == "/usr/bin/systemctl"
        mapped = [self.mapping.get(arg, arg) for arg in command]
        assert not set(mapped) & set(NAMES)
        mapped[0] = "/bin/systemctl"
        if mapped[1] in ("enable", "disable"):
            mapped.insert(2, "--runtime")
        return super().run(mapped, **kwargs)

    def port_free(self, port):
        pass  # Test HTTP endpoint intentionally occupies its port.

    def free(self, device):
        assert device == "/dev/froeling-verification-only"
        return True


if len(sys.argv) == 5 and sys.argv[1] == "child":
    native.STATE = Path(sys.argv[3])
    native.control(sys.argv[4], Spares(sys.argv[2]))
    raise SystemExit(0)
if os.geteuid() != 0 or sys.argv[1:] != ["--run-local-spares"]:
    raise SystemExit(
        "Use sudo and --run-local-spares. Real heating services are never accessed."
    )


class Ready(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            b'{"phase":"ready","connection":{"connected":true},"catalogue_ready":true,"collector":{"successful_cycles":1}}'
        )

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), Ready)
Thread(target=server.serve_forever, daemon=True).start()
base = "froeling-independent-spare-" + uuid.uuid4().hex[:10]
system = Spares(base)
with tempfile.TemporaryDirectory(prefix=base) as temporary:
    native.STATE = Path(temporary)
    path = native.STATE / "installation.json"
    path.write_text(
        json.dumps(
            dict(
                p4d_fallback=True,
                p4d_enabled=True,
                device="/dev/froeling-verification-only",
                port=server.server_port,
            )
        )
    )
    created = []
    try:
        texts = {
            native.P4D: "[Service]\nExecStart=/bin/sleep infinity\n[Install]\nWantedBy=multi-user.target\n",
            native.LIVE: "[Unit]\nAfter="
            + native.P4D
            + "\nConflicts="
            + native.P4D
            + "\nOnFailure=froeling-bridge-rescue.service\n[Service]\nExecStart=/bin/sleep infinity\nRestart=no\nRestartSec=1\n[Install]\nWantedBy=multi-user.target\n",
            "froeling-bridge-rescue.service": "[Unit]\nAfter="
            + native.LIVE
            + "\n[Service]\nType=oneshot\nExecStart="
            + str(ROOT / ".venv/bin/python")
            + " -I "
            + str(Path(__file__).resolve())
            + " child "
            + base
            + " "
            + temporary
            + " rescue\n",
            native.GUARD: "[Timer]\nOnActiveSec=2s\nAccuracySec=100ms\nUnit=froeling-bridge-rescue.service\n",
        }
        for name in NAMES:
            texts.setdefault(
                name,
                (
                    "[Timer]\nOnActiveSec=1h\nUnit=froeling-bridge-rescue.service\n"
                    if name.endswith(".timer")
                    else "[Service]\nExecStart=/bin/sleep infinity\n"
                ),
            )
        for name, text in texts.items():
            for real, spare in system.mapping.items():
                text = text.replace(real, spare)
            file = Path("/run/systemd/system") / system.mapping[name]
            assert not file.exists()
            file.write_text(text)
            created.append(file)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        system.boot(native.P4D, True)
        system.start(native.P4D)
        assert native.control("start", system)["bridge_active"]
        system.run(["/usr/bin/systemctl", "kill", "--signal=SIGKILL", native.LIVE])
        for _ in range(100):
            if (
                system.active(native.P4D)
                and not system.active(native.LIVE)
                and system.enabled(native.P4D)
            ):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("native OnFailure fallback failed")
        print(
            "PASS native real systemd: fatal failure restores original p4d spare and boot selection."
        )
        # On a new host there is no original daemon: crash recovery must restart the bridge instead.
        state = json.loads(path.read_text())
        state["p4d_fallback"] = False
        path.write_text(json.dumps(state))
        system.stop(native.P4D)
        livepath = Path("/run/systemd/system") / system.mapping[native.LIVE]
        livepath.write_text(
            livepath.read_text().replace("Restart=no", "Restart=on-failure")
        )
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        system.start(native.LIVE)
        system.boot(native.LIVE, True)
        system.run(["/usr/bin/systemctl", "kill", "--signal=SIGKILL", native.LIVE])
        time.sleep(2)
        assert system.active(native.LIVE) and system.enabled(native.LIVE)
        assert not system.active(native.P4D)
        print(
            "PASS native real systemd: new-host failure restarts bridge without requiring p4d."
        )
    finally:
        for name in system.mapping.values():
            subprocess.run(["systemctl", "stop", name], capture_output=True)
            subprocess.run(
                ["systemctl", "disable", "--runtime", name], capture_output=True
            )
        for file in created:
            file.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        for name in system.mapping.values():
            subprocess.run(["systemctl", "reset-failed", name], capture_output=True)
        server.shutdown()
        server.server_close()
