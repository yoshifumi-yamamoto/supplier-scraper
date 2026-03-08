#!/bin/bash

LOG_DIR="/root/baysync-yafuoku-stock-scraper/logs/cron"
mkdir -p "$LOG_DIR"
NOW=$(date "+%Y%m%d_%H%M%S")

cd /root/baysync-yafuoku-stock-scraper
/usr/bin/python3 main.py >> "$LOG_DIR/run_$NOW.log" 2>&1
