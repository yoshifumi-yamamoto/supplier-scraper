#!/bin/bash

LOG_DIR="/root/scrape_logs"
mkdir -p "$LOG_DIR"
NOW=$(date "+%Y%m%d_%H%M%S")

echo "=== スクレイピング一括処理開始 ==="

# 共通処理: tmp_chrome 削除関数
cleanup_tmp_chrome() {
  TARGET_DIR="$1"
  TMP_DIR="$TARGET_DIR/tmp_chrome"
  if [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
    echo "🧹 tmp_chrome 削除: $TMP_DIR"
  fi
}

# ✅ Mercari
echo "▶️ Mercari 開始"
rm -f /tmp/mercari_done.flag
cleanup_tmp_chrome "/root/baysync-mercari-stock-scraper"
screen -dmS scrape_mercari_$NOW bash -c "/bin/bash /root/baysync-mercari-stock-scraper/run_scrape.sh"

echo "⏳ Mercari 終了待ち中..."
while [ ! -f /tmp/mercari_done.flag ]; do
  sleep 30
done
echo "✅ Mercari 終了検知"

# ✅ Yafuoku
echo "▶️ Yafuoku 開始"
cleanup_tmp_chrome "/root/baysync-yafuoku-stock-scraper"
screen -dmS scrape_yafuoku_$NOW bash -c "/bin/bash /root/baysync-yafuoku-stock-scraper/run_scrape.sh"

# ✅ Yahoofleama
echo "▶️ Yahoofleama 開始"
cleanup_tmp_chrome "/root/baysync-yahoofleama-stock-scraper"
screen -dmS scrape_yahoofleama_$NOW bash -c "/bin/bash /root/baysync-yahoofleama-stock-scraper/run_scrape.sh"

# ✅ Hardoff
echo "▶️ Hardoff 開始"
cleanup_tmp_chrome "/root/baysync-hardoff-stock-scraper"
screen -dmS scrape_hardoff_$NOW bash -c "/bin/bash /root/baysync-hardoff-stock-scraper/run_scrape.sh"

# ✅ 2ndStreet
echo "▶️ 2ndStreet 開始"
cleanup_tmp_chrome "/root/baysync-2ndstreet-stock-scraper"
screen -dmS scrape_2ndstreet_$NOW bash -c "/bin/bash /root/baysync-2ndstreet-stock-scraper/run_scrape.sh"

# ✅ Yodobashi
echo "▶️ Yodobashi 開始"
cleanup_tmp_chrome "/root/baysync-yodobashi-stock-scraper"
screen -dmS scrape_yodobashi_$NOW bash -c "/bin/bash /root/baysync-yodobashi-stock-scraper/run_scrape.sh"

# ✅ Rakuma
echo "▶️ Rakuma 開始"
cleanup_tmp_chrome "/root/baysync-rakuma-stock-scraper"
screen -dmS scrape_rakuma_$NOW bash -c "/bin/bash /root/baysync-rakuma-stock-scraper/run_scrape.sh"

# --- グローバル Chrome クリーンアップ ---
echo "🧹 グローバル Chrome/Chromedriver プロセス掃除"

USER_DATA_DIR_BASE="/tmp/selenium-profile"
if [ -d "$USER_DATA_DIR_BASE" ]; then
  rm -rf ${USER_DATA_DIR_BASE:?}/*
  echo "✅ user-data-dir を削除しました ($USER_DATA_DIR_BASE)"
fi

pkill -f chromedriver && echo "✅ chromedriver プロセス終了"
pkill -f -- "chrome" && echo "✅ chrome プロセス終了"

# --- 古いログの削除 ---
LOG_CLEAN_DIR="/root/scrape_logs"
find "$LOG_CLEAN_DIR" -type f -name "*.log" -mtime +7 -delete && echo "✅ 古いログ削除 ($LOG_CLEAN_DIR)"

# --- 再起動（週1回） ---
DOW=$(date +%u)  # 1=月曜日, ..., 7=日曜日
if [ "$DOW" -eq 7 ]; then
  echo "♻️ 毎週再起動タスクを実行します..."
  shutdown -r +1 "再起動をスケジュールしました（1分後）"
else
  echo "✅ 本日は再起動しません ($DOW)"
fi

echo "=== すべてのスクレイピング処理が開始されました ==="
