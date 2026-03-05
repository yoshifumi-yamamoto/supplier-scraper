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
