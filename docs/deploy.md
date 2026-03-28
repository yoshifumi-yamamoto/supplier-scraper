# Deploy

## 方針
- 手動でサーバーへコピーして反映する運用をやめる
- `main` への push を KAGOYA デプロイのトリガにする
- デプロイ時に最低限の構文確認を入れて、壊れた状態で本番に入れない

## GitHub Actions
- Workflow: `.github/workflows/deploy-kagoya.yml`
- Trigger:
  - `main` への push
  - 手動実行 (`workflow_dispatch`)

## 必要な GitHub Secrets
- `KAGOYA_HOST`
  - 例: `133.18.43.105`
- `KAGOYA_USER`
  - 例: `root`
- `KAGOYA_APP_DIR`
  - 例: `/root/supplier-scraper-main`
- `KAGOYA_SSH_PRIVATE_KEY`
  - KAGOYA に接続できる秘密鍵全文

## サーバー側前提
- KAGOYA 上の `$KAGOYA_APP_DIR` が git clone 済み
- `origin` が push 元 repo を指している
- `.venv` が作成済み
- `supplier-mcp.service` が既存どおり動いている

## デプロイ内容
- `git fetch origin`
- `git checkout <branch>`
- `git pull --ff-only origin <branch>`
- `.venv/bin/python3 -m py_compile` による最低限の検証
- `supplier-mcp.service` の restart

## 注意
- これは `push -> pull/restart` の最小構成
- DB migration は自動適用していない
- migration が必要な変更は、workflow を分けるか手順を明示する

## 今回この形にした理由
- 現在の障害は、修正自体より「修正が KAGOYA に入っていない」ことが原因だった
- まずは未デプロイ事故を構造で潰す方が優先
