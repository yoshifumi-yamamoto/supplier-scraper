# Bootstrap

## 1) API起動 (FastAPI)
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SUPABASE_URL="https://<project>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<service_role_key>"
uvicorn apps.dashboard_api.main:app --reload --host 0.0.0.0 --port 8080
```

### 1-1) 先に作成するテーブル
Supabase SQL Editor で次を順に実行:
- `infra/sql/001_create_scrape_runs.sql`
- `infra/sql/002_create_scrape_run_steps.sql`
- `infra/sql/003_optimize_items_fetch.sql`

## 2) Web起動 (Next.js)
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main/apps/dashboard-web
npm install
NEXT_PUBLIC_DASHBOARD_API_BASE=http://127.0.0.1:8080 npm run dev
```

## 3) Runner実行
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
# 任意: 二重起動防止ロック配置先（default: /tmp）
export RUN_LOCK_DIR=/tmp
# 任意: Linuxサーバーで stale chrome/chromedriver を掃除する場合のみ有効化
export RUNNER_PROCESS_CLEANUP=true
PYTHONPATH=. python3 apps/runner/main.py --site yahoofleama
PYTHONPATH=. python3 apps/runner/main.py --site secondstreet
```
