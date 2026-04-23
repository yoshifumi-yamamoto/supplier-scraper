# API 在庫監視設計

更新日: 2026-04-03

## 1. 目的
- `楽天市場`
- `Yahoo!ショッピング`
- `Amazon`

の3サイトについて、Selenium ではなく API 優先で在庫監視を行う。

背景:
- 現行のブラウザ監視は `mercari` を中心に CPU コストが高い
- 今後サイト数が増える前提では、増分サイトは API ベースで設計した方が `1日2回` 要件を満たしやすい
- API 監視は速度、安定性、並列性、障害切り分けの面で有利

## 2. 基本方針
- 既存 Selenium サイトとは別レーンで実装する
- site ごとの HTML 判定ロジックは持たず、`site API client -> normalizer -> run_store` の流れに揃える
- `scrape_runs` / `scrape_run_steps` は既存の監視基盤をそのまま使う
- ダッシュボードでは `source=api` を明示できる形にする
- API 未取得時の fallback に Selenium を安易に入れない

## 3. 対象と優先順
1. `rakuten`
2. `yahoo_shopping`
3. `amazon`

理由:
- `rakuten` と `Yahoo!ショッピング` は API ベース移行の現実性が高い
- `Amazon` は認証と利用条件が最も重いため最後に扱う

## 4. 監視要件

### 4.1 必須
- 在庫有無
- 価格
- 最終取得時刻
- item ごとの取得成功/失敗
- API 失敗時の error type 分類

### 4.2 できれば欲しい
- バリエーション在庫
- 販売状態
- ポイント/送料の補助情報
- レート制限残量

### 4.3 今回は不要
- 商品説明全文
- 画像同期
- レビュー
- 検索連動のランキング情報

## 5. サイト別設計

### 5.1 楽天市場
- 方針:
  - 公式 API ベースで在庫監視
  - 既存 `baysync-rakuten-stock-scraper` は段階的に廃止
- 前提:
  - Rakuten Web Service の `楽天市場API` を利用する
  - URL 監視より `itemCode` 監視を優先する
  - `item.rakuten.co.jp/<shop>/<item>/` または `www.rakuten.co.jp/<shop>/<item>/` から `shop:item` を解決する
- 実装メモ:
  - `scrapers/sites/rakuten/client.py`
  - `scrapers/sites/rakuten/normalizer.py`
  - `scrapers/sites/rakuten/adapter.py`
- 懸念:
  - 商品 URL しか持っていない item をどう `item code` に解決するか
  - バリエーション在庫の扱い

### 5.2 Yahoo!ショッピング
- 方針:
  - 公式 API ベースで在庫監視
  - `yahoofleama` とは別 site として扱う
- 前提:
  - `seller item code` か `item id` を保持する
  - URL 依存ではなく API key/secret で取れる識別子へ寄せる
- 実装メモ:
  - `scrapers/sites/yahoo_shopping/client.py`
  - `scrapers/sites/yahoo_shopping/normalizer.py`
  - `scrapers/sites/yahoo_shopping/adapter.py`
- 懸念:
  - 複数 seller / variation item の扱い
  - 価格・在庫が seller 単位なのか item 単位なのかの統一

### 5.3 Amazon
- 方針:
  - `SP-API` か `Product Advertising API` のどちらを使うかを最初に固定する
  - 実装順は最後
- 前提:
  - 認証、権限、利用条件が他2サイトより重い
  - `ASIN` を主キーとして扱う
- 実装メモ:
  - `scrapers/sites/amazon/client.py`
  - `scrapers/sites/amazon/normalizer.py`
  - `scrapers/sites/amazon/adapter.py`
- 懸念:
  - 在庫可否が欲しい粒度で本当に取得できるか
  - API 利用条件が運用負荷になる可能性

## 6. 共通アーキテクチャ

### 6.1 構成
- `client.py`
  - 認証
  - API 呼び出し
  - レート制限 / retry
- `normalizer.py`
  - site 固有レスポンスから共通 stock payload へ変換
- `adapter.py`
  - `fetch_active_items_by_domain()` 相当の取得
  - item ごとの API 実行
  - `run_store` 記録
  - `update_item_stock_bulk()` への flush

### 6.2 共通 payload
```python
{
    "item_id": "...",
    "site": "rakuten",
    "source": "api",
    "in_stock": True,
    "price": 12800,
    "currency": "JPY",
    "availability_text": "在庫あり",
    "raw_status": "...",
    "fetched_at": "2026-04-03T12:00:00+09:00",
}
```

### 6.3 step 記録
- `fetch_items`
- `fetch_items` message: `fetched {N} items`
- `check:<item_id>`
- `finish_run(success|failed)`

Selenium サイトと同じ progress 計算に乗せる。

## 7. 認証と設定

### 7.1 環境変数
- `RAKUTEN_APPLICATION_ID`
- `RAKUTEN_ACCESS_KEY`
- `RAKUTEN_AFFILIATE_ID`
- `RAKUTEN_BASE_URL`
- `RAKUTEN_SITE_KEY`
- `YAHOO_SHOPPING_CLIENT_ID`
- `YAHOO_SHOPPING_CLIENT_SECRET`
- `AMAZON_SP_API_*` または `AMAZON_PA_API_*`

### 7.2 ルール
- key/secret は repo に置かない
- KAGOYA の `.env` と GitHub Secrets から供給する
- dashboard では secret の有無そのものを出さず、`auth_ready=true/false` だけ返す

## 8. エラー分類
- `api_auth`
- `api_rate_limit`
- `api_not_found`
- `api_server_error`
- `network`
- `unknown`

`validator` と dashboard で、Selenium サイトの `db_timeout` などと並べて見えるようにする。

## 9. ダッシュボード要件
- `source=api` の表示
- API site も `processed / total / remaining / eta` を表示
- `rate_limit` と `auth_ready` を将来的に Capacity/運用欄へ出せる形にする

## 10. 実装順

### Phase A
- `rakuten` の API client/adapter 雛形
- `apps/runner` に `--site rakuten`
- `registry.py` と dashboard 表示追加

### Phase B
- `Yahoo!ショッピング` を同じ構成で追加
- 共通 API stock normalizer を切り出す

### Phase C
- `Amazon` の API 方針を固定
- 認証前提を満たせるか確認後に実装

## 11. 完了条件
- `rakuten` / `Yahoo!ショッピング` / `Amazon` が Selenium なしで在庫監視できる
- `scrape_runs` / `scrape_run_steps` へ既存 site と同じ形式で記録される
- dashboard で `source=api` と進捗が見える
- `1日2回` 要件の capacity 計算にこの3サイトを含められる

## 12. 直近アクション
1. `rakuten` の認証方式と item 主キーを確定
2. `Yahoo!ショッピング` の item 識別子を URL から解決できるか確認
3. `Amazon` は利用可能 API と認証保有状況を確認してから着手
