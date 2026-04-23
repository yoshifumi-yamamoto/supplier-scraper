# 改修履歴

目的:
- 「何を変えたか」だけでなく「なぜ変えたか」「何を確認して判断したか」を残す
- 同じ論点を後で再調査しなくて済むようにする
- domain 条件、retry、通知、DB query のような再発しやすい改修でデグレを防ぐ

運用ルール:
- 挙動変更を伴う改修では、このファイルか該当計画書に最低1件は記録する
- 1件につき残す内容は `日付 / 事象 / 原因 / 対応 / 検証 / 残課題`
- その場しのぎの対処でも、採用理由と戻し条件を書く
- 関連する回帰テストを追加した場合は、テスト名も残す
- 障害通知を受けて調査した事象は、修正の有無に関係なく記録する
- 同一障害の再発時は、新規エントリを追加するか、既存エントリに「再発条件」と「追加対応」を追記する

---

## 2026-04-23

### dashboard API の Supabase 障害を degraded 応答 + 通知に変更
- 事象:
  - `supplier-dashboard-api.service` は起動していても、Supabase DNS/到達障害で `/api/overview` や `/api/mcp/summary` が 500 になり、frontend 全体が壊れて見えた
- 原因:
  - dashboard API は upstream 失敗時にそのまま 500 JSON を返しており、frontend は fallback を持っていても API 側の情報が乏しく、障害検知も API レイヤではしていなかった
- 対応:
  - `apps/dashboard_api/main.py`
  - `overview` / `system_schedule` / `capacity` / `mcp_summary` / `validator_summary` で、Supabase 失敗時は 500 ではなく degraded fallback JSON を返すよう変更
  - `db_timeout` / `network` / `timeout` を検知した場合は Chat 通知するよう追加
  - 通知は `/tmp/dashboard_api_alert_state.json` を使って cooldown する
- 検証:
  - `python3 -m py_compile apps/dashboard_api/main.py`
- 残課題:
  - KAGOYA 反映後に、意図的に upstream を落とした状態で frontend が崩れず degraded 表示になるか確認する
  - cooldown 秒数 (`DASHBOARD_ALERT_COOLDOWN_SECONDS`) の調整

### KAGOYA DNS 障害の恒久原因を追記
- 事象:
  - reboot 前、`dig kmwyjsvjwtxqqvgrccxh.supabase.co` が `SERVFAIL` / timeout
  - `curl https://...supabase.co` が `Could not resolve host`
- 原因:
  - VM 上の `systemd-resolved` / network state が不安定化
  - さらに `/etc/netplan/50-cloud-init.yaml` と `/run/systemd/network/10-netplan-eth0.network` に KAGOYA DNS が固定されており、public DNS 変更は reboot で戻る構成だった
- 対応:
  - VM reboot で一時復旧
  - 原因と再発条件を docs に明記
- 残課題:
  - cloud-init / netplan の恒久 DNS 上書き方針を決める
  - resolver 不調を監視するヘルスチェックを追加する

## 2026-03-28

### `fetch_active_items_by_domain()` の複数 domain query を修正
- 事象:
  - `yafuoku` で `Supabase 500 / statement timeout` が繰り返し発生
- 原因:
  - `stocking_domain` 列と index は存在していたが、複数 domain を `stocking_domain in (...)` でまとめ、さらに `order by ebay_item_id asc` を付けた query だと planner が `idx_items_active_stocking_domain_item_id` ではなく `items_ebay_item_id_key` を選んでいた
  - その結果、広い index scan の後に domain filter を掛ける形になり、`limit 50` でも遅かった
- 確認:
  - `EXPLAIN ANALYZE` で `order by` ありは約 `828ms`
  - `order by` なしは `idx_items_active_stocking_domain_item_id` を使い約 `5.9ms`
  - `yafuoku` 対象 item の `stocking_domain` backfill は `10719 / 10719` で完了
- 対応:
  - `scrapers/common/items.py`
  - `stocking_domain` 利用時かつ複数 domain の場合は、domain ごとに個別 query を発行して結果を結合するよう変更
  - `stocking_domain` が使えない環境では、従来どおり `stocking_url ilike.any(...)` fallback を維持
- 検証:
  - `python3 -m unittest tests.test_items_fetch tests.test_mercari_domain_fetch tests.test_site_domain_aliases`
  - `tests/test_items_fetch.py`
  - `tests/test_mercari_domain_fetch.py`
  - `tests/test_site_domain_aliases.py`
