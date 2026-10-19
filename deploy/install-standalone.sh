#!/bin/bash
# From a source checkout: sudo bash deploy/install-standalone.sh [--config private.json] [--take-over-p4d]
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 2; }
exec 9>/run/lock/froeling-bridge-install.lock
flock -n 9 || { echo 'Another installation is running.' >&2; exit 2; }
source_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
if [[ -f "$source_root/SHA256SUMS" ]]; then
  (cd "$source_root" && sha256sum --quiet -c SHA256SUMS)
fi
configuration=()
takeover=no
while (($#)); do
  case "$1" in
    --config) configuration=(--config "$(realpath -- "$2")"); shift 2;;
    --take-over-p4d) takeover=yes; shift;;
    *) echo 'Unknown option.' >&2; exit 2;;
  esac
done
if systemctl is-active --quiet froeling-bridge.service; then
  echo 'Stop/rollback the running Bridge before changing its installation.' >&2; exit 2
fi
for unit in froeling-bridge-hardware-test.service froeling-bridge-rollback.timer froeling-bridge-rollback.service; do
  if systemctl is-active --quiet "$unit"; then
    echo 'Finish/rollback the active old hardware test first.' >&2; exit 2
  fi
done
if systemctl is-active --quiet p4d.service && [[ $takeover != yes ]]; then
  echo 'p4d is active. Use --take-over-p4d for the controlled switch; original remains installed.' >&2; exit 2
fi
# Check venv before creating a release. Install missing Debian/Ubuntu support automatically.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3-venv
fi
command -v fuser >/dev/null || { apt-get update; apt-get install -y psmisc; }
id froeling-bridge >/dev/null 2>&1 || useradd --system --home /var/lib/froeling-bridge --shell /usr/sbin/nologin froeling-bridge
usermod -a -G dialout froeling-bridge
release=/opt/froeling-bridge/0.7.1
if [[ -e "$release" && ! -f "$release/source.sha256" ]]; then
  echo 'An unrecognized release directory exists; preserved.' >&2; exit 2
fi
install -d -m 0750 -g froeling-bridge "$release"
wheel_hash=$(python3 - "$source_root" <<'PY'
import hashlib,sys
from pathlib import Path
root=Path(sys.argv[1]);digest=hashlib.sha256()
for path in sorted((root/'src/froeling_bridge').rglob('*')):
 if path.is_file() and '__pycache__' not in path.parts:
  digest.update(str(path.relative_to(root)).encode());digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)
if [[ -e "$release/source.sha256" ]]; then
  [[ $(cat "$release/source.sha256") == "$wheel_hash" ]] || { echo 'Different release exists; preserved. Use a new version.' >&2; exit 2; }
else
  printf '%s\n' "$wheel_hash" > "$release/source.sha256"
fi
python3 -m venv "$release/venv"
if [[ -d "$source_root/wheels" ]]; then
  "$release/venv/bin/python" -I -m pip install --no-index --find-links "$source_root/wheels" 'froeling-bridge[service]==0.7.1'
else
  "$release/venv/bin/python" -I -m pip install "$source_root[service]"
fi
chgrp -R froeling-bridge "$release/venv"
chmod -R g+rX "$release/venv"
install -d -m 0750 -g froeling-bridge /etc/froeling-bridge
"$release/venv/bin/python" -I -m froeling_bridge.configure "${configuration[@]}"
chown root:froeling-bridge /etc/froeling-bridge/settings.json
chmod 0640 /etc/froeling-bridge/settings.json
install -d -m 0700 /var/lib/froeling-bridge-installer
"$release/venv/bin/python" -I - <<'PY'
import json,subprocess
from pathlib import Path
from froeling_bridge.host_test import atomic_json
path=Path('/var/lib/froeling-bridge-installer/installation.json')
settings=json.loads(Path('/etc/froeling-bridge/settings.json').read_text())
if path.exists():
 state=json.loads(path.read_text())
else:
 state=dict(p4d_fallback=subprocess.run(['systemctl','is-active','--quiet','p4d.service']).returncode==0,
            p4d_enabled=subprocess.run(['systemctl','is-enabled','--quiet','p4d.service'],capture_output=True).returncode==0)
