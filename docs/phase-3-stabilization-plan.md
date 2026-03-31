# Phase 3 安定化改修計画（2026-03-25開始 / 2週間）

## 1. このフェーズの位置づけ
- `docs/unified-platform-design.md` の Phase 3 を、現在の実装状態に合わせて再定義した実行計画。
- 新機能追加より前に、運用基盤の未実装と再発ポイントを潰し切るための2週間。
- 対象期間のゴールは「通知が静かで、失敗時も原因が分かり、同じ根因で全サイトが崩れない状態」。

## 1.1 運用要件（2026-03-31 追記）
- 全サイトを `1日2回` 実行できることを明示要件とする
- 個別サイトの改善判断ではなく、`全サイト合計で 24時間内に 2サイクル完了できるか` を基準にする
- 並列数、throughput、server capacity の判断はこの要件を満たすかで決める
- 現在のサーバースペックで足りない場合は、ソフトウェア改善に加えてサーバースペック増強も許容する
- `Capacity` 表示と今後の `resource guard` は、この要件判定に使える指標を返すこと

## 2. 2026-03-25時点の棚卸し

### 2.1 完了
- `apps/runner` による統合実行入口
- `scrape_runs` / `scrape_run_steps` による run 単位の追跡
- `apps/validator_agent` による失敗検知と再試行の土台
- ダッシュボードの Overview / validator summary の最低限表示

### 2.2 部分完了
- 通知
  - 通知自体はある
  - 同一障害の抑止は今回修正したが、本番反映前
- Retry
  - 自動再試行はある
  - 根本原因別の制御、バックオフ標準化、悪化防止は未完
- DB最適化
  - `items` 取得のクエリ修正と index SQL は追加済み
  - Supabase 適用と本番反映は未実施
- ダッシュボード
  - 最新状態は見える
  - 原因分類や同種障害の集約はまだ弱い

### 2.3 未着手または未完了
- `resource guard`（並列数 / メモリ制御）
- エラー分類の標準化（db / proxy / timeout / selector / unknown）
- DB更新責務の一本化
- 回帰テストデータと再現条件の固定化
- 運用手順書の更新

## 3. 今回追加されたP0

| ID | 区分 | 優先度 | 事象 | 影響 | 対応方針 |
|---|---|---|---|---|---|
| A-004 | A | P0 | `fetch_active_items_by_domain()` が `stocking_url ilike '%domain%'` に依存し、`yahoofleama` を中心に `Supabase 57014 statement timeout` を誘発 | 複数サイト同時失敗、validator 再試行連鎖、通知多発 | `stocking_domain` 列を追加して exact match に切り替え、既存データを backfill し、本番反映後に再発確認 |
| A-005 | A | P0 | `stocking_domain` 最適化後に alias domain の吸収漏れがあると、site run が success のまま `0 items` で終わり未監視が継続する | Mercari のように `jp.mercari.com` 系 item が一括で未スクレイプ化する | domain 最適化変更時は site ごとの alias domain を明示し、`fetch_active_items_by_domain()` と adapter 呼び出しの回帰テストを同時追加する |
| A-006 | A | P0 | `scrape_runs.status=running` が process 不在のまま残留し、ダッシュボード・validator・orchestrator の状態が崩れる | 長時間の誤稼働表示、再実行阻害、障害検知遅延 | `orphaned run cleanup` と `run heartbeat` を導入し、process 不在かつ stale な run を自動回収する |

## 4. この2週間の完了条件
- `A-004` が本番で再発しない
- `A-005` として、domain alias を含む取得条件の回帰テストが mainline に入っている
- `A-006` として、orphaned / stale running run が自動回収され、何日も `running` が残らない
- 同一根因で Chatwork 通知が連打しない
- 失敗理由が最低でも `db_timeout / proxy / network / selector / unknown` に分類される
- Retry が根因を悪化させない
- `resource guard` の最小実装が入っている
- P0/P1 の担当、状態、次アクションが `md` で追跡できる

## 5. 進め方
- 優先順は `A: 実行停止系` → `C: 運用阻害系` → `B: 品質劣化系`
- 毎日「実装・検証・文書更新」を1セットで進める
- サーバー確認は KAGOYA の実ログと Supabase の実 run を基準に行う
- 途中で新しい障害が見つかっても、P0/P1 以外はこのフェーズ終了後へ回す

## 6. 日次タスク

### Day 1
- `A-004` のコード差分を整理し、デプロイ対象を確定する
- Supabase に `infra/sql/004_optimize_items_domain_lookup.sql` を適用する
- `items` 取得の変更を本番へ反映する
- `validator_agent` の通知抑止修正も同時に本番へ反映する
- 反映後、`mercari / rakuma / yahoofleama / yafuoku / secondstreet` の最新 run を確認する