- 残課題:
  - 本番反映後に `items fetch finished` の `elapsed_ms` と `match_mode` を確認する
  - `yafuoku` の最新 run で `statement timeout` が消えるか確認する

### `push -> deploy` を前提にした KAGOYA デプロイ導線を追加
- 事象:
  - `yafuoku` 障害の調査で、本番 KAGOYA にローカル修正が反映されていないことが判明
- 原因:
  - 現在の運用は修正後のデプロイが手作業で、反映漏れを防ぐ構造になっていない
- 対応:
  - `.github/workflows/deploy-kagoya.yml` を追加
  - `scripts/deploy_kagoya.sh` を追加
  - `docs/deploy.md` を追加
- 目的:
  - `main` への push を KAGOYA 反映のトリガにする
  - 「直したが本番に入っていない」を運用ミスではなく構造で防ぐ
- 残課題:
  - GitHub Secrets の設定
  - KAGOYA 側 service / key の前提確認
  - DB migration を伴う変更の自動化方針

### KAGOYA deploy を `git pull` から `rsync` に切り替え
- 事象:
  - GitHub Actions 初回実行で `fatal: not a git repository` となり deploy に失敗
- 原因:
  - KAGOYA の `/root/supplier-scraper-main` は `git clone` された repo ではなく、ファイルが配置された作業ディレクトリだった
- 対応:
  - `.github/workflows/deploy-kagoya.yml` を `rsync -> remote finalize` に変更
  - `scripts/deploy_kagoya.sh` から `git fetch/pull` を削除
- 判断理由:
  - 現在の本番実体に合わせた方が早く、未デプロイ事故も防げる
  - `.env` や `.venv` を温存しつつコードだけ同期できる

## 2026-03-30

### `validator stale` と空エラー文言の再発に対する補修
- 事象:
  - `mercari` / `yafuoku` / `yahoofleama` がダッシュボード上で失敗表示
  - `yahoofleama` の最新失敗 run は `error_summary = "Message: "` で原因が読めなかった
  - `yafuoku` / `yahoofleama` では validator に stale 判定された後でも、後続で success 完走した run に古い `error_summary` が残るケースがあった
- 原因:
  - `scrapers/common/run_store.py` の `finish_run()` が success 時に `error_summary` を明示的に `null` に戻していなかった
  - `apps/runner/main.py` と一部 adapter が `str(exc)` だけを保存しており、Selenium 例外によっては `"Message:"` のような情報量ゼロの文字列になっていた
- 対応:
  - `scrapers/common/error_text.py` を追加し、`str(exc)` が空に近いときは `exc.msg` / `exc.args` / 例外型を使って説明文へ整形
  - `apps/runner/main.py` で run 失敗時の通知・保存文言にその整形結果を使用
  - `scrapers/sites/yahoofleama/adapter.py` で step 失敗時も同じ整形結果を記録
  - `scrapers/common/run_store.py` で `finish_run()` が毎回 `error_summary` を更新し、success 時は `null` に戻すよう変更
- 検証:
  - `python3 -m py_compile apps/runner/main.py scrapers/common/run_store.py scrapers/common/error_text.py scrapers/sites/yahoofleama/adapter.py`
  - `python3 -m unittest tests.test_items_fetch tests.test_mercari_domain_fetch tests.test_site_domain_aliases`
- 残課題:
  - KAGOYA 反映後に `yahoofleama` の次回失敗で空メッセージが消えるか確認
  - stale 判定そのものの閾値 (`120m`) と、実際の長時間サイトの実行特性が合っているかは別途見直しが必要

### デプロイ漏れで `runner` が `ModuleNotFoundError` を起こした件
- 事象:
  - `2026-03-30 11:14 JST` 頃、`mercari` / `yahoofleama` の手動再実行が起動直後に `ModuleNotFoundError: No module named 'scrapers.common.error_classifier'` で失敗
- 原因:
  - `scrapers/common/error_classifier.py` が local には存在したが、git 未管理のまま deploy に乗っていなかった
- 対応:
  - `scrapers/common/error_classifier.py` を repo 管理に追加して再 deploy
- 残課題:
  - deploy 後に `mercari` / `yahoofleama` を再度起動して即死しないことを確認する

### `push -> deploy` 前後に smoke test を追加
- 事象:
  - deploy 自体は成功しても、server 上で import 不足や未管理ファイル漏れにより `runner` が起動直後に落ちるケースがあった
- 原因:
  - 既存 workflow は `rsync` と最小の `py_compile` のみで、重要 import や git 管理漏れを止められていなかった
