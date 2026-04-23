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

## Git 運用
- `git commit` と `git push` を並列で流さない
- `.git/index.lock` がある状態で次の git 操作へ進まない
- commit / push は `scripts/safe_commit_push.sh` を使って直列で行う

例:
```bash
./scripts/safe_commit_push.sh \
  "Add dashboard capacity summary" \
  apps/dashboard_api/main.py \
  apps/dashboard-web/lib/api.ts \
  apps/dashboard-web/app/page.tsx \
  docs/change-history.md
```

このスクリプトは次を行う:
- `index.lock` の事前検知
- 対象 path のみ `git add`
- staged diff 表示
- `git commit`
- `HEAD` と `origin/main` の比較
- `git push origin main`
- push 後の `HEAD == origin/main` 検証

## 今回この形にした理由
- 現在の障害は、修正自体より「修正が KAGOYA に入っていない」ことが原因だった
- まずは未デプロイ事故を構造で潰す方が優先
- KAGOYA 上の `/root/supplier-scraper-main` は `git clone` ではなく作業ディレクトリだったため、`git pull` 前提では動かなかった

## DNS 障害時の切り分け
- `marketpilot-dashboard-web.service` が `active` でも、`supplier-dashboard-api.service` が Supabase name resolution failure で 500 を返すと画面は壊れて見える
- まず `frontend` ではなく `KAGOYA -> Supabase` の到達性を確認する

確認コマンド:
```bash
dig +short kmwyjsvjwtxqqvgrccxh.supabase.co
curl -I https://kmwyjsvjwtxqqvgrccxh.supabase.co
systemctl status supplier-dashboard-api.service -l
systemctl status marketpilot-dashboard-web.service -l
curl -sS http://127.0.0.1:8080/api/overview | head
curl -I http://127.0.0.1:3000/
```

見方:
- `127.0.0.1:3000` が `200` で `:8080/api/overview` が 500 の場合
  - web service 自体ではなく dashboard API 側の障害
- `dig` / `curl https://...supabase.co` が失敗する場合
  - Supabase ではなく KAGOYA 側 DNS / network stack を疑う

## DNS resolver が壊れた時の暫定対応
1. resolver 状態確認
```bash
resolvectl status
cat /etc/resolv.conf
cat /etc/systemd/resolved.conf
journalctl -u systemd-resolved -n 100
```

2. `systemd-resolved` 再起動
```bash
systemctl restart systemd-resolved
```

3. public DNS へ切替
```bash
cat >/etc/systemd/resolved.conf <<'EOF'
[Resolve]
DNS=1.1.1.1 8.8.8.8
FallbackDNS=1.0.0.1 8.8.4.4
EOF
systemctl restart systemd-resolved
```

4. それでも `SERVFAIL` / `Could not resolve host` が続く場合
- resolver 自体の不安定化を疑い、VM reboot を優先
- reboot 後に service と localhost endpoint を再確認する

## 恒久対策メモ
- `dashboard_api` は Supabase fetch 失敗時に 500 を返さず、degraded fallback JSON を返す
- `overview` / `capacity` / `mcp_summary` / `validator_summary` は fallback shape を維持するので、frontend は全面崩壊しにくい
- dashboard API は `db_timeout` / `network` / `timeout` を検知した時だけ Chat 通知する
- 通知は `/tmp/dashboard_api_alert_state.json` で cooldown する
- 既定 cooldown は `DASHBOARD_ALERT_COOLDOWN_SECONDS=900`

## 今回の原因メモ
- `systemd-resolved` が KAGOYA 既定 DNS (`210.134.55.219`, `210.134.48.31`) に対して不安定化
- public DNS に変えても `UDP <-> TCP` degrade を繰り返し、resolver が安定しなかった
- 最終的に VM reboot で `dig +short kmwyjsvjwtxqqvgrccxh.supabase.co` と dashboard API / web が復旧
- `/etc/netplan/50-cloud-init.yaml` と `/run/systemd/network/10-netplan-eth0.network` に KAGOYA DNS が固定されており、reboot 後に public DNS 変更は戻る
- つまり `public DNS へ切替 -> reboot で再発防止` にはならず、cloud-init / netplan 側を恒久対応しない限り再発余地がある
