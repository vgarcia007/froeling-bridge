#!/bin/bash
# Apply the reviewed LAN-access hotfix to the existing 0.3.0 test installation.
# Does not stop p4d or start the hardware test.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run this update with sudo.' >&2; exit 2; }
exec 9>/run/lock/froeling-bridge-install.lock
flock -n 9 || { echo 'Another setup is running.' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
release=/opt/froeling-bridge/0.3.0
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
python3 -I "$bundle/install_state.py" check "$bundle"
systemctl is-active --quiet p4d.service
if systemctl is-active --quiet froeling-bridge-hardware-test.service; then
  echo 'Finish/rollback the active hardware test before updating.' >&2; exit 2
fi
"$release/venv/bin/python" -I -m pip install --no-index --no-deps --force-reinstall "$bundle/wheels/froeling_bridge-0.3.0-py3-none-any.whl"
install -m 0644 "$bundle/wheels/froeling_bridge-0.3.0-py3-none-any.whl" "$release/wheels/"
chgrp -R froeling-bridge-test "$release/venv"
chmod -R g+rX "$release/venv"
install -m 0644 systemd/froeling-bridge-preview.service systemd/froeling-bridge-hardware-test.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/froeling-bridge-preview.service /etc/systemd/system/froeling-bridge-hardware-test.service
systemctl daemon-reload
systemctl restart froeling-bridge-preview.service
python3 -I - <<'PY'
import time,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(30):
 try:
  with opener.open('http://127.0.0.1:8000/api/v1/health',timeout=1) as response:
   if response.status==200: break
 except OSError:
  time.sleep(0.3)
else: raise SystemExit('Preview did not become ready; inspect its systemd journal.')
PY
systemctl is-active --quiet p4d.service
echo 'LAN preview ready: http://SERVER-IP:8000'
echo 'p4d is still running. Hardware test is not started.'
