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
from urllib.request import urlopen, Request

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
import os,json,sys,subprocess,signal,time
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
  proc=subprocess.Popen(['runuser','-u','froeling-bridge','--','/opt/froeling-bridge/0.7.2/venv/bin/python','-I','-m','froeling_bridge.run_config','/etc/froeling-bridge/settings.json'],stdout=log,stderr=log,start_new_session=True)
  state[u]['pid']=proc.pid
if a=='stop':
 unit=state.setdefault(u,{})
 if unit.get('pid'):
  try:os.killpg(unit['pid'],signal.SIGTERM)
  except ProcessLookupError:pass
  # Match real systemctl stop: wait until the service releases the serial port.
  for _ in range(150):
   proc=Path('/proc')/str(unit['pid'])/'stat'
   if not proc.exists() or proc.read_text().split()[2]=='Z':break
   time.sleep(.1)
  else:raise SystemExit('simulated systemctl stop timed out')
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
config.write_text(json.dumps(dict(device=device, host="127.0.0.1", port=8000,auth=dict(mode='lan'))))
os.close(slave)
slave = None
try:
    result = subprocess.run(
        ["bash", "/tmp/project/deploy/install-standalone.sh"],
        input=device+"\nn\n",
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
    assert 'Weboberfläche: http://' in result.stdout and ':8000' in result.stdout
    assert 'initial-login.json' in result.stdout and 'froeling-bridge-users add' in result.stdout
    installed=json.loads(Path('/etc/froeling-bridge/settings.json').read_text())
    assert installed['auth']=={'mode':'lan'}
    initial=json.loads(Path('/var/lib/froeling-bridge-installer/initial-login.json').read_text())
    assert initial['username']=='operator' and initial['password'] not in result.stdout
    import re
    from http.cookiejar import CookieJar
    from urllib.request import build_opener,HTTPCookieProcessor
    from urllib.parse import urlencode
    browser=build_opener(HTTPCookieProcessor(CookieJar()))
    def login(name,password):
        with browser.open('http://127.0.0.1:8000/login') as response:
            csrf=re.search(r'name="csrf" value="([^"]+)"',response.read().decode())[1]
        body=urlencode(dict(username=name,password=password,csrf=csrf)).encode()
        with browser.open(Request('http://127.0.0.1:8000/api/v1/auth/login',data=body,headers={'Origin':'http://127.0.0.1:8000'})) as response:
            assert response.status==200
        with browser.open('http://127.0.0.1:8000/api/v1/auth/me') as response:
            return json.load(response)
    writer=login(initial['username'],initial['password'])
    assert writer['role']=='write' and 'write_validation' not in installed
    assert heater.parameter_write_count==0  # Installation itself must not change settings.
    with browser.open('http://127.0.0.1:8000/api/v1/health') as response:
        assert json.load(response)['write_operations']==['write_parameter']
    with browser.open('http://127.0.0.1:8000/api/v1/menu?parent=10') as response:
        parameter=next(x for x in json.load(response)['items'] if x['address']==0x1234)
    assert parameter['editable']
    def parameter_job(value,actor):
        request=Request('http://127.0.0.1:8000/api/v1/jobs',
                        data=json.dumps(dict(operation='write_parameter',menu_id=parameter['id'],value=value)).encode(),
                        headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8000','X-CSRF-Token':actor['csrf']})
        with browser.open(request) as response:
            assert response.status==202
            job_url='http://127.0.0.1:8000'+json.load(response)['url']
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            with browser.open(job_url) as response:job=json.load(response)
            if job['state'] in ('completed','failed'):return job
            time.sleep(.05)
        raise AssertionError('Fictional parameter job timed out')
    assert parameter_job('67.5',writer)['result']['status']=='confirmed'
    assert heater.parameter_write_count==1 and str(heater.parameters[0x1234].value)=='67.5'
    invalid=parameter_job('999',writer)
    assert invalid['state']=='failed' and invalid['error']['code']=='validation_error'
    assert heater.parameter_write_count==1
    added=subprocess.run(['/usr/local/sbin/froeling-bridge-users','add','personal-user','--role','read','--generate-password'],check=True,capture_output=True,text=True)
    reader=login('personal-user',added.stdout.strip())
    assert reader['role']=='read'
    from urllib.error import HTTPError
    try:parameter_job('69.5',reader)
    except HTTPError as exc:assert exc.code==403
    else:raise AssertionError('Read-only account could write a parameter')
    assert heater.parameter_write_count==1
    headers={'Authorization':'Bearer '+Path('/etc/froeling-bridge/monitor-api-key').read_text().strip()}
    with urlopen(Request("http://127.0.0.1:8000/api/v1/runtime",headers=headers)) as r:
        runtime = json.load(r)
    with urlopen(Request("http://127.0.0.1:8000/api/v1/sensors",headers=headers)) as r:
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
        "PASS isolated Debian native installation: real package, service user/permissions, TTY discovery/HTTP, default parameter writing and read-only denial, no MariaDB/p4d, repeat installation. systemd activation shimmed; real systemd separately tested."
    )
finally:
    subprocess.run(
        ["/usr/bin/systemctl", "stop", "froeling-bridge.service"], capture_output=True
    )
    stop.set()
    os.close(master)
    if slave is not None:
        os.close(slave)
