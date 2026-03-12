#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE=${MCP_ORCHESTRATOR_LOCK_FILE:-/tmp/supplier-mcp-orchestrator.lock}
LOG_PREFIX=${MCP_ORCHESTRATOR_LOG_PREFIX:-[mcp-orchestrator]}
API_BASE=${MCP_API_BASE:-http://127.0.0.1:8080}
RUN_SCRIPT=${MCP_RUN_SCRIPT:-/root/supplier-scraper-main/scripts/mcp_run_site.sh}
SITE_TIMEOUT_SEC=${MCP_SITE_TIMEOUT_SEC:-5400}
# Default order follows current operational priority.
SITES_CSV=${MCP_SITES_CSV:-mercari,yafuoku,hardoff,yodobashi,rakuma,yahoofleama,secondstreet,kitamura}
DEFAULT_INTERVAL_MIN=${MCP_DEFAULT_INTERVAL_MIN:-720}

# Per-site minimum interval (minutes)
declare -A INTERVAL_MIN=(
  [mercari]="${MCP_INTERVAL_MERCARI_MIN:-720}"
  [yafuoku]="${MCP_INTERVAL_YAFUOKU_MIN:-720}"
  [hardoff]="${MCP_INTERVAL_HARDOFF_MIN:-720}"
  [yodobashi]="${MCP_INTERVAL_YODOBASHI_MIN:-720}"
  [rakuma]="${MCP_INTERVAL_RAKUMA_MIN:-720}"
  [kitamura]="${MCP_INTERVAL_KITAMURA_MIN:-720}"
  [yahoofleama]="${MCP_INTERVAL_YAHOOFLEAMA_MIN:-720}"
  [secondstreet]="${MCP_INTERVAL_SECONDSTREET_MIN:-720}"
)

log() {
  printf '%s %s %s\n' "$(date '+%F %T')" "$LOG_PREFIX" "$*"
}

fetch_last_started_at() {
  local site="$1"
  local payload
  payload="$(curl -fsS "$API_BASE/api/mcp/summary" 2>/dev/null || echo '{}')"
  python3 - "$site" "$payload" <<'PY'
import json, sys
site = sys.argv[1]
payload = sys.argv[2]
found = ""
try:
    data = json.loads(payload)
    for row in data.get("latest_by_site", []):
        if (row.get("site") or "") == site:
            found = (row.get("started_at") or "").strip()
            break
except Exception:
    pass
print(found)
PY
}

is_site_running() {
  local site="$1"
  local payload
  payload="$(curl -fsS "$API_BASE/api/mcp/summary" 2>/dev/null || echo '{}')"
  python3 - "$site" "$payload" <<'PY'
import json, sys
site = sys.argv[1]
payload = sys.argv[2]
running = "false"
try:
    data = json.loads(payload)
    for row in data.get("latest_by_site", []):
        if (row.get("site") or "") == site and (row.get("status") or "") == "running":
            running = "true"
            break
except Exception:
    pass
print(running)
PY
}

should_run_site() {
  local site="$1"
  local interval="${INTERVAL_MIN[$site]:-$DEFAULT_INTERVAL_MIN}"
  local last_started
  last_started="$(fetch_last_started_at "$site" || true)"

  if [ -z "$last_started" ]; then
    return 0
  fi

  python3 - "$last_started" "$interval" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
raw = sys.argv[1].strip()
interval_min = int(sys.argv[2])
if not raw:
    print("run")
    raise SystemExit(0)
raw = raw.replace("Z", "+00:00")
try:
    dt = datetime.fromisoformat(raw)
except ValueError:
    print("run")
    raise SystemExit(0)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
print("run" if now - dt >= timedelta(minutes=interval_min) else "skip")
PY
}

main() {
  mkdir -p "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "lock busy: $LOCK_FILE"
    exit 0
  fi

  if [ ! -x "$RUN_SCRIPT" ]; then
    log "run script not executable: $RUN_SCRIPT"
    exit 1
  fi

  IFS=',' read -r -a sites <<< "$SITES_CSV"
  local rc=0

  for site in "${sites[@]}"; do
    site="${site// /}"
    [ -z "$site" ] && continue

    if [ "$(is_site_running "$site" || echo false)" = "true" ]; then
      log "skip site=$site reason=already_running"
      continue
    fi

    decision="$(should_run_site "$site" || echo run)"
    if [ "$decision" != "run" ]; then
      log "skip site=$site reason=cooldown"
      continue
    fi

    log "start site=$site timeout_sec=$SITE_TIMEOUT_SEC"
    if timeout "$SITE_TIMEOUT_SEC" "$RUN_SCRIPT" "$site"; then
      log "finish site=$site status=ok"
    else
      site_rc=$?
      rc=1
      if [ "$site_rc" -eq 124 ]; then
        log "finish site=$site status=timeout"
      else
        log "finish site=$site status=failed code=$site_rc"
      fi
      # Continue processing next sites even on failure.
    fi
  done

  exit "$rc"
}

main "$@"