- 対応:
  - `.github/workflows/deploy-kagoya.yml` に `preflight` job を追加
  - `scripts/ci_preflight.sh` を追加
  - `scripts/post_deploy_smoke.sh` を追加
  - `scripts/deploy_kagoya.sh` から server 側 smoke を呼ぶよう変更
  - preflight では `py_compile`、重要 import、既存テスト、重要ファイルの `git ls-files` 確認を行う
- 検証:
  - `bash -n scripts/ci_preflight.sh`
  - `bash -n scripts/post_deploy_smoke.sh`
  - `bash -n scripts/deploy_kagoya.sh`
- 残課題:
  - GitHub Actions 上で `requirements.txt` を入れた状態の preflight が green になることを確認する

### preflight で `notifier.py` の未コミット差分を検出
- 事象:
  - GitHub Actions `preflight` が `ImportError: cannot import name 'should_notify_failure'` で停止
- 原因:
  - `scrapers/common/notifier.py` の `should_notify_failure()` 追加が local 変更のままで、repo に反映されていなかった
- 対応:
  - `scrapers/common/notifier.py` を正式に commit 対象へ追加
- 効果:
  - 今回のような「server に手当てしたが repo に戻していない」差分が workflow で顕在化し、そのまま deploy されなくなる

### validator の stale 判定を site 別に分離
- 事象:
  - `mercari` / `yafuoku` の新しい run が実行継続中にもかかわらず、`120m` 超過で validator に `failed` 化され続けた
- 原因:
  - `apps/validator_agent/main.py` が全サイト一律 `VALIDATOR_STALE_RUNNING_MINUTES=120` で判定していた
  - 長時間実行が普通のサイトでも、step 更新間隔や全体所要時間を考慮していなかった
- 対応:
  - `VALIDATOR_STALE_RUNNING_MINUTES_BY_SITE` を追加
  - code default として `mercari:360,yafuoku:360,yahoofleama:360` を設定
  - stale 判定、`site_running` 判定、ログ出力のすべてで site 別閾値を使用
- 検証:
  - `python3 -m py_compile apps/validator_agent/main.py`
- 残課題:
  - 本番反映後に `mercari` / `yafuoku` が `120m` ではなく `360m` までは失敗化されないことを確認する
  - さらに安全にするなら「プロセス生存 + step 更新あり」は stale 対象外に固定する

### ダッシュボードを成功率中心から運用状態中心へ変更
- 事象:
  - 画面上の `70%` や `100%` が運用判断に使えず、`running` 中の件数・残件・完了見込み・次回予定が見えなかった
- 原因:
  - API が `scrape_runs` の粗い状態しか返しておらず、`scrape_run_steps` の件数進捗や最終更新をUIに渡していなかった
- 対応:
  - `apps/dashboard_api/main.py` で latest run ごとに `scrape_run_steps` を集計
  - `processed / total / remaining / success / failed / running / eta / last_step_at / next_run_at` を返すよう変更
  - `apps/dashboard-web/app/page.tsx` を成功率主表示から、進捗件数・経過時間・次回予定・成功失敗件数中心の表示へ変更
- 検証:
  - `python3 -m py_compile apps/dashboard_api/main.py`
  - `npm run build` は local の Next SWC バイナリ読み込み制限で完走不可だったため、GitHub Actions / 本番で確認が必要
- 残課題:
  - `running` ではない最新 failed run について、直前までの件数進捗を保持して表示するかは別途検討

### ダッシュボードが古い画面のまま配信されていた件
- 事象:
  - `marketpilot.jp` のダッシュボードが plain で古いレイアウトのまま表示され、新しい進捗項目が反映されなかった
- 原因:
  - `push -> deploy` は scraper / validator 用 service しか restart しておらず、`apps/dashboard-web` の `next build` と `marketpilot-dashboard-web.service` の restart を実施していなかった
  - そのため server 上の source は更新されても、配信中の Next build は古いままだった
- 対応:
  - `scripts/deploy_kagoya.sh` に `apps/dashboard-web` の `npm run build` を追加
  - deploy 後に `supplier-dashboard-api.service` と `marketpilot-dashboard-web.service` も restart するよう変更
  - `scripts/post_deploy_smoke.sh` に dashboard 画面ラベルの存在確認を追加
- 検証:
  - `bash -n scripts/deploy_kagoya.sh`
  - `bash -n scripts/post_deploy_smoke.sh`
- 残課題:
  - 本番 deploy 後に `http://127.0.0.1:3000/` の HTML が新しい進捗ラベルを返すことを確認する

