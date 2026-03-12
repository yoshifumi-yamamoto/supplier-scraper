# Bootstrap

## 0) KAGOYA SSH接続
旧 `supplier-scraper/docs/ssh-access.md` から移植。

```bash
ssh -i ~/.ssh/kagoya-backend-key.pem root@133.18.43.105
```

接続メモ:
- 秘密鍵ファイル: `~/.ssh/kagoya-backend-key.pem`
- 接続ユーザー: `root`
- 接続先IP: `133.18.43.105`

## 1) API起動 (FastAPI)
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SUPABASE_URL="https://kmwyjsvjwtxqqvgrccxh.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imttd3lqc3Zqd3R4cXF2Z3JjY3hoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0MTI2ODUwNiwiZXhwIjoyMDU2ODQ0NTA2fQ.fqqYPRvfH1qqliml3DHYtIpS0jPJXS9JdcrnBJ5ZXr8"
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

## 2-1) MCPサーバー起動
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
. .venv/bin/activate
uvicorn apps.mcp_server.main:app --host 0.0.0.0 --port 8090
```
詳細: `docs/mcp-server.md`

## 2-2) 統合オーケストレータ起動（推奨）
固定時刻でサイトごとに並列起動する代わりに、1つのcronから順次実行します。

```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
chmod +x scripts/mcp_orchestrator.sh
```

### 設定可能な環境変数
- `MCP_SITES_CSV`: 実行順（default: `mercari,yafuoku,hardoff,yodobashi,rakuma,yahoofleama,secondstreet`）
- `MCP_SITE_TIMEOUT_SEC`: 1サイトの最大実行秒（default: `5400`）
- `MCP_DEFAULT_INTERVAL_MIN`: 各サイトの最小実行間隔（default: `720`=12h）
- `MCP_INTERVAL_<SITE>_MIN`: サイト個別間隔（例: `MCP_INTERVAL_MERCARI_MIN=360`）

### cron設定例（10分ごとに起動、内部でクールダウン判定）
```cron
*/10 * * * * /bin/bash /root/supplier-scraper-main/scripts/mcp_orchestrator.sh >> /var/log/mcp_orchestrator.log 2>&1
```

## 3) Runner実行
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
# 任意: 二重起動防止ロック配置先（default: /tmp）
export RUN_LOCK_DIR=/tmp
# 任意: Linuxサーバーで stale chrome/chromedriver を掃除する場合のみ有効化
export RUNNER_PROCESS_CLEANUP=true
# 任意: 異常時にChatwork通知
export CHATWORK_NOTIFY_ENABLED=true
export CHATWORK_API_TOKEN="<chatwork_api_token>"
export CHATWORK_ROOM_ID="<chatwork_room_id>"
PYTHONPATH=. python3 apps/runner/main.py --site yahoofleama
PYTHONPATH=. python3 apps/runner/main.py --site secondstreet
```

## 4) Validator Agent実行
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
. .venv/bin/activate
PYTHONPATH=. python3 apps/validator_agent/main.py
```

## 5) Mercari商品情報抽出
検索結果ページから商品URLを順次開き、CSVへ出力します。

```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
. .venv/bin/activate
python3 scripts/mercari_extract_search.py \
  --search-url 'https://jp.mercari.com/search?search_condition_id=1cx0zHHN0HTEcY2lkHTc3OBxiaWQdMzYzMDAcax0xLzQ4HGVrHeOCu-ODg-ODiCDjg4fjgqvjg7zjg6s' \
  --output samples/mercari_extract.csv \
  --max-pages 2 \
  --headless
```

出力列:
- `タイトル`
- `価格`
- `画像`
- `CustomLabel`
- `アイテムスペック用`
- `ブランド`
- `サイズ`
- `出品者`
