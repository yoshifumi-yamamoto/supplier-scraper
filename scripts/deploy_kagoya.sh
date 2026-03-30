#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${KAGOYA_APP_DIR:-/root/supplier-scraper-main}"

cd "$APP_DIR"

echo "[deploy] app_dir=$APP_DIR"

if [ -x ".venv/bin/python3" ]; then
  /bin/bash ./scripts/post_deploy_smoke.sh
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet supplier-mcp.service && systemctl restart supplier-mcp.service || true
fi

echo "[deploy] completed"