### stale run が長時間ぶら下がり、画面と実態が乖離した件
- 事象:
  - `mercari` が `2026-03-30 19:08 JST` 開始の run のまま長時間 `running` に残り、実際には step 更新が止まっていた
  - `secondstreet` / `yafuoku` も DB 上 `running` のまま残り、ダッシュボードが `稼働中` に見えていた
- 原因:
  - `scrape_runs.status` が `running` のまま残る経路があり、process 不在や長時間 no step activity を即時に回収できていなかった
  - dashboard は DB status を信用しすぎており、実プロセス有無と last step activity を十分見ていなかった
  - validator / dashboard 両方の process 判定が wrapper shell に誤反応する余地があった
- 対応:
  - dashboard API に `display_status` を追加し、`process_alive` と `last_step_at` を使って `stalled` を導出
  - `mercari` / `yafuoku` / `secondstreet` の stale run を手動で `failed` 化し、新しい run を起動
  - validator / dashboard の process 判定を `python3 apps/runner/main.py --site ...` 本体優先に修正
- 検証:
  - KAGOYA 上の `scrape_runs` と `scrape_run_steps` を直接確認
  - 古い stalled run を閉じた後、新 run が `fetch_items` / `check:*` を開始することを確認
- 残課題:
  - `orphaned run cleanup` を実装し、process 不在かつ stale な `running` を自動回収する
  - `heartbeat_at` もしくは同等の run heartbeat を導入し、step 更新がない run を早く検出できるようにする
  - `runner` の異常終了時に `finish_run(failed)` が必ず実行されるよう終了ハンドリングを強化する

### 進捗メータがサイトごとに揃っていない件を棚卸し
- 事象:
  - ダッシュボードで `processed / total / remaining / eta` が出るサイトと出ないサイトが混在していた
  - 同じ `running` でも、`mercari` / `yafuoku` / `yahoofleama` は進捗が見える一方、`rakuma` などはメータを共通計算できなかった
- 原因:
  - site adapter ごとに `scrape_run_steps` の積み方が統一されていなかった
  - 統一済みサイトは `fetch_items` + `check:<ebay_item_id>` を使っていたが、未統一サイトは bulk の `check_stock` と `fetched={N}` message を使っていた
- 確認:
  - 統一済み: `mercari`, `yafuoku`, `yahoofleama`, `secondstreet`, `surugaya`
  - 未統一: `rakuma`, `hardoff`, `kitamura`, `yodobashi`
- 対応:
  - `docs/phase-3-stabilization-plan.md` に進捗メータ統一の棚卸しと優先順を追加
  - 統一方針を `fetch_items` / `fetched {N} items` / `check:<ebay_item_id>` に固定
- 残課題:
  - `rakuma` から順に per-item step へ移行する
  - `dashboard_api` の site 別分岐を、adapter 側 step 統一後に削減する

### `rakuma` の step 記録を canonical 形式へ統一
- 事象:
  - `rakuma` は `running` でも進捗メータを共通計算できず、ダッシュボード上で件数進捗が出しづらかった
- 原因:
  - adapter が `fetch_items` の message に `fetched={N}` を使い、item 単位の `check:<ebay_item_id>` ではなく bulk の `check_stock` を積んでいた

## 2026-04-03

### 楽天・Yahoo!ショッピング・Amazon を API 監視前提で設計開始
- 事象:
  - 既存 Selenium サイトの最適化を進めつつ、次段で `楽天市場 / Yahoo!ショッピング / Amazon` の在庫監視を追加したい要求が出た
- 判断:
  - 新規3サイトまで Selenium で増やすと、`1日2回` 要件に対して CPU コストが重すぎる
  - 新規 site は API 優先で別レーン設計にする方が、throughput と安定性の面で有利
- 対応:
  - `docs/api-stock-monitoring-design.md` を新設
  - `rakuten / yahoo_shopping / amazon` を共通の `client -> normalizer -> adapter` 構成で追加する方針を明文化
  - `phase-3` にも「新規3サイトは API 監視前提」として追記
- 残課題:
  - `rakuten` の認証方式と item 主キーの確定
  - `Yahoo!ショッピング` の item 識別子を URL から解決できるか確認
  - `Amazon` で利用可能な API と credential の保有状況確認
- 対応:
  - `scrapers/sites/rakuma/adapter.py` を修正
  - `fetch_items` の success message を `fetched {N} items` に統一
  - item ごとに `check:<ebay_item_id>` step を積むよう変更
  - check 失敗時も item 単位で `不明` 更新と step 完了を残すよう変更
