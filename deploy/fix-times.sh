#!/bin/bash
# Apply the observed read-only time-program reply mapping. No hardware test start.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
python3 -I "$bundle/install_state.py" check "$bundle"
systemctl is-active --quiet p4d.service
if systemctl is-active --quiet froeling-bridge-hardware-test.service; then
  echo 'Finish the active hardware test before applying this fix.' >&2; exit 2
fi
config=/etc/froeling-bridge-test/heating-reply-profile.json
if [[ -e "$config" ]] && ! cmp --silent heating-reply-profile.json "$config"; then
  echo 'An alternative reply profile already exists; preserved.' >&2; exit 2
fi
bash "$bundle/update-lan.sh"
install -m 0644 systemd/froeling-bridge-hardware-test.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/froeling-bridge-hardware-test.service
systemctl daemon-reload
systemctl is-active --quiet p4d.service
echo 'Time-program read profile installed. p4d is still running; no test started.'
