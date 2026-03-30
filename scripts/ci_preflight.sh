#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[preflight] root=$ROOT_DIR"

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/supplier-scraper-pycache}"
mkdir -p "$PYTHONPYCACHEPREFIX"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
fi

"$PYTHON_BIN" -m py_compile \
  scrapers/common/error_classifier.py \
  scrapers/common/error_text.py \
  scrapers/common/notifier.py \
  scrapers/common/run_store.py \
  scrapers/common/items.py \
  apps/runner/main.py \
  apps/validator_agent/main.py \
  scrapers/sites/yafuoku/adapter.py \
  scrapers/sites/yahoofleama/adapter.py

"$PYTHON_BIN" - <<'PY'
from scrapers.sites.registry import list_sites

sites = set(list_sites())
required = {"mercari", "yafuoku", "yahoofleama"}
missing = sorted(required - sites)
if missing:
    raise SystemExit(f"missing sites in registry: {missing}")

from scrapers.common.error_classifier import classify_error, is_transient_error
from scrapers.common.notifier import should_notify_failure

assert classify_error("Supabase 500 statement timeout") == "db_timeout"
assert is_transient_error("read timed out")
assert should_notify_failure("fatal parser mismatch")
assert not should_notify_failure("Supabase 500 statement timeout")

print("python_import_smoke_ok")
PY

"$PYTHON_BIN" -m unittest tests.test_items_fetch tests.test_mercari_domain_fetch tests.test_site_domain_aliases

git ls-files --error-unmatch \
  apps/runner/main.py \
  apps/validator_agent/main.py \
  scrapers/common/error_classifier.py \
  scrapers/common/error_text.py \
  scrapers/common/notifier.py \
  scrapers/common/run_store.py \
  scrapers/common/items.py \
  scrapers/sites/yafuoku/adapter.py \
  scrapers/sites/yahoofleama/adapter.py \
  >/dev/null

echo "[preflight] completed"