- 検証:
  - `python3 -m unittest tests.test_rakuma_step_progress tests.test_site_domain_aliases`
  - `python3 -m py_compile scrapers/sites/rakuma/adapter.py`
- 残課題:
  - 同じ形式へ `hardoff` / `kitamura` / `yodobashi` を順に揃える

### `hardoff` の step 記録を canonical 形式へ統一
- 事象:
  - `hardoff` は `running` でも進捗メータを共通計算できず、ダッシュボード上で件数進捗が出しづらかった
- 原因:
  - adapter が `fetch_items` の message に `fetched={N}` を使い、item 単位の `check:<ebay_item_id>` ではなく bulk の `check_stock` を積んでいた
- 対応:
  - `scrapers/sites/hardoff/adapter.py` を修正
  - `fetch_items` の success message を `fetched {N} items` に統一
  - item ごとに `check:<ebay_item_id>` step を積むよう変更
  - check 失敗時も item 単位で `不明` 更新と step 完了を残すよう変更
- 検証:
  - `python3 -m unittest tests.test_hardoff_step_progress tests.test_site_domain_aliases`
  - `python3 -m py_compile scrapers/sites/hardoff/adapter.py`
- 残課題:
  - 同じ形式へ `kitamura` / `yodobashi` を順に揃える

### `kitamura` の step 記録を canonical 形式へ統一
- 事象:
  - `kitamura` は `running` でも進捗メータを共通計算できず、ダッシュボード上で件数進捗が出しづらかった
- 原因:
  - adapter が `fetch_items` の message に `fetched={N}` を使い、item 単位の `check:<ebay_item_id>` ではなく bulk の `check_stock` を積んでいた
- 対応:
  - `scrapers/sites/kitamura/adapter.py` を修正
  - `fetch_items` の success message を `fetched {N} items` に統一
  - item ごとに `check:<ebay_item_id>` step を積むよう変更
  - check 失敗時も item 単位で `不明` 更新と step 完了を残すよう変更
- 検証:
  - `python3 -m unittest tests.test_kitamura_step_progress tests.test_site_domain_aliases`
  - `python3 -m py_compile scrapers/sites/kitamura/adapter.py`
- 残課題:
  - 同じ形式へ `yodobashi` を揃える

### `yodobashi` の step 記録を canonical 形式へ統一
- 事象:
  - `yodobashi` は `running` でも進捗メータを共通計算できず、ダッシュボード上で件数進捗が出しづらかった
- 原因:
  - adapter が `fetch_items` の message に `fetched={N}` を使い、item 単位の `check:<ebay_item_id>` ではなく bulk の `check_stock` を積んでいた
- 対応:
  - `scrapers/sites/yodobashi/adapter.py` を修正
  - `fetch_items` の success message を `fetched {N} items` に統一
  - item ごとに `check:<ebay_item_id>` step を積むよう変更
  - check 失敗時も item 単位で `不明` 更新と step 完了を残すよう変更
- 検証:
  - `python3 -m unittest tests.test_yodobashi_step_progress tests.test_site_domain_aliases`
  - `python3 -m py_compile scrapers/sites/yodobashi/adapter.py`
- 残課題:
  - 今回の棚卸し対象 `rakuma / hardoff / kitamura / yodobashi` は adapter 形式の統一が完了

### 並列余力判断用 Capacity 表示の設計を追加
- 事象:
  - ダッシュボードに `メモリ使用率` と `Swap使用率` は出ているが、並列数を安全に上げられるかの判断材料としては不足していた
- 原因:
  - 現状の画面は `system memory` と `run status` を別々に見せており、`db_timeout` / `stalled_runs` / browser 数 / throughput を同じ文脈で見られなかった
- 対応:
  - `docs/phase-3-stabilization-plan.md` に `Capacity` セクションの設計を追加
  - `GET /api/capacity` の返却案、計算元、UI 要件、初期しきい値を定義
- 狙い:
  - 先に観測指標を固め、その後 `resource guard` の制御指標と揃える
- 残課題:
  - `dashboard_api` 実装
  - `dashboard-web` の `Capacity` セクション追加
  - 数日観測したうえで並列数増加の判断ルールを見直す

### Capacity API と Overview 表示を実装
- 事象:
  - 並列数を上げる判断材料がダッシュボード上に不足していた
- 対応:
  - `apps/dashboard_api/main.py` に `GET /api/capacity` を追加
  - `apps/dashboard-web/lib/api.ts` に `CapacitySummary` 型と fetch を追加
  - `apps/dashboard-web/app/page.tsx` に `Capacity` パネルを追加
