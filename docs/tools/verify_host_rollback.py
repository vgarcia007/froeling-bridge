"""Real systemd rollback checks against uniquely named /bin/sleep spare units.

No references to the actual p4d unit, port or databases reach subprocesses.
"""

import json, os, subprocess, sys, tempfile, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if any(char in str(ROOT) for char in (" ", "%", "$")):
    raise SystemExit("Use a simple checkout path for systemd verification.")
sys.path.insert(0, str(ROOT / "src"))
from froeling_bridge.host_test import (
    Coordinator,
    System,
    P4D,
    TEST,
    TIMER,
    ROLLBACK,
    TestControlError,
)


class Spares(System):
    def __init__(self, base):
        self.base = base
        self.mapping = {
            P4D: base + "-original.service",
            TEST: base + "-test.service",
            TIMER: base + "-rollback.timer",
            ROLLBACK: base + "-rollback.service",
        }

    def run(self, command, **kwargs):
        mapped = [self.mapping.get(arg, arg) for arg in command]
        assert not set(mapped) & {P4D, TEST, TIMER, ROLLBACK}
        assert mapped[0] == "/usr/bin/systemctl"
        mapped[0] = "/bin/systemctl"
        return super().run(mapped, **kwargs)

    def preflight(self):
        if not self.active(P4D):
            raise TestControlError("spare original not active")

    def prepare_window(self, run_id):
        pass

    def device_free(self):
        return True

    def test_ready(self):
        if not self.active(TEST):
            raise TestControlError("spare test not ready")

    def capture(self):
        return {"successful_cycles": 5, "spare_units": True}

    def resumed_recording(self, after):
        return self.active(P4D)


if len(sys.argv) == 4 and sys.argv[1] == "rollback":
    result = Coordinator(Spares(sys.argv[2]), Path(sys.argv[3])).rollback()
    print(json.dumps(result))
    raise SystemExit(0)

if sys.argv[1:] != ["--run-local-spares"] or os.geteuid() != 0:
    raise SystemExit(
        "Run explicitly with sudo and --run-local-spares; only uniquely named spare units are changed."
    )
base = "froeling-bridge-spare-" + uuid.uuid4().hex[:10]
system = Spares(base)
with tempfile.TemporaryDirectory(prefix=base) as temporary:
    state = Path(temporary)
    units = Path("/run/systemd/system")
    created = []
    try:
        contents = {
            P4D: "[Service]\nExecStart=/bin/sleep infinity\n",
            TEST: "[Unit]\nOnFailure="
            + system.mapping[ROLLBACK]
            + "\n[Service]\nExecStart=/bin/sleep infinity\n",
            ROLLBACK: "[Service]\nType=oneshot\nExecStart="
            + str(ROOT / ".venv/bin/python")
            + " -I "
            + str(ROOT / "docs/tools/verify_host_rollback.py")
            + " rollback "
            + base
            + " "
            + str(state)
            + "\n",
            TIMER: "[Timer]\nOnActiveSec=2s\nAccuracySec=100ms\nUnit="
            + system.mapping[ROLLBACK]
            + "\n",
        }
        for unit, content in contents.items():
            path = units / system.mapping[unit]
            assert not path.exists()
            path.write_text(content)
            created.append(path)
        subprocess.run(["/bin/systemctl", "daemon-reload"], check=True)
        system.start(P4D)
        control = Coordinator(system, state)
        assert control.start()["phase"] == "running"
        # No active coordinator remains. Timer invokes a new process independently.
        for i in range(100):
            if control.read().get("phase") == "returned":
                break
            time.sleep(0.1)
        else:
            raise AssertionError("independent timer did not restore spare original")
        assert system.active(P4D) and not system.active(TEST)
        print(
            "PASS real systemd: independent timer restores spare original after coordinator exits"
        )
        # Abrupt test process failure, before the long timer, triggers OnFailure.
        system.stop(TIMER)
        timerpath = units / system.mapping[TIMER]
        timerpath.write_text(contents[TIMER].replace("2s", "60s"))
        subprocess.run(["/bin/systemctl", "daemon-reload"], check=True)
        control.start()
        subprocess.run(
            ["/bin/systemctl", "kill", "--signal=SIGKILL", system.mapping[TEST]],
            check=True,
        )
        for i in range(100):
            if control.read().get("phase") == "returned":
                break
            time.sleep(0.1)
        else:
            raise AssertionError("OnFailure did not restore spare original")
        assert system.active(P4D) and not system.active(TEST)
        print(
            "PASS real systemd: SIGKILL of spare test service triggers OnFailure rollback"
        )
    finally:
        for name in system.mapping.values():
            subprocess.run(
                ["/bin/systemctl", "stop", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        for path in created:
            path.unlink(missing_ok=True)
        subprocess.run(["/bin/systemctl", "daemon-reload"], check=True)
        for name in system.mapping.values():
            subprocess.run(
                ["/bin/systemctl", "reset-failed", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
