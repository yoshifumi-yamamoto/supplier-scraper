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
