# 統合開発 設計書（リポジトリ統合 / 不具合修正 / GUIダッシュボード）

## 1. 目的
- 既存のサイト別スクレイパー（`baysync-*-stock-scraper`）を1つの統合リポジトリへ再編する。
- 現在発生している不具合を、場当たり対応ではなく再発防止を前提に修正する。
- 運用可視化のため、`https://baysync-dashboard.vercel.app/` を参考にしたGUIダッシュボードを構築する。
- 一括開発ではなく、段階的リリースで停止リスクを回避する。

## 2. 現状整理（2026-03-04時点）
- ルート直下にサイト別ディレクトリが複数存在。
- 多くのリポジトリで実行フローが共通:
  - `fetch_urls.py` → `split_urls.py` → `scrape_status.py` → `summarize_results.py` → `upload_to_supabase.py` → `delete_temp_data.py`
- `run_scrape.sh` もほぼ同型で、サイト名だけ差分。
- 依存管理・ログ構造・一時ファイル管理が分散しており、障害時の原因追跡が難しい。

### 2.1 確定した主要課題（エンジニア指摘反映）
- ページ読み込み失敗と在庫切れが同一扱いになっており、判定品質が毀損している。
- XPathセレクタのハードコード依存が強く、HTML変更時に広範囲で同時故障する。
- Supabase更新責務が重複しており、整合性不良が発生しうる。
- 並列実行数（12プロセス）のリソース制御が未実装で、安定稼働リスクが高い。
- プロキシ障害フォールバック、バックオフなしリトライ、cron失敗検知不全により運用で障害を見逃す。
- 2ndstreet は CSVスキーマ不一致が直接的な停止要因。
- メルカリはセレクタ変更頻発により個別修正型の保守限界が顕在化。

## 3. 統合後のゴールアーキテクチャ

### 3.1 リポジトリ構成（提案）
```text
supplier-scraper/
  apps/
    runner/                 # CLI実行エントリ（手動/cron/再実行）
    dashboard-api/          # ダッシュボード用API
    dashboard-web/          # GUIフロントエンド
  scrapers/
    common/                 # 共通基盤（HTTP, Selenium, logging, retry, parser utils）
    mercari/
    rakuma/
    rakuten/
    yafuoku/
    yahoofleama/
    yodobashi/
    hardoff/
    2ndstreet/
  jobs/
    pipelines/              # fetch/split/scrape/summarize/upload の統合ジョブ
  infra/
    cron/                   # KAGOYA cron設定テンプレート
    systemd/                # 必要なら常駐化
    sql/                    # Supabase/Postgres向けDDL・index
  docs/
```

### 3.2 設計原則
- サイト固有ロジックと共通ロジックを分離（Plugin方式）。
- すべてのジョブ実行は同じインターフェースに統一。
- 監視・再実行・追跡のため、ジョブ実行ID（run_id）を全工程で共有。
- 「失敗しても全停止しない」よりも「失敗を確実に検知・再実行できる」を優先。

### 3.3 ジョブ実行モデル
- `pipeline` を1単位として以下を順に実行:
  1. URL収集
  2. 分割
  3. スクレイピング
  4. 集計
  5. DB反映
  6. クリーンアップ
- 各ステップは `status: queued/running/success/failed` を保存。
- 中断時は「失敗ステップから再開」可能にする。

## 4. データ設計（最小）

### 4.1 テーブル案
- `scrape_runs`
  - `id`, `site`, `started_at`, `finished_at`, `status`, `trigger_type`, `error_summary`
- `scrape_run_steps`
  - `run_id`, `step_name`, `status`, `started_at`, `finished_at`, `message`
- `scrape_run_metrics`
  - `run_id`, `total_urls`, `success_count`, `failed_count`, `duration_sec`
- `scrape_errors`
  - `run_id`, `site`, `url`, `error_type`, `error_message`, `first_seen_at`

### 4.2 ログ方針
- 形式はJSON Linesで統一。
- 最低限の共通キー:
  - `timestamp`, `run_id`, `site`, `step`, `level`, `message`, `context`
- KAGOYAサーバー上では日次ローテーション。

## 5. 不具合修正方針（先に土台を整えてから修正）

### 5.1 既存不具合の分類
- `A: 実行停止系`（例: Selenium起動失敗、環境変数欠落）
- `B: 品質劣化系`（誤判定、更新漏れ、重複更新）
- `C: 運用阻害系`（ログ不足、再現不可、手動復旧前提）

### 5.2 修正優先順位
1. A（停止系）
2. C（運用阻害系）
3. B（品質劣化系）