### Day 2
- 本番の `scrape_runs` と `validator_agent.log` を見て、`57014` の再発有無を確認する
- `fetch_active_items_by_domain()` の取得件数と経過時間をログに出す
- `db_timeout` を明示判定できるよう、共通エラー分類の下地を入れる
- domain alias を持つサイトでは、取得条件変更時に回帰テスト追加を必須ルールとして明文化する
- 2週間用の進捗欄をこのファイルに追記開始する

### Day 3
- Retry の標準方針を決める
- `db_timeout` 時は即時多重再試行しない制御を入れる
- `proxy / network / db_timeout` で retry 条件を分ける
- validator の「再試行してよい失敗」と「人に上げるべき失敗」を整理する

### Day 4
- `scrapers/common` に共通エラー分類ヘルパーを追加する
- `runner` と主要 site adapter に分類済み error_summary を流す
- ダッシュボード API で分類済みエラーが取れる形を確認する
- `unknown` が多いサイトを1つ選び、原因の掘り下げを始める

### Day 5
- `resource guard` の最小実装方針を確定する
- 並列数とメモリ閾値をどこで制御するか決める
- `mcp_orchestrator` と `runner` の役割分担を整理する
- 今週の残件を見直し、週末時点のブロッカーを潰す
- `A-006` の設計として、`heartbeat_at` と orphan cleanup の責務分担を決める

### Day 6
- `resource guard` の実装を入れる
- 高負荷時に新規 site 起動を抑制する
- `already_running` と実際の停滞を区別できるようログを改善する
- KAGOYA 上の稼働状況確認コマンドを手順化する
- `orphaned run cleanup` を実装し、process 不在 + no step activity の `running` を `failed` 化する

### Day 7
- 主要5サイトで手動またはスモーク実行する
- `db_timeout`、`already_running`、`retry_cooldown` の挙動を確認する
- validator の通知文面を、原因別に判別しやすいよう調整する
- 失敗事例を backlog へ反映する
- `mercari` のような長時間 run が停止したときに、画面が `稼働中` のまま残らないことを確認する

### Day 8
- `B-002` の DB更新責務重複を再点検する
- 更新箇所が複数ある site を洗い出す
- まず1サイトで責務の一本化を実施するか、設計メモを確定する
- 回帰しやすい箇所に軽いテストを追加する

### Day 9
- `A-001` と `A-002` の下地対応を進める
- `out_of_stock` と `error/unknown` の扱いを整理する
- proxy 障害時の fallback と最終 error_summary を整える
- 運用での見え方が改善したかをダッシュボードで確認する

### Day 10
- 2週間の残課題を P0/P1/P2 に整理し直す
- 今回フェーズで完了扱いにできる項目を確定する
- 未完了項目は次フェーズへ移す条件を書く
- 本番運用チェックリストを更新する

## 7.1 進捗メータ統一の棚卸し（2026-03-31）

### 目的
- ダッシュボード上の `processed / total / remaining / eta` を全サイトで同じ計算で出せるようにする
- サイトごとに step 名や message 形式が違うため、表示できるサイトとできないサイトが混在している状態を解消する

### 現在の統一済みサイト
- `mercari`
- `yafuoku`
- `yahoofleama`
- `secondstreet`
- `surugaya`

共通パターン:
- `fetch_items` step を持つ
- `check:<ebay_item_id>` の per-item step を積む
- `fetch_items` の message から総件数を取りやすい

### 未統一サイト
- `rakuma`
- `hardoff`
- `kitamura`
- `yodobashi`

現状の差分:
- per-item の `check:<ebay_item_id>` ではなく、bulk の `check_stock` を使っている
- `fetch_items` の message が `fetched={N}` 形式で、他サイトの `fetched N items` と揃っていない
- そのため、ダッシュボード側で `processed / total / remaining / eta` を同一ロジックで出しづらい

### 統一方針
- 全サイトで `fetch_items` を使用する
- `fetch_items` の message は `fetched {N} items` に揃える
- 各 item 処理は `check:<ebay_item_id>` に揃える
- item 単位の失敗は step 単位で `failed` に残す
- `check_stock` のような bulk step は段階的に廃止する

### 優先順
1. `rakuma`
2. `hardoff`
3. `kitamura`
4. `yodobashi`

### 完了条件
- 全サイトで `processed / total / remaining / eta` がダッシュボードに表示される
- `display_status` と進捗メータが同じ run / step 群を基準に計算される
- 進捗表示のための site 別分岐を `dashboard_api` から減らせる

