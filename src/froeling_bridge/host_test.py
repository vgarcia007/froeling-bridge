"""Fixed-action root coordinator for the temporary, read-only host test.

Invoked through an immutable /usr/local/sbin wrapper, never through HTTP.
Commands, paths and duration are fixed. Only local test state is written.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
import fcntl
import json
import os
import pwd
from pathlib import Path
import socket
import subprocess
import sys
import stat
import time
import uuid

from .storage import DatabaseConfig, ReadOnlyDatabase, TestDatabase, ZONE

P4D = "p4d.service"
TEST = "froeling-bridge-hardware-test.service"
TIMER = "froeling-bridge-rollback.timer"
ROLLBACK = "froeling-bridge-rollback.service"
DEVICE = "/dev/ttyUSB0"
CONFIG = Path("/etc/froeling-bridge-test")
STATE = Path("/var/lib/froeling-bridge-coordinator")
TEST_STATE = Path("/var/lib/froeling-bridge-test")
DURATION = 900


class TestControlError(Exception):
    pass


def atomic_json(path, data, mode=0o600, group=None):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if group is not None:
            os.chown(temporary, 0, group)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_report(path):
    """Read an unprivileged diagnostic file without following symlinks."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size >= 262144:
                return {}
            data = json.loads(stream.read(262144))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class System:
    def run(self, command, timeout=40, accepted=(0,)):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "LC_ALL": "C.UTF-8",
                    "HOME": pwd.getpwuid(os.geteuid()).pw_dir,
                },
            )
        except (OSError, subprocess.TimeoutExpired):
            raise TestControlError(
                "system operation unavailable or timed out"
            ) from None
        if result.returncode not in accepted:
            raise TestControlError("system operation failed")
        return result

    def docker(self, *arguments):
        binary = next(
            (
                path
                for path in ("/usr/bin/docker", "/snap/bin/docker")
                if os.path.isfile(path)
            ),
            None,
        )
        if binary is None:
            raise TestControlError("Docker client unavailable")
        return self.run([binary, "--host", "unix:///var/run/docker.sock", *arguments])

    def active(self, unit):
        return (
            self.run(
                ["/usr/bin/systemctl", "is-active", "--quiet", unit], accepted=(0, 3, 4)
            ).returncode
            == 0
        )

    def enabled(self, unit):
        return (
            self.run(
                ["/usr/bin/systemctl", "is-enabled", "--quiet", unit], accepted=(0, 1)
            ).returncode
            == 0
        )

    def start(self, unit):
        self.run(["/usr/bin/systemctl", "start", unit])

    def stop(self, unit):
        self.run(["/usr/bin/systemctl", "stop", unit])

    def arm(self):
        # Reset the installed monotonic timer on every new window.
        self.stop(TIMER)
        self.start(TIMER)
        if not self.active(TIMER):
            raise TestControlError("rollback timer not active")
        value = self.run(
            [
                "/usr/bin/systemctl",
                "show",
                TIMER,
                "--property=NextElapseUSecMonotonic",
                "--value",
            ]
        ).stdout.strip()
        if value in ("", "0", "infinity"):
            raise TestControlError("rollback deadline not scheduled")

    def device_free(self):
        if not os.path.exists(DEVICE):
            return True  # No new open can compete if the adapter was unplugged.
        result = self.run(["/usr/bin/fuser", "--", DEVICE], accepted=(0, 1))
        if result.returncode == 1 and result.stderr.strip():
            raise TestControlError("could not determine device holders")
        return result.returncode == 1

    def preflight(self):
        if not self.active(P4D) or not self.enabled(P4D):
            raise TestControlError(
                "p4d must be running with its original autostart enabled"
            )
        if (
            self.active(TEST)
            or not os.path.exists(DEVICE)
            or not stat.S_ISCHR(os.stat(DEVICE).st_mode)
        ):
            raise TestControlError("hardware test already running or device missing")
        with socket.socket() as sock:
            try:
                sock.bind(("0.0.0.0", 8001))
            except OSError:
                raise TestControlError("test HTTP port unavailable") from None
        # Original is only read. The destination is a fresh empty test schema.
        source = ReadOnlyDatabase(DatabaseConfig.load(CONFIG / "source-db.json"))
        sensors = source.sensors()
        source.menu(1)
        if not any(
            s["record"] == "A" and s["type"] in ("VA", "UD", "DO", "DI", "AO")
            for s in sensors
        ):
            raise TestControlError("no supported recorded sensors selected")
        target = DatabaseConfig.load(CONFIG / "test-db.json")
        target.require_test()
        if target.host != "127.0.0.1" or target.port != 33079:
            raise TestControlError("unexpected test database endpoint")
        container = self.docker("inspect", "froeling-bridge-test-db").stdout
        info = json.loads(container)[0]
        if (
            info["Config"].get("Labels", {}).get("org.froeling-bridge.role")
            != "hardware-test"
        ):
            raise TestControlError("test database container ownership does not match")
        bindings = info["NetworkSettings"]["Ports"].get("3306/tcp")
        if bindings != [{"HostIp": "127.0.0.1", "HostPort": "33079"}]:
            raise TestControlError("test database binding does not match")

    def prepare_window(self, run_id):
        from .testdb import initialize
        import grp

        target = DatabaseConfig.load(CONFIG / "test-db.json")
        target = replace(target, database="froeling_bridge_test_" + run_id)
        initialize(target, seed=False)
        atomic_json(
            CONFIG / "test-db.json",
            dict(
                database=target.database,
                user=target.user,
                password=target.password,
                host=target.host,
                port=target.port,
            ),
            mode=0o640,
            group=grp.getgrnam("froeling-bridge-test").gr_gid,
        )
        # Root-owned environment file: neither the unprivileged API nor callers
        # can inject an ExecStart option or change the destination afterwards.
        path = CONFIG / "window.env"
        temporary = path.with_suffix(".new")
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as stream:
            stream.write("BRIDGE_TRACE=" + str(TEST_STATE / (run_id + ".trace")) + "\n")
        os.replace(temporary, path)

    def test_ready(self):
        from urllib.request import urlopen

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not self.active(TEST):
                raise TestControlError("hardware test exited during startup")
            try:
                with urlopen(
                    "http://127.0.0.1:8001/api/v1/health", timeout=1
                ) as response:
                    data = json.load(response)
                if (
                    data.get("mode") == "hardware-read"
                    and data.get("read_connection_verified")
                    and not data.get("capabilities", {}).get("heating_write")
                ):
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        raise TestControlError("hardware test did not become ready")

    def capture(self):
        from urllib.request import urlopen

        try:
            with urlopen(
                "http://127.0.0.1:8001/api/v1/collector", timeout=1
            ) as response:
                return json.load(response)
        except (OSError, ValueError):
            return None

    def resumed_recording(self, after):
        original = ReadOnlyDatabase(DatabaseConfig.load(CONFIG / "source-db.json"))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if not self.active(P4D):
                return False
            try:
                with original.transaction() as cursor:
                    cursor.execute(
                        "SELECT time FROM samples WHERE time >= %s AND aggregate='S' "
                        "ORDER BY time DESC LIMIT 1",
                        (after,),
                    )
                    if cursor.fetchone():
                        return True
            except Exception:
                return False
            time.sleep(2)
        return False


