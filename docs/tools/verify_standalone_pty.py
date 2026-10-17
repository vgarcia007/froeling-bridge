import json, os, pty, select, socket, subprocess, tempfile, time
from pathlib import Path
from threading import Thread, Event
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from froeling_bridge.codec import StreamDecoder, encode_frame
from froeling_bridge.simulator import demo_heater
from froeling_bridge.messages import Command, MenuItem

root = Path.cwd()
master, slave = pty.openpty()
device = os.ttyname(slave)
stop = Event()
commands = []
heater = demo_heater()
heater.menu += (MenuItem(3, 1, 0, 43, b"Demo temperature"),)


def respond():
    decoder = StreamDecoder()
    while not stop.is_set():
        if not select.select([master], [], [], 0.1)[0]:
            continue
        try:
            data = os.read(master, 512)
        except OSError:
            return
        for frame in decoder.feed(data):
            commands.append(frame.command)
            for reply in heater.handle(frame):
                os.write(master, encode_frame(reply))


thread = Thread(target=respond, daemon=True)
thread.start()
with tempfile.TemporaryDirectory(prefix="froeling-independent-pty-") as tmp:
    tmp = Path(tmp)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (tmp / "log").open("w+")
    args = [
        str(root / ".venv/bin/python"),
        "-m",
        "froeling_bridge",
        "serve",
        "--mode",
        "standalone",
        "--state-dir",
        str(tmp / "state"),
        "--device",
        device,
        "--interval",
        ".3",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]

    def launch():
        return subprocess.Popen(
            args,
            env=dict(os.environ, PYTHONPATH=str(root / "src")),
            stdout=log,
            stderr=log,
        )

    process = launch()
    base = f"http://127.0.0.1:{port}/api/v1"

    def get(path):
        with urlopen(base + path, timeout=2) as response:
            return json.load(response)

    def ready():
        for _ in range(200):
            if process.poll() is not None:
                raise AssertionError("process exited; private log: " + log.name)
            try:
                data = get("/sensors")
                if any(
                    s["type"] == "VA" and s["address"] == 43 and s["latest"]
                    for s in data["items"]
                ):
                    return
            except OSError:
                pass
            time.sleep(0.05)
        raise AssertionError("no discovery/live values")

    try:
        ready()
        runtime = get("/runtime")
        assert runtime["catalogue_ready"]
        assert not runtime["history"]["configured"]
        request = Request(
            base + "/jobs",
            data=json.dumps(
                dict(operation="write_parameter", menu_id=2, value="67.5")
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request)
            raise AssertionError("write accepted without validation")
        except HTTPError as e:
            assert e.code == 403
        assert not set(commands) & {Command.SET_PARAMETER, Command.SET_TIMES}
        assert (tmp / "state/catalogue.sqlite3").exists()
        first_count = commands.count(Command.VALUES_FIRST)
        process.terminate()
        assert process.wait(timeout=15) == 0
        process = launch()
        ready()
        assert (
            commands.count(Command.VALUES_FIRST) == first_count
        ), "restart unnecessarily discarded catalogue"
        process.terminate()
        assert process.wait(timeout=15) == 0
        # File loss: keep only known time cache, rebuild catalogue entirely from TTY.
        (tmp / "state/catalogue.sqlite3").unlink()
        process = launch()
        ready()
        assert commands.count(Command.VALUES_FIRST) == first_count + 1
        print(
            "PASS real PTY/HTTP: empty boot, discovery, live values, write denial, SIGTERM/restart, catalogue loss/rebuild; no MariaDB/p4d."
        )
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        stop.set()
        thread.join(2)
        os.close(master)
        os.close(slave)
        log.close()