### 5.3 修正テンプレート
- 事象
- 再現手順
- 原因
- 修正内容
- 影響範囲
- 再発防止（テスト/監視/アラート）

## 6. GUIダッシュボード設計

### 6.1 目的
- 実行状況を「今どうなっているか」で即時把握できること。
- 障害時に、担当者がログファイルを直接掘らなくても原因候補へ到達できること。

### 6.2 画面要件（`baysync-dashboard`参考）
- Overview
  - サイト別の最新実行結果（成功/失敗/実行時間）
  - 今日の総実行回数・失敗数
- Runs
  - 実行履歴一覧（絞り込み: site/status/date）
  - run_id単位でステップ別ステータス表示
- Errors
  - エラー一覧（site, error_type, first_seen, latest_seen）
  - 同種エラーの集約
- Run Detail
  - 時系列ログ、メトリクス、失敗URL一覧
- Manual Control（将来）
  - サイト単位の手動実行、再実行

### 6.3 API要件（最小）
- `GET /api/overview`
- `GET /api/runs`
- `GET /api/runs/:runId`
- `GET /api/errors`
- `POST /api/runs/:site/retry`（第2段階以降）

## 7. KAGOYA前提の運用設計
- 実行基盤は当面 `cron + Python` を継続。
- `cron` は統合ランナー（`apps/runner`）のみを起動。
- 旧サイト別 `run_scrape.sh` は段階的に廃止。
- デプロイは「Blue/Green相当の2ディレクトリ切替」または「日時付きリリースディレクトリ + symlink」方式を採用。
- 失敗時に即ロールバックできる運用手順を先に定義する。

## 8. 移行計画（段階開発）

### Phase 0: 調査固定化（1週間）
- 既存8サイトの入力/出力/依存/エラーを棚卸し。
- 既知不具合リスト作成（優先度付き）。
- 受け入れ基準（成功率、最大処理時間、許容失敗率）確定。
- `docs/bug-backlog.md` を一次版として作成し、29件の管理台帳を運用開始。

### Phase 1: 共通基盤導入（1-2週間）
- `scrapers/common` 作成。
- 共通ロガー、設定ロード、リトライ、run_id付与を導入。
- 既存コードへの影響を最小にしてラップ移植。

### Phase 2: パイプライン統合（2週間）
- `jobs/pipelines` に統合ジョブ実装。
- まず2サイト（例: Mercari / Yafuoku）を先行移行。
- 先行2サイトで安定後、残りを水平展開。

### Phase 3: 不具合修正スプリント（並行2週間）
- A→C→Bの順に修正。
- 修正ごとに再現テスト/回帰テストを追加。

### Phase 4: ダッシュボードMVP（2週間）
- API + Webで Overview / Runs / Run Detail を先に提供。
- KAGOYA上で認証付き公開（IP制限またはBasic認証）。

### Phase 5: 運用自動化（1週間）
- アラート連携（Slack/メール）
- 自動再実行ポリシー（回数上限付き）

## 9. 技術スタック提案
- Backend/API: FastAPI もしくは Node.js (Nest/Express)
- Frontend: Next.js
- DB: 既存Supabase/Postgres活用
- Queue（必要時）: Redis + RQ/Celery または BullMQ
- 監視: Sentry + メトリクス（Prometheus互換または簡易集計）

## 10. リスクと対策
- リスク: 一気に移行して全サイト停止
  - 対策: サイト単位の段階移行、旧ジョブ温存
- リスク: Selenium/プロキシ由来の不安定
  - 対策: タイムアウト標準化、再試行、失敗URL隔離
- リスク: ダッシュボード先行で運用が増える
  - 対策: 先にデータモデル統一、UIはMVPに限定

## 11. 受け入れ基準（MVP）
- 統合ランナーから2サイト以上を同一基盤で日次実行できる。
- run_id単位で「どこで失敗したか」をUIから特定できる。
- 停止系不具合（A分類）の再発件数を移行前より50%以上削減。

## 12. 直近の実装タスク（この設計書ベース）
1. `docs/bug-backlog.md` を作成し、既知不具合をA/B/C分類で起票。
2. `scrapers/common` の雛形（config/logger/retry）を追加。
3. 先行2サイトの `main.py` を統合ランナー呼び出しへ差し替え。
4. `scrape_runs` 系テーブルを作成し、run_id記録を開始。
5. ダッシュボードMVPのAPIスキーマを確定。

---
この設計書は「一気に作り直す」のではなく「止めずに置き換える」前提です。次のステップは Phase 0 の不具合バックログ作成です。