class Coordinator:
    def __init__(self, system, state_dir=STATE):
        self.system = system
        self.path = state_dir / "window.json"

    def read(self):
        if not self.path.exists():
            return dict(phase="idle")
        return json.loads(self.path.read_text())

    def write(self, state):
        atomic_json(self.path, state)

    def status(self):
        state = self.read()
        return dict(
            state,
            p4d_active=self.system.active(P4D),
            hardware_active=self.system.active(TEST),
            timer_active=self.system.active(TIMER),
        )

    def start(self):
        previous = self.read()
        if previous.get("phase") in ("armed", "switching", "running", "restoring"):
            raise TestControlError("a test window is already active")
        self.system.preflight()
        run_id = uuid.uuid4().hex
        self.system.prepare_window(run_id)
        state = dict(
            phase="armed",
            run_id=run_id,
            duration_seconds=DURATION,
            started_at=datetime.now(ZONE).isoformat(),
            collector=None,
        )
        # The durable state and verified timer must exist before p4d is touched.
        self.write(state)
        try:
            self.system.arm()
            state["phase"] = "switching"
            self.write(state)
            self.system.stop(P4D)
            if self.system.active(P4D) or not self.system.device_free():
                raise TestControlError("p4d or another process still holds the device")
            self.system.start(TEST)
            self.system.test_ready()
            state["phase"] = "running"
            self.write(state)
            return self.status()
        except BaseException:
            # Even cancellation after the stop must restore p4d. The timer is
            # an independent fallback if this process itself disappears.
            self.rollback()
            raise

    def rollback(self):
        state = self.read()
        if (
            state.get("phase") in ("idle", "returned")
            and not self.system.active(TEST)
            and self.system.active(P4D)
        ):
            return self.status()
        state["collector"] = self.system.capture() or state.get("collector")
        report = TEST_STATE / (str(state.get("run_id", "")) + ".trace.result.json")
        final = read_report(report)
        state["collector"] = final.get("collector") or state["collector"]
        state["fatal_reason"] = final.get("fatal_reason")
        state["phase"] = "restoring"
        self.write(state)
        self.system.stop(TEST)
        final = read_report(report)
        state["collector"] = final.get("collector") or state["collector"]
        state["fatal_reason"] = final.get("fatal_reason") or state.get("fatal_reason")
        if self.system.active(TEST) or (
            not self.system.active(P4D) and not self.system.device_free()
        ):
            state["phase"] = "restore_failed"
            self.write(state)
            raise TestControlError(
                "test has not released the device; p4d was not started concurrently"
            )
        after = datetime.now(ZONE).replace(tzinfo=None, microsecond=0)
        self.system.start(P4D)
        if not self.system.active(P4D):
            raise TestControlError("p4d did not restart")
        state["recording_resumed"] = self.system.resumed_recording(after)
        state["phase"] = (
            "returned"
            if state["recording_resumed"]
            else "returned_without_recording_confirmation"
        )
        state["returned_at"] = datetime.now(ZONE).isoformat()
        self.write(state)
        self.system.stop(TIMER)
        return self.status()


@contextmanager
def locked():
    fd = os.open(
        STATE / "coordinator.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise TestControlError("another test-control action is in progress") from None
    finally:
        os.close(fd)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if (
        os.geteuid() != 0
        or len(args) != 1
        or args[0] not in ("status", "start-test", "rollback")
    ):
        print(
            "Use the installed root helper with status, start-test or rollback.",
            file=sys.stderr,
        )
        return 2
    try:
        with locked():
            controller = Coordinator(System())
            if args[0] == "start-test":
                result = controller.start()
            elif args[0] == "rollback":
                result = controller.rollback()
            else:
                result = controller.status()
            print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, TestControlError)
            else "test control failed; inspect local configuration and service state"
        )
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
