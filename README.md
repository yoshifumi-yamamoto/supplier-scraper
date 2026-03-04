# supplier-scraper

統合スクレイパー基盤 + ダッシュボードの開発リポジトリ。

## 構成
- `apps/runner`: 統合パイプライン実行CLI
- `apps/dashboard_api`: ダッシュボード用API（FastAPI）
- `apps/dashboard-web`: ダッシュボードWeb（静的MVP）
- `scrapers/common`: 共通ロジック（status/retry/logging）
- `scrapers/sites`: サイト別アダプタ
- `jobs/pipelines`: 統合ジョブ
- `legacy`: 既存サイト別スクレイパーの退避領域
- `docs`: 設計書・不具合台帳

## 初期方針
- 既存環境は止めず、統合基盤で並走検証して切替。
- まず `yahoofleama` と `2ndstreet` を先行移植。

## 次アクション
1. `legacy/` へ既存コードを取り込み
2. `apps/runner` からサイト別アダプタを呼び出す
3. `apps/dashboard_api` で run/error API を提供
