#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${KAGOYA_APP_DIR:-/root/supplier-scraper-main}"

cd "$APP_DIR"

echo "[deploy] app_dir=$APP_DIR"

if [ -x ".venv/bin/python3" ]; then
  .venv/bin/python3 -m py_compile \
    scrapers/common/items.py \
    scrapers/sites/yafuoku/adapter.py \
    apps/runner/main.py \
    apps/validator_agent/main.py
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet supplier-mcp.service && systemctl restart supplier-mcp.service || true
fi

echo "[deploy] completed"
