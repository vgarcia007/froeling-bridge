#!/bin/bash
# Install separately from the tested release, then activate continuous recording.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 2; }
exec 9>/run/lock/froeling-bridge-install.lock
flock -n 9 || { echo 'Another installation is running.' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
release=/opt/froeling-bridge/0.4.0
if systemctl is-active --quiet froeling-bridge.service; then
  /usr/local/sbin/froeling-bridge-live status
  exit 0
fi
systemctl is-active --quiet p4d.service
for unit in froeling-bridge-hardware-test.service froeling-bridge-rollback.timer froeling-bridge-rollback.service; do
  if systemctl is-active --quiet "$unit"; then
    echo 'Finish/rollback the hardware test first.' >&2; exit 2
  fi
done
if [[ -e "$release" ]]; then
  cmp --silent release.json "$release/release.json" || { echo 'Different release already exists; preserved.' >&2; exit 2; }
else
  install -d -m 0750 -g froeling-bridge-test "$release"
  install -m 0600 release.json "$release/release.json"
fi
python3 -m venv "$release/venv"
"$release/venv/bin/python" -I -m pip install --no-index --find-links "$bundle/wheels" 'froeling-bridge[service]==0.4.0'
chgrp -R froeling-bridge-test "$release/venv"
chmod -R g+rX "$release/venv"
"$release/venv/bin/python" -I - <<'PY'
from froeling_bridge.storage import DatabaseConfig,P4dDatabase
repo=P4dDatabase(DatabaseConfig.load('/etc/froeling-bridge-test/source-db.json'),allow_recording=True)
repo.validate_schema()
print('Existing database schema verified; no data/schema changes performed.')
PY
install -d -m 0700 -o froeling-bridge-test -g froeling-bridge-test /var/lib/froeling-bridge
if [[ ! -e /var/lib/froeling-bridge/time-programs-cache.json && ! -L /var/lib/froeling-bridge-test/time-programs-cache.json && -f /var/lib/froeling-bridge-test/time-programs-cache.json ]]; then
  install -m 0600 -o froeling-bridge-test -g froeling-bridge-test /var/lib/froeling-bridge-test/time-programs-cache.json /var/lib/froeling-bridge/time-programs-cache.json
fi
install -m 0755 froeling-bridge-live /usr/local/sbin/froeling-bridge-live
install -m 0644 systemd/* /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/froeling-bridge.service /etc/systemd/system/froeling-bridge-fallback.service /etc/systemd/system/froeling-bridge-activation.timer
systemctl daemon-reload
# Fixed operations for subsequent checks/rollback through the existing SSH user.
if [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
  [[ $SUDO_USER =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || { echo 'Unsupported sudo user name.' >&2; exit 2; }
  sudoers=$(mktemp)
  trap 'rm -f "$sudoers"' EXIT
  printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/froeling-bridge-live status, /usr/local/sbin/froeling-bridge-live start, /usr/local/sbin/froeling-bridge-live rollback\n' "$SUDO_USER" > "$sudoers"
  visudo -cf "$sudoers"
  install -m 0440 "$sudoers" /etc/sudoers.d/froeling-bridge-live
fi
# Preserve the original files. Only the selected boot service changes.
/usr/local/sbin/froeling-bridge-live start
echo 'LIVE: http://SERVER-IP:8000 — continuous recording in the existing p4d database.'
echo 'Return to p4d: sudo /usr/local/sbin/froeling-bridge-live rollback'
