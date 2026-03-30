#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${KAGOYA_APP_DIR:-/root/supplier-scraper-main}"
DASHBOARD_WEB_DIR="$APP_DIR/apps/dashboard-web"

cd "$APP_DIR"

echo "[deploy] app_dir=$APP_DIR"

if [ -x ".venv/bin/python3" ]; then
  /bin/bash ./scripts/post_deploy_smoke.sh
fi

if [ -f "$DASHBOARD_WEB_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
  echo "[deploy] building dashboard-web"
  (
    cd "$DASHBOARD_WEB_DIR"
    npm run build
  )
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet supplier-mcp.service && systemctl restart supplier-mcp.service || true
  systemctl is-active --quiet supplier-dashboard-api.service && systemctl restart supplier-dashboard-api.service || true
  systemctl is-active --quiet marketpilot-dashboard-web.service && systemctl restart marketpilot-dashboard-web.service || true
fi

echo "[deploy] completed"
