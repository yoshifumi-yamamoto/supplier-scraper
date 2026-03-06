# Validator Agent

失敗runを監視し、`transient` エラー（timeout / 57014 / proxy系）を検知した場合に  
MCP経由で `retry_failed_step` を呼び出す自動改善エージェントです。

## 実行
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
. .venv/bin/activate
PYTHONPATH=. python3 apps/validator_agent/main.py
```

## 主要環境変数
- `VALIDATOR_LOOKBACK_MINUTES` (default: `720`)
- `VALIDATOR_SITE_ALLOWLIST` (default: `yahoofleama,secondstreet`)
- `VALIDATOR_AUTO_RETRY` (default: `true`)
- `VALIDATOR_RETRY_MAX_PAGES` (default: `1`)
- `MCP_BASE_URL` (default: `http://127.0.0.1:8090`)

## サーバーcron例
```cron
*/15 * * * * cd /root/supplier-scraper-main && . .venv/bin/activate && PYTHONPATH=. python3 apps/validator_agent/main.py >> /var/log/validator_agent.log 2>&1
```