- 表示内容:
  - `cpu/load`
  - `memory/swap`
  - `running sites/runs`
  - `stalled runs`
  - `chrome/runner`
  - `success/fail/retry/db_timeout/stale (1h)`
  - `run success (24h)`
  - `items/min`
  - `parallel_level` と理由
- 検証:
  - `python3 -m py_compile apps/dashboard_api/main.py`
  - `npm run build` は local の Next SWC バイナリ制限で失敗。GitHub Actions / 本番 build で確認が必要
- 残課題:
  - `resource guard` と同じしきい値に揃える
  - 数日観測して `parallel_level` の条件を補正する

### `mercari` の item 処理速度を改善
- 事象:
  - `mercari` が `4万件超` の run で `1時間42分で 987 件` と遅く、完了見込みが `約3日` に伸びていた
- 原因:
  - item ごとに Selenium で `driver.get()` と `wait_ready()` を行ううえ、標準判定で `WebDriverWait(..., 3)` を毎回使っていた
  - さらに browser を `12件ごと` に再生成しており、安定化の代償として throughput が落ちていた
- 対応:
  - `scrapers/sites/mercari/adapter.py`
    - `MERCARI_REBUILD_EVERY` を導入し、default を `30` に変更
  - `scrapers/sites/mercari/checker.py`
    - `MERCARI_PURCHASE_WAIT_SECONDS` の default を `1.5`
    - `MERCARI_REFRESH_RETRY_WAIT_SECONDS` の default を `1.5`
    - 購入ボタン待機と refresh 後再判定の待ち時間を短縮
- 検証:
  - `python3 -m unittest tests.test_mercari_domain_fetch tests.test_site_domain_aliases`
  - `python3 -m py_compile scrapers/sites/mercari/adapter.py scrapers/sites/mercari/checker.py`
- 残課題:
  - 本番の `items/min` と `eta` が改善するかを確認する
  - まだ遅い場合は `update_item_stock()` の batch 化を検討する

### commit / push の手順をスクリプト化
- 事象:
  - `git commit` 後に `Everything up-to-date` と見えるズレが繰り返し発生した
- 原因:
  - `git commit` と `git push` を並列で流しており、`push` が先に走ることがあった
  - 加えて `.git/index.lock` が頻発し、commit 失敗後に次の操作へ進みやすかった
- 対応:
  - `scripts/safe_commit_push.sh` を追加
  - `docs/deploy.md` に Git 運用ルールと利用例を追記
- 効果:
  - `index.lock` がある状態で進まない
  - commit / push を直列化できる
  - push 後に `HEAD == origin/main` まで検証できる
- 残課題:
  - 今後の commit / push はこのスクリプトに寄せる

### 性能判断の基準を「全サイトを1日2回」へ修正
- 事象:
  - `mercari` の throughput 改善を個別サイト単位で見てしまい、全体要件に対して十分かの判断が抜けていた
- 原因:
  - `1日2回` の対象を個別サイトの完走時間として扱ってしまい、`全サイト合計で 24時間内に 2サイクル` という本来要件を docs に明示していなかった
- 対応:
  - `docs/phase-3-stabilization-plan.md` に運用要件を追加
  - 今後は並列数、throughput、server capacity の判断をこの要件基準で行う
- 残課題:
  - 全サイトの現状所要時間を一覧化する
  - `1日2回` 達成に必要な並列数と server capacity を算出する

### Mercari の item 更新を batch 化して DB 往復を削減
- 事象:
  - `mercari` の run が `4万件超` の対象に対して極端に長く、ダッシュボード ETA が `52時間` 級になっていた
- 原因:
  - item ごとに `update_item_stock()` を即時実行しており、Selenium 処理に加えて DB 更新往復が `4万回` 近く発生していた
- 対応:
  - `scrapers/common/items.py` に `update_item_stock_bulk()` を追加
  - `scrapers/sites/mercari/adapter.py` で item 更新を batch 化し、既定 `50件` ごとに flush するよう変更
  - browser 再生成前と run 終了時にも pending update を flush するようにした
  - `tests/test_mercari_domain_fetch.py` に batch 更新の回帰テストを追加
- 残課題:
  - 本番 run の `items/min` と ETA がどこまで改善したかを測定する
  - 必要なら batch サイズと worker 数を再調整する

### Mercari を site 内並列化して browser 直列処理を緩和
- 事象:
  - batch 更新導入後も `mercari` の `avg_step_sec` は約 `4.5秒` で、ETA がなお `50時間` 超だった
