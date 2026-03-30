#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${KAGOYA_APP_DIR:-/root/supplier-scraper-main}"

cd "$APP_DIR"

echo "[post-deploy-smoke] app_dir=$APP_DIR"

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/supplier-scraper-pycache}"
mkdir -p "$PYTHONPYCACHEPREFIX"

.venv/bin/python3 -m py_compile \
  scrapers/common/error_classifier.py \
  scrapers/common/error_text.py \
  scrapers/common/notifier.py \
  scrapers/common/run_store.py \
  scrapers/common/items.py \
  apps/runner/main.py \
  apps/validator_agent/main.py \
  scrapers/sites/yafuoku/adapter.py \
  scrapers/sites/yahoofleama/adapter.py

.venv/bin/python3 - <<'PY'
from scrapers.sites.registry import list_sites
from scrapers.common.error_classifier import classify_error
from scrapers.common.notifier import should_notify_failure

sites = set(list_sites())
required = {"mercari", "yafuoku", "yahoofleama"}
missing = sorted(required - sites)
if missing:
    raise SystemExit(f"missing sites in registry: {missing}")

assert classify_error("Supabase 500 statement timeout") == "db_timeout"
assert not should_notify_failure("Supabase 500 statement timeout")
assert should_notify_failure("unexpected parser mismatch")

print("post_deploy_import_smoke_ok")
PY

echo "[post-deploy-smoke] completed"