## 7.2 並列余力判断用 Capacity 表示の設計（2026-03-31）

### 目的
- `メモリ使用率` や `Swap使用率` だけでは、並列数を安全に上げられるか判断できない
- ダッシュボード上で「今どれくらい余力があり、何がボトルネックか」を見えるようにする
- 将来の `resource guard` と同じ指標を先に可視化し、制御前に観測できる状態を作る

### 画面に出す指標

#### システム余力
- `CPU使用率`
- `CPU load average (1m / 5m / 15m)`
- `メモリ使用率`
- `Swap使用率`
- `ディスク空き容量`

#### 実行中リソース
- `実行中サイト数`
- `実行中 run 数`
- `実行中 browser 数`
- `実行中 runner process 数`
- `停止疑い run 数`

#### 実行品質
- `直近1時間の成功 run 数`
- `直近1時間の失敗 run 数`
- `直近1時間の retry 数`
- `直近1時間の db_timeout 件数`
- `直近1時間の stale_running 件数`
- `直近24時間の成功率`

#### Throughput
- `site ごとの平均 run 時間`
- `site ごとの item 処理速度 (items/min)`
- `running 中 site の processed / total / remaining / eta`

### API 設計
- `GET /api/capacity`

返却案:
```json
{
  "snapshot_at": "2026-03-31T12:00:00+09:00",
  "system": {
    "cpu_percent": 21.4,
    "load_average": [1.2, 1.0, 0.9],
    "memory_percent": 18.0,
    "swap_percent": 11.0,
    "disk_free_gb": 142.3
  },
  "runtime": {
    "running_sites": 3,
    "running_runs": 3,
    "stalled_runs": 1,
    "chrome_processes": 9,
    "runner_processes": 3
  },
  "quality": {
    "success_runs_1h": 5,
    "failed_runs_1h": 1,
    "retry_runs_1h": 1,
    "db_timeout_1h": 0,
    "stale_running_1h": 1,
    "run_success_rate_24h": 0.87
  },
  "throughput": {
    "items_per_minute_running": 42.1,
    "avg_run_minutes_by_site": {
      "mercari": 181,
      "yafuoku": 132
    }
  },
  "capacity_hint": {
    "parallel_level": "caution",
    "reasons": [
      "stalled_runs=1",
      "chrome_processes=9"
    ]
  }
}
```

### 計算元
- `system`
  - `psutil.cpu_percent()`
  - `os.getloadavg()`
  - `psutil.virtual_memory()`
  - `psutil.swap_memory()`
  - `psutil.disk_usage("/")`
- `runtime`
  - `scrape_runs` の latest status
  - 既存の `_site_process_running()` と `_process_counts()`
  - `display_status == stalled`
- `quality`
  - `scrape_runs`
  - `error_summary`
  - `error_type`
  - validator summary
- `throughput`
  - `scrape_run_steps`
  - `processed_items / elapsed_minutes`

### UI 設計
- Overview の KPI の下に `Capacity` セクションを追加
- 色は `ok / caution / ng` の 3 段階
- まず数値を出し、推奨メッセージは補助表示に留める
- `メモリに余裕あり` のような曖昧文言ではなく、必ず理由も出す
  - 例: `並列増加は注意: stale run 1件 / browser 9件`

### 並列判断の初期ルール
- `ok`
  - `memory_percent < 70`
  - `swap_percent < 20`
  - `stalled_runs = 0`
  - `db_timeout_1h = 0`
  - `chrome_processes <= 8`
- `caution`
  - 上記の一部を超過しているが、重大障害ではない
- `ng`
  - `stalled_runs > 0`
  - または `db_timeout_1h > 0`
  - または `swap_percent >= 40`

### 段階的導入
1. `dashboard_api` に `GET /api/capacity` を追加
2. `dashboard-web` に `Capacity` セクションを追加
3. 数日観測してから `resource guard` の実制御へ接続する

### 完了条件
- ダッシュボードだけで「今 parallel を上げていいか」を判断できる
- `memory/swap` 以外に `db_timeout` と `stalled_runs` を見て判断できる
- 後続の `resource guard` が同じ指標を使える

## 8. 毎日の確認項目
- `validator_agent.log` に同一原因の連続通知が出ていないか
- `scrape_runs` に `57014` / `502` / `already_running` がどう出ているか
- retry が増やした run と改善した run の比率
- 主要サイトの最新成功時刻
- 新しい失敗パターンが backlog に反映されているか