- 原因:
  - `mercari` は 1 run 内で 1 browser が全 item を直列処理しており、DB 往復を減らしても Selenium 側の待ち時間が支配的だった
- 対応:
  - `scrapers/sites/mercari/adapter.py` に worker 分割を追加し、既定 `3 browser workers` で item 群を分散処理するよう変更
  - `MERCARI_BROWSER_WORKERS` で worker 数を調整できるようにした
  - `tests/test_mercari_domain_fetch.py` に chunk 分割の回帰テストを追加
- 残課題:
  - 本番の `chrome_processes` と `items/min` を見て worker 数 `3` が妥当か確認する
  - server capacity が許すなら `4` 以上への引き上げを検討する

### Mercari の page ready 後 sleep を site 限定で短縮
- 事象:
  - `mercari` は item ごとに `wait_ready()` の既定 `2秒 sleep` を踏んでおり、browser worker を増やしても step 秒数が下がり切らなかった
- 原因:
  - `scrapers/common/browser.py` の共通 `wait_ready()` が全サイト向けに保守的で、Mercari の item 単位巡回には長すぎた
- 対応:
  - `scrapers/sites/mercari/checker.py` で `MERCARI_READY_SLEEP_SECONDS` を追加
  - `wait_ready(driver, sleep_sec=...)` を使って、Mercari だけ既定 `0.4秒` に短縮
- 残課題:
  - shops 系 URL で false negative が増えないか本番 run で確認する

### Mercari を shard 実行できるようにして同一サイト並列の土台を追加
- 事象:
  - `worker=3` と `ready_sleep=0.4` まで詰めても、Mercari 1 run の ETA がなお `30時間` 級で、全サイト 1日2回の要件を満たせなかった
- 原因:
  - `mercari` は 1 run = 全 item が前提で、複数 run に水平分割できず、同一サイトの処理量を複数 run に逃がせなかった
- 対応:
  - `apps/runner/main.py` に `--shard-index` / `--shard-total` を追加
  - `scrapers/common/execution_guard.py` で shard ごとに別 lock を取れるよう変更
  - `scrapers/sites/mercari/adapter.py` で shard index/total に応じて対象 item を分割するよう変更
  - `apps/dashboard_api/main.py` で同一サイトの複数 running run を合算表示できるよう変更
- 残課題:
  - orchestrator から shard 起動するか、当面は手動 shard 起動で運用するかを決める
  - dashboard UI に `active_run_count` を出すか判断する
  - 現状は `2 shard` で観測し、件数増加に備えて `3 shard` を次段候補として plan に保持する

### Yahoo系サイトの stock pipeline を共通化しつつ batch 更新と待機短縮を導入
- 事象:
  - `yafuoku` と `yahoofleama` はどちらも 1 item ごとの即時 DB 更新と保守的な待機を使っており、全サイト 1日2回の要件に対して throughput が不足していた
- 原因:
  - adapter の構造がほぼ同じなのに共通化されておらず、Mercari で効いた最適化を横展開しづらかった
- 対応:
  - `scrapers/common/selenium_stock_pipeline.py` を追加し、`fetch -> browser loop -> batch update -> rebuild_every` を共通 helper 化
  - `yafuoku` と `yahoofleama` の adapter を helper 利用へ置き換え
  - 両 checker に site 別 `READY_SLEEP_SECONDS` / `BUY_WAIT_SECONDS` を追加して既定待機を短縮
  - `tests/test_yahoo_stock_pipeline.py` を追加
- 残課題:
  - 本番で `items_per_min` がどこまで改善するか確認する
  - 効果が不足する場合は `yafuoku` を shard 候補に上げる
### Dashboard API の step 集計を 1000 行上限からページング対応へ修正

- 事象:
  - `mercari` / `yafuoku` / `yahoofleama` の進捗が `999` 件で頭打ちに見えた
  - 実際には `scrape_run_steps` は増え続けていたが、ダッシュボード API が先頭 1000 行しか読めていなかった
- 原因:
  - Supabase REST の実効取得上限をまたいだ時に `apps/dashboard_api/main.py` の `_fetch_run_steps()` が 1 リクエストで終了していた
- 対応:
  - `_fetch_run_steps()` を `offset + limit` のページングに変更
  - `RUN_STEPS_PAGE_SIZE` を環境変数化
  - 回帰用に `tests/test_dashboard_api_run_steps.py` を追加
- 残課題:
  - KAGOYA 反映後に `/api/mcp/summary` の `processed_items` が `999` を超えて追随することを確認する

