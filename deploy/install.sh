#!/bin/bash
# Run exactly once with sudo after reviewing this prepared bundle.
# Does not stop p4d, open the TTY or start the hardware test.
set -euo pipefail
umask 077
if [[ $EUID -ne 0 ]]; then echo 'Run this setup with sudo.' >&2; exit 2; fi
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
release=/opt/froeling-bridge/0.3.0
config=/etc/froeling-bridge-test
coordinator=/var/lib/froeling-bridge-coordinator
operator=${SUDO_USER:-}
if [[ -z "$operator" || "$operator" == root || ! "$operator" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]]; then
  echo 'Run through sudo from the intended SSH account.' >&2; exit 2
fi
for executable in python3 systemctl fuser sha256sum visudo; do command -v "$executable" >/dev/null; done
if [[ -x /usr/bin/docker ]]; then docker_cli=/usr/bin/docker
elif [[ -x /snap/bin/docker ]]; then docker_cli=/snap/bin/docker
else echo 'No supported local Docker client found.' >&2; exit 2; fi
docker_local() { "$docker_cli" --host unix:///var/run/docker.sock "$@"; }
docker_local info --format '{{.ServerVersion}}' >/dev/null
envfile="$config/test-db.env"
if [[ "$docker_cli" == /snap/bin/docker ]]; then
  # Snap confinement cannot assume access to our private /etc directory.
  envfile=/var/snap/docker/common/froeling-bridge-test.env
  if [[ -e "$envfile" ]]; then echo 'Snap test environment file already exists; inspect it before reinstalling.' >&2; exit 2; fi
fi
if [[ -e "$release" || -e "$config" || -e "$coordinator" || -e /usr/local/sbin/froeling-bridge-test ]]; then
  echo 'An installation already exists; it will not be overwritten. Inspect it before upgrading.' >&2; exit 2
fi
if docker_local inspect froeling-bridge-test-db >/dev/null 2>&1 || docker_local volume inspect froeling-bridge-test-data >/dev/null 2>&1; then
  echo 'The intended test container name is already in use; nothing was changed.' >&2; exit 2
fi
if ! systemctl is-active --quiet p4d.service || ! systemctl is-enabled --quiet p4d.service; then
  echo 'Original p4d must be active and enabled before setup.' >&2; exit 2
fi
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
python3 -I - <<'PY'
import socket
for port in (8000,8001,33079):
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',port))
PY
# Validate every shipped unit before installing it. Exec paths are created below.
getent group dialout >/dev/null
if ! id froeling-bridge-test >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin froeling-bridge-test
fi
install -d -m 0755 "$release"
install -m 0644 release.json "$release/release.json"
install -d -m 0750 -g froeling-bridge-test "$config"
install -d -m 0700 "$coordinator"
install -d -m 0700 -o froeling-bridge-test -g froeling-bridge-test /var/lib/froeling-bridge-test
install -m 0640 -g froeling-bridge-test source-db.json "$config/source-db.json"
install -d -m 0700 "$release/wheels"
install -m 0644 wheels/*.whl "$release/wheels/"
python3 -m venv "$release/venv"
"$release/venv/bin/python" -I -m pip install --no-index --find-links "$release/wheels" 'froeling-bridge[service]==0.3.0'
# Secret material is generated locally and is never placed in command arguments.
python3 -I - <<'PY'
import json,os,secrets,grp
from pathlib import Path
root=Path('/etc/froeling-bridge-test')
password=secrets.token_hex(32)
(root/'test-db.env').write_text('MARIADB_ROOT_PASSWORD='+password+'\n')
os.chmod(root/'test-db.env',0o600)
path=root/'test-db.json'
path.write_text(json.dumps(dict(host='127.0.0.1',port=33079,database='froeling_bridge_test_initial',user='root',password=password))+'\n')
os.chmod(path,0o640)
os.chown(path,0,grp.getgrnam('froeling-bridge-test').gr_gid)
PY
# Refuse a Docker daemon failure; do not touch any existing container or database.
if [[ "$envfile" != "$config/test-db.env" ]]; then
  install -m 0600 "$config/test-db.env" "$envfile"
fi
docker_local run -d --name froeling-bridge-test-db --restart unless-stopped \
  --label org.froeling-bridge.role=hardware-test \
  --env-file "$envfile" -p 127.0.0.1:33079:3306 \
  -v froeling-bridge-test-data:/var/lib/mysql mariadb:10.11 >/dev/null
"$release/venv/bin/python" -I - <<'PY'
from dataclasses import replace
from pathlib import Path
import time
from froeling_bridge.storage import DatabaseConfig
from froeling_bridge.testdb import initialize
config=DatabaseConfig.load('/etc/froeling-bridge-test/test-db.json')
for attempt in range(60):
 try:
  conn=replace(config,database='').connect()
  conn.close()
  break
 except Exception:
  time.sleep(1)
else: raise SystemExit('Separate test database did not become ready; p4d is unchanged.')
initialize(config,seed=False)
PY
install -m 0755 froeling-bridge-test /usr/local/sbin/froeling-bridge-test
install -m 0644 systemd/*.service systemd/*.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/froeling-bridge-*.service /etc/systemd/system/froeling-bridge-*.timer
sudoers=$(mktemp)
trap 'rm -f "$sudoers"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/froeling-bridge-test status, /usr/local/sbin/froeling-bridge-test start-test, /usr/local/sbin/froeling-bridge-test rollback\n' "$operator" > "$sudoers"
visudo -cf "$sudoers" >/dev/null
install -m 0440 "$sudoers" /etc/sudoers.d/froeling-bridge-test
systemctl daemon-reload
systemctl start froeling-bridge-preview.service
systemctl is-active --quiet p4d.service
systemctl is-active --quiet froeling-bridge-preview.service
echo 'Setup complete. p4d is still running. Simulator preview: loopback port 8000.'
echo 'Hardware test is NOT started. Use the fixed helper when ready.'