state.update(device=settings['device'],port=settings.get('port',8000))
atomic_json(path,state)
# Immediate p4d fallback and automatic Bridge restart are different host roles.
# Some systemd versions defer OnFailure until automatic restarts are exhausted.
dropin=Path('/etc/systemd/system/froeling-bridge.service.d')
dropin.mkdir(parents=True,exist_ok=True)
fallback=state.get('automatic_p4d_fallback',state['p4d_fallback'])
policy='[Service]\nRestart=no\n' if fallback else '[Unit]\nStartLimitIntervalSec=0\n\n[Service]\nRestart=always\n'
(dropin/'10-host-role.conf').write_text(policy)
PY
install -d -m 0700 -o froeling-bridge -g froeling-bridge /var/lib/froeling-bridge
# Existing 0.4 state has a different service user; preserve private caches and transfer ownership.
chown -R froeling-bridge:froeling-bridge /var/lib/froeling-bridge
"$release/venv/bin/python" -I -c 'import json; from pathlib import Path; s=json.loads(Path("/etc/froeling-bridge/settings.json").read_text()); assert s.get("auth",{}).get("mode")=="lan" or s.get("auth",{}).get("public_origin"), "Configure auth.mode=lan or auth.public_origin before starting production"'
"$release/venv/bin/python" -I -m froeling_bridge.auth_setup
printf '%s\n' '#!/bin/sh' 'exec /opt/froeling-bridge/0.7.1/venv/bin/python -I -m froeling_bridge.lifecycle "$@"' > "$release/control"
install -m 0755 "$release/control" /usr/local/sbin/froeling-bridge-control
printf '%s\n' '#!/bin/sh' 'exec /opt/froeling-bridge/0.7.1/venv/bin/python -I -m froeling_bridge.auth "$@"' > "$release/users"
install -m 0755 "$release/users" /usr/local/sbin/froeling-bridge-users
for unit in "$source_root"/deploy/standalone/*; do
  if [[ -f /etc/systemd/system/${unit##*/} && ! -e $release/${unit##*/}.previous ]]; then
    cp -p "/etc/systemd/system/${unit##*/}" "$release/${unit##*/}.previous"
  fi
  install -m 0644 "$unit" /etc/systemd/system/
done
systemd-analyze verify /etc/systemd/system/froeling-bridge.service /etc/systemd/system/froeling-bridge-rescue.service /etc/systemd/system/froeling-bridge-startup.timer /etc/systemd/system/froeling-bridge-health.service /etc/systemd/system/froeling-bridge-health.timer
install -d -m 0755 /usr/local/libexec
install -m 0644 "$source_root/deploy/libexec/froeling-bridge-health.py" /usr/local/libexec/froeling-bridge-health.py
systemctl daemon-reload
if [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
  [[ $SUDO_USER =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || exit 2
  sudoers=$(mktemp)
  trap 'rm -f "$sudoers"' EXIT
  printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/froeling-bridge-control status, /usr/local/sbin/froeling-bridge-control start, /usr/local/sbin/froeling-bridge-control rollback\n' "$SUDO_USER" > "$sudoers"
  visudo -cf "$sudoers"
  install -m 0440 "$sudoers" /etc/sudoers.d/froeling-bridge-control
fi
/usr/local/sbin/froeling-bridge-control start
systemctl enable --now froeling-bridge-health.timer

"$release/venv/bin/python" -I - <<'PYINFO'
import json,socket
from pathlib import Path
settings=json.loads(Path('/etc/froeling-bridge/settings.json').read_text())
auth=settings.get('auth',{})
if auth.get('mode')=='lan':
 host=settings.get('host','0.0.0.0')
 if host in ('0.0.0.0','::'):
  try:
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
    probe.connect(('192.0.2.1',9));host=probe.getsockname()[0]
  except OSError:host=socket.gethostname()+'.local'
 if ':' in host:host='['+host+']'
 url='http://'+host+':'+str(settings.get('port',8000))
else:url=auth['public_origin']
print('Weboberfläche: '+url)
print('Erster Benutzer: operator')
print('Erstpasswort anzeigen: sudo cat /var/lib/froeling-bridge-installer/initial-login.json')
print('Eigenen Benutzer anlegen: sudo froeling-bridge-users add NAME --role write')
PYINFO
