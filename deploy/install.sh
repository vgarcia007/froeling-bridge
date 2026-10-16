#!/bin/bash
# Run with sudo after reviewing this prepared bundle; interrupted setup can be resumed.
# Does not stop p4d, open the TTY or start the hardware test.
set -euo pipefail
umask 077
phase=preflight
trap 'echo "Setup failed during $phase. p4d was not stopped. Fix the reported cause and rerun this same installer." >&2' ERR
# Serialize setup attempts independently of the hardware coordinator.
if [[ $EUID -ne 0 ]]; then echo 'Run this setup with sudo.' >&2; exit 2; fi
exec 9>/run/lock/froeling-bridge-install.lock
flock -n 9 || { echo 'Another setup is running.' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
release=/opt/froeling-bridge/0.3.0
config=/etc/froeling-bridge-test
coordinator=/var/lib/froeling-bridge-coordinator
operator=${SUDO_USER:-}
if [[ -z "$operator" || "$operator" == root || ! "$operator" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]]; then
  echo 'Run through sudo from the intended SSH account.' >&2; exit 2
fi
for executable in python3 systemctl systemd-analyze fuser sha256sum visudo flock; do command -v "$executable" >/dev/null; done
if [[ -x /usr/bin/docker ]]; then docker_cli=/usr/bin/docker
elif [[ -x /snap/bin/docker ]]; then docker_cli=/snap/bin/docker
else echo 'No supported local Docker client found.' >&2; exit 2; fi
docker_local() { "$docker_cli" --host unix:///var/run/docker.sock "$@"; }
docker_local info --format '{{.ServerVersion}}' >/dev/null
envfile="$config/test-db.env"
if [[ "$docker_cli" == /snap/bin/docker ]]; then
  # Snap confinement cannot assume access to our private /etc directory.
  envfile=/var/snap/docker/common/froeling-bridge-test.env
fi
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
python3 -I "$bundle/install_state.py" check "$bundle"
if systemctl is-active --quiet froeling-bridge-hardware-test.service; then
  echo 'A hardware test is running; finish/rollback that test before setup.' >&2; exit 2
fi
# Check venv support BEFORE creating permanent installation directories.
venv_probe=$(mktemp -d)
if ! python3 -m venv "$venv_probe/venv"; then
  rm -rf -- "$venv_probe"
  echo 'Python venv support is missing. Install python3-venv (on this host: python3.12-venv), then rerun.' >&2
  exit 2
fi
rm -rf -- "$venv_probe"
container_exists=false
if docker_local inspect froeling-bridge-test-db >/dev/null 2>&1; then
  container_exists=true
  # Never invent new credentials for an existing database.
  if [[ ! -f "$config/test-db.json" ]]; then
    echo 'Existing test container has no matching credentials; preserved.' >&2; exit 2
  fi
  docker_local inspect froeling-bridge-test-db | python3 -I "$bundle/install_state.py" container "$bundle"
elif docker_local volume inspect froeling-bridge-test-data >/dev/null 2>&1; then
  # Only volumes created by this resumable installer can be adopted without a container.
  if [[ $(docker_local volume inspect --format '{{index .Labels "org.froeling-bridge.role"}}' froeling-bridge-test-data) != hardware-test ]]; then
    echo 'Unidentified existing test volume; preserved.' >&2; exit 2
  fi
  if [[ ! -f "$config/test-db.json" ]]; then
    echo 'Existing test volume has no matching credentials; preserved.' >&2; exit 2
  fi
fi
if ! systemctl is-active --quiet p4d.service || ! systemctl is-enabled --quiet p4d.service; then
  echo 'Original p4d must be active and enabled before setup.' >&2; exit 2
fi
# Existing services may own their expected ports on a repeated setup.
skip_ports=""
if systemctl is-active --quiet froeling-bridge-preview.service; then skip_ports=8000; fi
if [[ "$container_exists" == true ]]; then skip_ports="$skip_ports 33079"; fi
python3 -I - "$skip_ports" <<'PY'
import socket,sys
skip={int(port) for port in sys.argv[1].split()}
for port in set((8000,8001,33079))-skip:
 with socket.socket() as sock:
  sock.bind(('127.0.0.1' if port == 33079 else '0.0.0.0',port))
PY
phase=files
getent group dialout >/dev/null
if ! id froeling-bridge-test >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin froeling-bridge-test
fi
install -d -m 0755 "$release"
install -m 0644 release.json "$release/release.json"
install -d -m 0750 -g froeling-bridge-test "$config"
install -d -m 0700 "$coordinator"
install -d -m 0700 -o froeling-bridge-test -g froeling-bridge-test /var/lib/froeling-bridge-test
if [[ ! -e "$config/source-db.json" ]]; then
  install -m 0640 -g froeling-bridge-test source-db.json "$config/source-db.json"
fi
install -d -m 0700 "$release/wheels"
install -m 0644 wheels/*.whl "$release/wheels/"
phase=python-environment
python3 -m venv "$release/venv"
"$release/venv/bin/python" -I -m pip install --no-index --find-links "$release/wheels" 'froeling-bridge[service]==0.3.0'
# venv inherits umask 077; grant the service group access to its own runtime.
chgrp -R froeling-bridge-test "$release/venv"
chmod -R g+rX "$release/venv"
phase=test-database
python3 -I "$bundle/install_state.py" credentials "$bundle"
if [[ "$envfile" != "$config/test-db.env" ]]; then
  if [[ -e "$envfile" ]]; then
    cmp --silent "$config/test-db.env" "$envfile" || {
      echo 'Existing Snap credentials differ; preserved.' >&2; exit 2;
    }
  else
    install -m 0600 "$config/test-db.env" "$envfile"
  fi
fi
if [[ "$container_exists" == true ]]; then
  docker_local start froeling-bridge-test-db >/dev/null
else
  docker_local volume create --label org.froeling-bridge.role=hardware-test froeling-bridge-test-data >/dev/null
  docker_local run -d --name froeling-bridge-test-db --restart unless-stopped \
    --label org.froeling-bridge.role=hardware-test \
    --env-file "$envfile" -p 127.0.0.1:33079:3306 \
    -v froeling-bridge-test-data:/var/lib/mysql mariadb:10.11 >/dev/null
fi
"$release/venv/bin/python" -I "$bundle/install_state.py" database "$bundle"
phase=services
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
echo 'Setup complete. p4d is still running. Simulator preview: http://SERVER-IP:8000 (LAN).'
echo 'Hardware test is NOT started. Use the fixed helper when ready.'
