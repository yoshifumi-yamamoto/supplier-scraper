# Rakuten Monitoring Policy

注記:
- 詳細設計は `docs/api-stock-monitoring-design.md` へ統合した
- このファイルは `rakuten` 単独方針の短い参照メモとして残す

## 方針
- RakutenはHTMLスクレイピングではなく、公式APIベースで在庫監視する。
- 既存 `baysync-rakuten-stock-scraper` の定期実行は段階的に廃止する。
- 本統合リポジトリでは `scrapers/sites/rakuten` をAPI監視実装の受け皿として維持する。

## TODO
1. Rakuten Web Service credential を KAGOYA `.env` に設定する
2. `itemCode` 解決不能 URL の扱いを sample 検証する
3. `scrape_runs / scrape_run_steps` の本番 run を確認する
4. ダッシュボードで `source=api` の表示を確認する

## 現在の env 契約
- `RAKUTEN_APPLICATION_ID`
- `RAKUTEN_ACCESS_KEY`
- `RAKUTEN_AFFILIATE_ID`
- `RAKUTEN_BASE_URL`
- `RAKUTEN_SITE_KEY`

## API endpoint
- 既定 endpoint は `https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401`
- 初回疎通は `keyword` で確認し、`itemCode` は最小パラメータで使う
