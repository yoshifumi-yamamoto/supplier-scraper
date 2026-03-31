#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 \"commit message\" <path> [<path> ...]" >&2
  exit 2
fi

commit_message="$1"
shift
paths=("$@")

if [[ -e .git/index.lock ]]; then
  echo "[safe-commit-push] error: .git/index.lock exists" >&2
  exit 1
fi

echo "[safe-commit-push] staging paths"
for path in "${paths[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "[safe-commit-push] error: path not found: $path" >&2
    exit 1
  fi
done

git add -- "${paths[@]}"

echo "[safe-commit-push] staged diff"
git diff --cached -- "${paths[@]}"

echo "[safe-commit-push] committing"
git commit -m "$commit_message"

local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main)"
echo "[safe-commit-push] before push: HEAD=$local_head origin/main=$remote_head"

echo "[safe-commit-push] pushing"
git push origin main

remote_after="$(git rev-parse origin/main)"
echo "[safe-commit-push] after push: HEAD=$local_head origin/main=$remote_after"

if [[ "$local_head" != "$remote_after" ]]; then
  echo "[safe-commit-push] error: push verification failed" >&2
  exit 1
fi

echo "[safe-commit-push] completed"