## 9. このフェーズでやらないこと
- 大規模な UI 再設計
- 新サイト追加
- 重い機能開発
- Queue 基盤の全面導入

## 10. 終了時のアウトプット
- P0/P1 の状態が反映された backlog
- 本番反映済みの DB timeout 対策
- retry / notification / resource guard の最小安定版
- 次フェーズへ渡す未完了項目一覧

## 11. 実施ログ

### 2026-03-25 Day 1
- `scrapers/common/items.py` を KAGOYA 本番へ反映
- `apps/validator_agent/main.py` を KAGOYA 本番へ反映
- `infra/sql/004_optimize_items_domain_lookup.sql` をサーバー配置
- KAGOYA 上で `python3 -m py_compile scrapers/common/items.py apps/validator_agent/main.py` を実施し、構文エラーなしを確認
- KAGOYA 上で `stocking_url.ilike.*mercari.com*` を使う Supabase クエリが `200` を返すことを確認
- 反映確認:
  - `items.py` に DB側 domain filter が入っている
  - `validator_agent` に `_build_ai_notification_fingerprint()` が入っている
- 未完了:
  - `004_optimize_items_domain_lookup.sql` の Supabase 本体適用
  - 反映後 run の再発確認
- ブロッカー:
  - 現在の接続情報では SQL Editor / `psql` / Supabase CLI 経由の実行経路がなく、DB index の自動適用は未実施

### 2026-03-25 Day 2-4 前倒し
- `scrapers/common/error_classifier.py` を追加
- error type を `db_timeout / proxy / network / selector / timeout / unknown` に統一
- `runner` の transient 通知抑止を共通分類ベースに変更
- `validator_agent` の retry / skipped / failed payload に `error_type` を追加
- `validator_agent` の `scrape_runs` 取得を直近 window の `running/failed/error` のみに縮小
- `validator_agent` に `validator runs fetched` 計測ログを追加
- `items.py` に `items fetch finished` 計測ログを追加
- domain alias の回帰テストがなく、`mercari.com` / `jp.mercari.com` の吸収漏れを見逃した。今後は取得条件変更と同時にテスト追加を必須とする
- `dashboard_api` の `mcp_summary` に `error_type` を追加
- 本番反映済み:
  - `apps/runner/main.py`
  - `apps/validator_agent/main.py`
  - `apps/dashboard_api/main.py`
  - `scrapers/common/notifier.py`
  - `scrapers/common/items.py`
  - `scrapers/common/error_classifier.py`
- Supabase `EXPLAIN ANALYZE` で `scrape_runs` は軽量化済みと確認
- Supabase `EXPLAIN ANALYZE` で `yahoofleama` の `items` 取得が `ILIKE '%paypayfleamarket.yahoo.co.jp%'` により後段 filter になっていると確認
- `infra/sql/006_add_stocking_domain.sql` を追加
- `items.py` を `stocking_domain = eq.<domain>` 優先、未移行時のみ `stocking_url ilike` fallback に変更
- `scrapers/common/items.py` と `infra/sql/006_add_stocking_domain.sql` を KAGOYA へ配置

### 2026-03-28 Day 4 追記
- `yafuoku` の `Supabase 500 / statement timeout` を調査
- Supabase SQL Editor で `stocking_domain` 列と `idx_items_active_stocking_domain_item_id` の存在を確認
- `yafuoku` 対象 (`auctions.yahoo.co.jp`, `page.auctions.yahoo.co.jp`) は `stocking_domain` の backfill が完了していることを確認
- `EXPLAIN ANALYZE` により、`stocking_domain in (...) order by ebay_item_id asc limit 50` が `items_ebay_item_id_key` を選び、後段 filter になっていることを確認
- 同じ条件でも `order by` を外すと `idx_items_active_stocking_domain_item_id` が使用され、実行時間が `~5.9ms` まで落ちることを確認
- 原因整理:
  - root cause は `stocking_domain` 列不足ではなく、複数 domain を `in (...)` でまとめた query と `order by ebay_item_id` の組み合わせ
  - planner が順序優先で `items_ebay_item_id_key` を選び、広い index scan 後に domain filter していた
- 対応:
  - `scrapers/common/items.py` の複数 domain fetch を、`stocking_domain` 利用時は domain ごとの個別 query に変更
  - `stocking_domain` 未対応環境では従来どおり `stocking_url ilike.any(...)` fallback を維持
  - `tests/test_items_fetch.py` を追加し、複数 domain の個別取得と fallback を回帰テスト化
- 検証:
  - `python3 -m unittest tests.test_items_fetch tests.test_mercari_domain_fetch tests.test_site_domain_aliases`
  - 10 tests passed
