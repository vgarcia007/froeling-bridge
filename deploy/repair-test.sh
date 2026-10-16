#!/bin/bash
# Restore p4d before installing the corrected test coordinator.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 2; }
bundle=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle"
sha256sum --quiet -c SHA256SUMS
if systemctl is-active --quiet froeling-bridge-hardware-test.service; then
  echo 'A hardware test is active; use the rollback helper before repair.' >&2; exit 2
fi
# Validate process inspection before any service change; no TTY open.
if fuser /dev/ttyUSB0 >/dev/null 2>"$bundle/fuser-repair-error.private"; then
  if ! systemctl is-active --quiet p4d.service; then
    echo 'USB port occupied while p4d is stopped; inspect the owner before repair.' >&2; exit 2
  fi
elif [[ -s "$bundle/fuser-repair-error.private" ]]; then
  echo 'Port inspection failed; inspect fuser-repair-error.private.' >&2; exit 2
fi
rm -f "$bundle/fuser-repair-error.private"
systemctl start p4d.service
bash "$bundle/update-lan.sh"
/usr/local/sbin/froeling-bridge-test rollback
echo 'Coordinator repaired; p4d active. No new hardware test started.'
