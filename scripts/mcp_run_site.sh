#!/usr/bin/env bash
set -euo pipefail
SITE=${1:-}
MAX_PAGES=${2:-}
if pgrep -f '/root/run_all_scrapes.sh' >/dev/null 2>&1; then
  echo "{\"skipped\":true,\"reason\":\"run_all_scrapes_in_progress\",\"site\":\"$SITE\"}"
  exit 0
fi
if [ -z "$SITE" ]; then
  echo "usage: $0 <site> [max_pages]" >&2
  exit 1
fi
if [ -n "$MAX_PAGES" ]; then
  PAYLOAD="{\"name\":\"run_scrape\",\"arguments\":{\"site\":\"$SITE\",\"max_pages\":$MAX_PAGES}}"
else
  PAYLOAD="{\"name\":\"run_scrape\",\"arguments\":{\"site\":\"$SITE\"}}"
fi
curl -sS -X POST http://127.0.0.1:8090/mcp/call -H 'content-type: application/json' -d "$PAYLOAD"
