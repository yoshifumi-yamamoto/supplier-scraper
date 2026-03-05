# Rakuten Monitoring Policy

## 方針
- RakutenはHTMLスクレイピングではなく、公式APIベースで在庫監視する。
- 既存 `baysync-rakuten-stock-scraper` の定期実行は段階的に廃止する。
- 本統合リポジトリでは `scrapers/sites/rakuten` をAPI監視実装の受け皿として維持する。

## TODO
1. 利用API仕様を確定（認証、レート制限、取得項目）
2. `apps/runner` に `--site rakuten` を追加
3. `scrape_runs / scrape_run_steps` へAPI監視結果を記録
4. ダッシュボードで `source=api` を表示
