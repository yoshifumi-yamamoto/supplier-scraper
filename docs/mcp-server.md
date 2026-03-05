# MCP Server

## 起動
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
. .venv/bin/activate
export SUPABASE_URL="https://<project>.supabase.co"
export SUPABASE_KEY="<service_role_key>"
uvicorn apps.mcp_server.main:app --host 0.0.0.0 --port 8090
```

## KAGOYA運用(systemd)
1) サービスファイル `/etc/systemd/system/supplier-mcp.service`
```ini
[Unit]
Description=Supplier Scraper MCP Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/supplier-scraper-main
EnvironmentFile=/root/baysync-yodobashi-stock-scraper/.env
Environment=PYTHONPATH=/root/supplier-scraper-main
Environment=MCP_JOB_LOG_DIR=/tmp/supplier-mcp-jobs
ExecStart=/root/supplier-scraper-main/.venv/bin/uvicorn apps.mcp_server.main:app --host 0.0.0.0 --port 8090
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

2) 有効化
```bash
systemctl daemon-reload
systemctl enable --now supplier-mcp.service
systemctl status supplier-mcp.service
```

## Cron (推奨: 既存バッチは維持しつつ追加)
```cron
# Legacy production batch
0 0,12 * * * /bin/bash /root/run_all_scrapes.sh >> /var/log/run_all_scrapes.log 2>&1

# MCP watchdog
*/5 * * * * /bin/bash /root/supplier-scraper-main/scripts/mcp_watchdog.sh >> /var/log/supplier_mcp_watchdog.log 2>&1

# MCP runs (overlap guard in mcp_run_site.sh)
30 1,13 * * * /bin/bash /root/supplier-scraper-main/scripts/mcp_run_site.sh yahoofleama >> /var/log/mcp_yahoofleama.log 2>&1
40 1,13 * * * /bin/bash /root/supplier-scraper-main/scripts/mcp_run_site.sh secondstreet >> /var/log/mcp_secondstreet.log 2>&1
```

## 手動実行ヘルパー
```bash
# run_all_scrapes.sh 実行中は自動スキップ
# site実行
/bin/bash /root/supplier-scraper-main/scripts/mcp_run_site.sh yahoofleama
/bin/bash /root/supplier-scraper-main/scripts/mcp_run_site.sh secondstreet 1
```

## ツール一覧
```bash
curl -sS http://127.0.0.1:8090/mcp/tools
```

## ツール実行例
1) スクレイピング開始（非同期）
```bash
curl -sS -X POST http://127.0.0.1:8090/mcp/call \
  -H 'content-type: application/json' \
  -d '{"name":"run_scrape","arguments":{"site":"yahoofleama","max_pages":1}}'
```

2) ジョブ状態確認
```bash
curl -sS -X POST http://127.0.0.1:8090/mcp/call \
  -H 'content-type: application/json' \
  -d '{"name":"get_job_status","arguments":{"job_id":"<job_id>"}}'
```

3) run/step確認
```bash
curl -sS -X POST http://127.0.0.1:8090/mcp/call \
  -H 'content-type: application/json' \
  -d '{"name":"get_run_status","arguments":{"limit":5}}'

curl -sS -X POST http://127.0.0.1:8090/mcp/call \
  -H 'content-type: application/json' \
  -d '{"name":"get_run_steps","arguments":{"limit":10}}'
```

4) サーバーヘルス
```bash
curl -sS -X POST http://127.0.0.1:8090/mcp/call \
  -H 'content-type: application/json' \
  -d '{"name":"get_server_health","arguments":{}}'
```
