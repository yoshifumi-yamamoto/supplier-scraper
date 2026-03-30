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
- KAGOYA 上の `$KAGOYA_APP_DIR` が存在している
- `.venv` が作成済み
- `supplier-mcp.service` が既存どおり動いている

## デプロイ内容
- GitHub Actions 上で preflight を実行
  - `py_compile`
  - 重要 import smoke
  - 対象テスト
  - 重要ファイルが git 管理下にあることの確認
- GitHub Actions runner から KAGOYA へ `rsync`
- KAGOYA 上で post-deploy smoke を実行
  - `py_compile`
  - 重要 import smoke
- `supplier-mcp.service` の restart

## 注意
- これは `push -> rsync/restart` の最小構成
- DB migration は自動適用していない
- migration が必要な変更は、workflow を分けるか手順を明示する
- server に直接コピーした緊急修正がある場合は、必ず同内容を repo に戻してから次回 deploy する

## 今回この形にした理由
- 現在の障害は、修正自体より「修正が KAGOYA に入っていない」ことが原因だった
- まずは未デプロイ事故を構造で潰す方が優先
- KAGOYA 上の `/root/supplier-scraper-main` は `git clone` ではなく作業ディレクトリだったため、`git pull` 前提では動かなかった
