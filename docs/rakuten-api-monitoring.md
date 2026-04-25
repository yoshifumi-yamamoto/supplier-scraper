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
2. 初回 discovery は `shopCode + keyword` 検索で候補を出し、型番一致を最優先に価格差・タイトル類似度・画像一致で confidence 判定する
3. high confidence のみ API 返却 `itemCode` を正式IDとして保存する
4. low confidence 候補は `pending` として保存し、在庫監視対象に入れない
5. `scrape_runs / scrape_run_steps` の本番 run を確認する
6. ダッシュボードで `source=api` の表示を確認する

## 2026-04-24 時点の追加方針
- 認証と許可 IP の疎通は確認済み
- `rakuten` run 自体も success している
- 現在の主要ボトルネックは
  - `429 Rate limit is exceeded`
  - `keyword is not valid`
- さらに、eBay タイトルを discovery 入力に使う方針は不適切と判断した
- 初回 discovery は Rakuten 商品ページ HTML から
  - 日本語タイトル
  - 型番候補
  - SKU / 商品コード / JAN 候補
  を抽出して API 検索へ渡す
- そのため、初回 discovery は通常監視と分けて扱う
  - 保存済み `itemCode` の再照会を優先する
  - 初回 discovery は 1 run ごとに上限件数を設ける
  - `RAKUTEN_DISCOVERY_LIMIT` の既定は `30`
  - discovery を超えた item は次回 run へ defer する
- 商品ページ HTML が `404` の場合は、楽天上で商品ページ自体が消えているとみなし `在庫なし` に倒す
- 価格差は eBay 側ドル価格と楽天側円価格で直接比較できないため、discovery の主要スコアから外す

## 現在の env 契約
- `RAKUTEN_APPLICATION_ID`
- `RAKUTEN_ACCESS_KEY`
- `RAKUTEN_AFFILIATE_ID`
- `RAKUTEN_BASE_URL`
- `RAKUTEN_SITE_KEY`

## API endpoint
- 既定 endpoint は `https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401`
- 初回疎通は `keyword` で確認し、正式 `itemCode` は API レスポンスから保存する
- URL / HTML の `sku` は正式 `itemCode` とみなさない

## 2026-04-25 検証結果
- `全部 不明` の状態からは脱出した
- 最新の Rakuten active items 集計:
  - 総件数: `288`
  - `在庫あり`: `2`
  - `在庫なし`: `14`
  - `不明`: `216`
  - `NULL`: `56`
- SKU 集計:
  - confirmed `rakuten:<itemCode>`: `2`
  - pending `rakuten-pending:<itemCode>`: `6`
  - empty: `279`
- 少なくとも次の shop で `itemCode` 確定が始まっている:
  - `sazac-store`
  - `golfpartner`
- 現時点の主ボトルネック:
  - `rakuten itemCode discovery unresolved`
  - `keyword is not valid`
  - upstream item row が incomplete なため `scraped_stock_status` が `NULL` のまま残るケース
