# supplier-scraper

統合スクレイパー基盤 + ダッシュボード（Next.js + FastAPI）の開発リポジトリ。

## 構成
- `apps/runner`: 統合パイプライン実行CLI
- `apps/dashboard_api`: ダッシュボード用API（FastAPI）
- `apps/dashboard-web`: ダッシュボードWeb（Next.js）
- `scrapers/common`: 共通ロジック（status/retry/logging）
- `scrapers/sites`: サイト別アダプタ
  - `yahoofleama`: legacy移植を段階運用
  - `rakuten`: API監視方式（スクレイピング対象外）
- `jobs/pipelines`: 統合ジョブ
- `legacy`: 既存サイト別スクレイパーの退避領域
- `docs`: 設計書・不具合台帳・スキーマ

## ダッシュボードAPI
- `GET /health`
- `GET /api/overview`
- `GET /api/runs`
- `GET /api/errors`

必要な環境変数:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`（または `SUPABASE_KEY`）

先に作成するテーブル:
- `infra/sql/001_create_scrape_runs.sql`
- `infra/sql/002_create_scrape_run_steps.sql`

## Rakuten方針
- RakutenはHTMLスクレイピングではなくAPI監視に統一する。
- 詳細は `docs/rakuten-api-monitoring.md` を参照。

## 起動
- `docs/bootstrap.md` を参照