### Yahoo 系共通 stock pipeline に shard 対応を追加

- 事象:
  - `yafuoku` は最適化後でも約 `12.7 items/min` で、約 `10.5時間` 級の完了見込みだった
  - 全サイト 1 日 2 回の要件を考えると、余裕が薄い
- 対応:
  - `scrapers/common/selenium_stock_pipeline.py` に `SCRAPER_SHARD_INDEX` / `SCRAPER_SHARD_TOTAL` ベースの shard 分割を追加
  - `apps/runner/main.py --shard-index/--shard-total` で Yahoo 系もそのまま分割実行できるようにした
  - `_select_shard_items()` の単体テストを追加
- 方針:
  - まず `yafuoku` を `2 shard` で計測
  - まだ不足なら `mercari` と同様に shard 数を段階的に上げる
### Mercari 実行中は他サイトを自動起動しない orchestrator ガードを追加

- 目的:
  - Mercari 3 shard 計測中に他サイト起動で CPU 競合させない
- 対応:
  - `scripts/mcp_orchestrator.sh` に `MCP_BLOCK_OTHER_SITES_WHEN_MERCARI_RUNNING` を追加
  - `mercari` が running の間は他サイトを `mercari_running_guard` で skip
- 備考:
  - 既定は `true`。運用で戻す時は env で `false` にできる

### Mercari shard 実行が import 時環境変数読込で無効化されていた問題を修正

- 事象:
  - `manual_shard_1_of_3` / `2_of_3` / `3_of_3` なのに各 run の `fetch_items` が全て `fetched 41260 items` になっていた
  - 3 shard で動いているように見えても、実際には各 shard が全件を処理していた
- 原因:
  - `scrapers/sites/mercari/adapter.py` が `SCRAPER_SHARD_INDEX` / `SCRAPER_SHARD_TOTAL` を module import 時に読み込んでいた
  - `apps/runner/main.py` は site adapter import 後に shard 環境変数をセットするため、既定値 `0/1` のまま固定されていた
- 対応:
  - shard index / total を `run_pipeline()` 実行時に読むよう修正
  - runtime shard で fetch 件数が変わる回帰テストを追加
- 影響:
  - これまでの `mercari` shard run は真の shard 実行ではなかったため、測定結果は破棄して再実行が必要

### KAGOYA 側 DNS resolver 障害で dashboard-web が落ちて見えた件

- 事象:
  - `marketpilot-dashboard-web.service` 自体は `active (running)` なのに、画面が壊れて見えた
  - `supplier-dashboard-api.service` の `/api/mcp/summary` や `/api/overview` が `500` を返していた
  - KAGOYA 上で `dig kmwyjsvjwtxqqvgrccxh.supabase.co` が `SERVFAIL`、`curl https://kmwyjsvjwtxqqvgrccxh.supabase.co` が `Could not resolve host` になった
- 原因:
  - `apps/dashboard_api/main.py` が Supabase REST を直接読む構成で、KAGOYA VM 側の `systemd-resolved` / DNS が壊れると API 全体が 500 化する
  - 実際の resolver log では KAGOYA 既定 DNS (`210.134.55.219`, `210.134.48.31`) だけでなく public DNS (`1.1.1.1`, `8.8.8.8`) に切り替えても `UDP <-> TCP` degrade を繰り返しており、resolver 自体の不安定化が見えた
  - その結果、web 側は生きていても backend API failure に巻き込まれて「frontend が落ちた」ように見えた
- 確認:
  - `curl -I http://127.0.0.1:3000/` は `200 OK`
  - `systemctl status marketpilot-dashboard-web.service` は `active`
  - 一方で `curl -sS http://127.0.0.1:8080/api/overview | head` は Supabase name resolution failure を返していた
  - VM reboot 後は `dig +short kmwyjsvjwtxqqvgrccxh.supabase.co` が IP を返し、`supplier-dashboard-api.service` / `marketpilot-dashboard-web.service` とも正常化した
- 対応:
  - KAGOYA VM を再起動して resolver/network state をリセット
  - 再起動後に
    - `supplier-dashboard-api.service`
    - `marketpilot-dashboard-web.service`
    - `http://127.0.0.1:8080/api/overview`
    - `http://127.0.0.1:3000/`
    の復旧を確認
- 残課題:
  - dashboard API で Supabase DNS failure 時に `500` を返さず fallback JSON を返す
  - dashboard-web 側も upstream API failure で画面全体が壊れて見えないよう guard を強める
  - KAGOYA 側 DNS 障害時の runbook を docs に固定する
