#!/bin/bash

# ログ出力先
LOG_DIR="/root/baysync-rakuma-stock-scraper/logs/cron"
mkdir -p "$LOG_DIR"

# タイムスタンプ
NOW=$(date "+%Y%m%d_%H%M%S")

cd /root/baysync-rakuma-stock-scraper
/usr/bin/python3 main.py >> "$LOG_DIR/run_$NOW.log" 2>&1

# 完了フラグ
echo "done" > /tmp/rakuma_done.flag
