#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOG_DIR="$SCRIPT_DIR/logs/cron"
mkdir -p "$LOG_DIR"
NOW=$(date "+%Y%m%d_%H%M%S")

cd "$SCRIPT_DIR"
/usr/bin/python3 main.py >> "$LOG_DIR/run_$NOW.log" 2>&1
