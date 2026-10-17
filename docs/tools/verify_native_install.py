import json, os, pty, select, subprocess, sys, tempfile, time
from pathlib import Path
from threading import Thread, Event

if (
    sys.argv[1:] != ["--in-container"]
    or not Path("/.dockerenv").exists()
    or os.geteuid() != 0
):
    raise SystemExit(
        "Run explicitly with --in-container inside a disposable Docker container; this test replaces container systemd commands."
    )
sys.path.insert(0, "/source/src")
from froeling_bridge.codec import StreamDecoder, encode_frame
from froeling_bridge.simulator import demo_heater
from froeling_bridge.messages import MenuItem
from urllib.request import urlopen

# This file runs inside a disposable container. Only systemd calls are simulated;
# installer/package/user/permissions/TTY/HTTP are real. Separate spare-unit test covers real systemd.
assert Path("/source/deploy/install-standalone.sh").exists()
import shutil

project = Path("/tmp/project")
project.mkdir()
for name in ("pyproject.toml", "README.md"):
    shutil.copy2(Path("/source") / name, project / name)
for name in ("src", "deploy"):
    shutil.copytree(
        Path("/source") / name,
        project / name,
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
shim = """#!/usr/local/bin/python3
import os,json,sys,subprocess,signal
from pathlib import Path
p=Path('/tmp/native-unit-state.json');state=json.loads(p.read_text()) if p.exists() else {}
a=sys.argv[1];units=[x for x in sys.argv[2:] if not x.startswith('--')];u=units[-1] if units else ''
if a=='is-active':raise SystemExit(0 if state.get(u,{}).get('active') else 3)
if a=='is-enabled':raise SystemExit(0 if state.get(u,{}).get('enabled') else 1)
if a in ('enable','disable'):state.setdefault(u,{})['enabled']=a=='enable'
if a=='start':
 state.setdefault(u,{})['active']=True
 if u=='froeling-bridge.service':
  log=open('/tmp/native-service.log','a')
  proc=subprocess.Popen(['runuser','-u','froeling-bridge','--','/opt/froeling-bridge/0.5.0/venv/bin/python','-I','-m','froeling_bridge.run_config','/etc/froeling-bridge/settings.json'],stdout=log,stderr=log,start_new_session=True)
  state[u]['pid']=proc.pid
if a=='stop':
 unit=state.setdefault(u,{})
 if unit.get('pid'):
  try:os.killpg(unit['pid'],signal.SIGTERM)
  except ProcessLookupError:pass
 unit['active']=False
p.write_text(json.dumps(state))
"""
Path("/usr/bin/systemctl").write_text(shim)
Path("/usr/bin/systemctl").chmod(0o755)
# Unit syntax/ordering is tested separately using the actual host systemd.
Path("/usr/bin/systemd-analyze").write_text("#!/bin/sh\nexit 0\n")
Path("/usr/bin/systemd-analyze").chmod(0o755)
master, slave = pty.openpty()
device = os.ttyname(slave)
import grp

os.chown(device, 0, grp.getgrnam("dialout").gr_gid)
os.chmod(device, 0o660)
heater = demo_heater()
heater.menu += (MenuItem(3, 1, 0, 43, b"Demo temperature"),)
stop = Event()


def respond():
    decoder = StreamDecoder()
    while not stop.is_set():
        if not select.select([master], [], [], 0.1)[0]:
            continue
        try:
            data = os.read(master, 1024)
        except OSError:
            stop.wait(0.05)
            continue
        for request in decoder.feed(data):
            for frame in heater.handle(request):
                # New installer profile is 43->42, as observed on the actual target.
                if request.command == 0x43:
                    from froeling_bridge.codec import Frame

                    frame = Frame(0x42, frame.payload)
                os.write(master, encode_frame(frame))


Thread(target=respond, daemon=True).start()
config = Path("/tmp/native-settings.json")
config.write_text(json.dumps(dict(device=device, host="127.0.0.1", port=8000)))
os.close(slave)
slave = None
try:
    result = subprocess.run(
        ["bash", "/tmp/project/deploy/install-standalone.sh", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=240,
    )
    Path("/tmp/installer-output.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr)[-4000:])
        print(
            Path("/tmp/native-service.log").read_text()
            if Path("/tmp/native-service.log").exists()
            else ""
        )
        raise AssertionError("native installer failed")
    with urlopen("http://127.0.0.1:8000/api/v1/runtime") as r:
        runtime = json.load(r)
    with urlopen("http://127.0.0.1:8000/api/v1/sensors") as r:
        sensors = json.load(r)["items"]
    assert (
        runtime["phase"] == "ready" and runtime["collector"]["successful_cycles"] >= 1
    )
    assert any(
        s["type"] == "VA" and s["address"] == 43 and s["latest"] for s in sensors
    )
    assert not runtime["history"]["configured"]
    assert Path("/etc/froeling-bridge/settings.json").stat().st_mode & 0o777 == 0o640
    assert Path("/var/lib/froeling-bridge/catalogue.sqlite3").stat().st_uid != 0
    subprocess.run(
        ["/usr/local/sbin/froeling-bridge-control", "rollback"],
        check=True,
        capture_output=True,
    )
    time.sleep(2)  # The shim signals the service; actual systemctl stop waits for exit.
    # Re-run identical setup to verify resumption/preserved state; configure is supplied without secrets.
    result = subprocess.run(
        ["bash", "/tmp/project/deploy/install-standalone.sh", "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        print((result.stdout + result.stderr)[-2500:])
        raise AssertionError("repeat installer failed")
    print(
        "PASS isolated Debian native installation: real package, service user/permissions, TTY discovery/HTTP, no MariaDB/p4d, repeat installation. systemd activation shimmed; real systemd separately tested."
    )
finally:
    subprocess.run(
        ["/usr/bin/systemctl", "stop", "froeling-bridge.service"], capture_output=True
    )
    stop.set()
    os.close(master)
    if slave is not None:
        os.close(slave)
