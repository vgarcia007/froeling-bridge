#!/bin/bash
# Copy private test traces for offline analysis. No service/device/DB changes.
set -euo pipefail
umask 077
if [[ $EUID -ne 0 || -z ${SUDO_USER:-} || ${SUDO_USER:-root} == root ]]; then
  echo 'Run this script with sudo from your SSH account.' >&2
  exit 2
fi
operator_home=$(getent passwd "$SUDO_USER" | cut -d: -f6)
[[ -d "$operator_home" ]] || { echo 'SSH account home directory not found.' >&2; exit 2; }
# Create a fresh root-owned file, then publish it atomically for the SSH account.
archive=$(mktemp "$operator_home/.froeling-traces.XXXXXX")
trap 'rm -f -- "$archive"' EXIT
tar -C /var/lib/froeling-bridge-test --exclude='time-programs-cache.json' --exclude='.time-cache-*' -czf "$archive" .
chmod 0600 "$archive"
chown "$SUDO_USER" "$archive"
mv -fT -- "$archive" "$operator_home/froeling-traces.private.tgz"
echo 'Private trace copy ready for analysis. p4d remains unchanged.'
