#!/usr/bin/env bash
set -euo pipefail
LOG=${MCP_WATCHDOG_LOG:-/var/log/supplier_mcp_watchdog.log}
TS=$(date '+%Y-%m-%d %H:%M:%S')
if ! systemctl is-active --quiet supplier-mcp.service; then
  echo "[$TS] supplier-mcp.service inactive -> restarting" >> "$LOG"
  systemctl restart supplier-mcp.service
fi
if ! curl -fsS http://127.0.0.1:8090/health >/dev/null; then
  echo "[$TS] MCP health endpoint failed" >> "$LOG"
else
  echo "[$TS] MCP healthy" >> "$LOG"
fi
