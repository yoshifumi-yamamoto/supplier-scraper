#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${KAGOYA_APP_DIR:-/root/supplier-scraper-main}"
DASHBOARD_WEB_DIR="$APP_DIR/apps/dashboard-web"

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

if [ -d "$DASHBOARD_WEB_DIR/app" ] && command -v node >/dev/null 2>&1; then
  node - <<'JS'
const fs = require("fs");
const page = fs.readFileSync("apps/dashboard-web/app/page.tsx", "utf8");
const required = [
  "開始時刻",
  "経過時間",
  "次回予定",
  "成功 / 失敗 / 実行中",
  "残件 / 完了見込み",
];
const missing = required.filter((text) => !page.includes(text));
if (missing.length) {
  throw new Error(`dashboard page missing labels: ${missing.join(", ")}`);
}
console.log("post_deploy_dashboard_smoke_ok");
JS
fi

echo "[post-deploy-smoke] completed"
