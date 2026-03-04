# supplier-scraper

統合スクレイパー基盤 + ダッシュボード（Next.js + FastAPI）の開発リポジトリ。

## 構成
- `apps/runner`: 統合パイプライン実行CLI
- `apps/dashboard_api`: ダッシュボード用API（FastAPI）
- `apps/dashboard-web`: ダッシュボードWeb（Next.js）
- `scrapers/common`: 共通ロジック（status/retry/logging）
- `scrapers/sites`: サイト別アダプタ
- `jobs/pipelines`: 統合ジョブ
- `legacy`: 既存サイト別スクレイパーの退避領域
- `docs`: 設計書・不具合台帳・スキーマ

## ダッシュボードAPI
- `GET /health`
- `GET /api/overview`
- `GET /api/runs`
- `GET /api/errors`

## 起動
- `docs/bootstrap.md` を参照
