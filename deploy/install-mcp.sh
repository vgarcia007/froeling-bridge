#!/usr/bin/env bash
# Install only the separate read-only MCP service; never touches Bridge/p4d.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
MCP_PYTHON="${BRIDGE_MCP_PYTHON:-python3.11}"
CONFIG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --python) MCP_PYTHON="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --help|-h) echo 'Usage: sudo bash deploy/install-mcp.sh [--python /path/to/python3.11] [--config /private/mcp.env]'; exit 0 ;;
    *) echo 'Unknown option' >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo 'Run this installer with sudo.' >&2; exit 1; }
"$MCP_PYTHON" -c 'import sys; assert sys.version_info >= (3,11), "MCP requires Python 3.11+"'
TARGET=/opt/froeling-bridge-mcp
ENV_FILE=/etc/froeling-bridge-mcp.env
if [[ -n "$CONFIG" ]]; then
  [[ -f "$CONFIG" ]] || { echo 'Missing private environment file.' >&2; exit 1; }
  if [[ "$(readlink -f "$CONFIG")" != "$ENV_FILE" ]]; then install -m 0600 -o root -g root "$CONFIG" "$ENV_FILE"; fi
fi
[[ -f "$ENV_FILE" ]] || { echo 'Prepare a private environment file as described in docs/mcp.md and pass --config.' >&2; exit 1; }
chown root:root "$ENV_FILE"; chmod 0600 "$ENV_FILE"
if ! id froeling-mcp >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin froeling-mcp
fi
install -d -m 0755 "$TARGET"
if [[ ! -x "$TARGET/venv/bin/python" ]]; then "$MCP_PYTHON" -m venv "$TARGET/venv"; fi
"$TARGET/venv/bin/python" -m pip install --disable-pip-version-check "$APP_DIR[mcp]"
runuser -u froeling-mcp -- "$TARGET/venv/bin/python" -I -c 'import froeling_bridge.mcp_server'
cat > /etc/systemd/system/froeling-bridge-mcp.service <<'EOF'
[Unit]
Description=Froeling Bridge read-only HTTP MCP adapter
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=froeling-mcp
Group=froeling-mcp
WorkingDirectory=/opt/froeling-bridge-mcp
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=/etc/froeling-bridge-mcp.env
ExecStart=/opt/froeling-bridge-mcp/venv/bin/python -I -m froeling_bridge.mcp_server
Restart=always
RestartSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
InaccessiblePaths=-/var/lib/froeling-bridge -/etc/froeling-bridge

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable froeling-bridge-mcp.service
systemctl restart froeling-bridge-mcp.service
echo 'MCP service installed. Check: systemctl status froeling-bridge-mcp.service'
