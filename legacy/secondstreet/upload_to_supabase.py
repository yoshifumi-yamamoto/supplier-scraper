import os
import glob
import csv
import requests
import logging
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "items"
SUMMARY_FOLDER = "summarized"

# ✅ ログ設定（ファイル名にタイムスタンプ付き）
log_folder = "logs"
os.makedirs(log_folder, exist_ok=True)
jst = timezone(timedelta(hours=9))
now_jst = datetime.now(jst)
timestamp = now_jst.strftime("%Y%m%d_%H%M%S")
log_path = os.path.join(log_folder, f"upload_to_supabase_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()  # 必要なければ消してOK
    ]
)

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def get_latest_summary_folder():
    subfolders = [f for f in glob.glob(os.path.join(SUMMARY_FOLDER, "*")) if os.path.isdir(f)]
    if not subfolders:
        return None
    return max(subfolders, key=os.path.getmtime)

def update_stock_to_supabase(folder_path):
    if not folder_path:
        logging.warning("⚠️ summarized フォルダがないため、今回の更新はスキップします。")
        return

    files = glob.glob(os.path.join(folder_path, "*.csv"))
    if not files:
        logging.warning(f"⚠️ {folder_path} にCSVがないため、今回の更新はスキップします。")
        return

    success_count = 0
    fail_count = 0

    for file in files:
        logging.info(f"▶️ ファイル処理開始: {file}")
        with open(file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ebay_item_id = row["ebay_item_id"]
                stock_status = row["stock_status"]

                url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?ebay_item_id=eq.{ebay_item_id}"
                payload = {
                    "scraped_stock_status": stock_status,
                    "scraped_updated_at": now_jst.isoformat(),
                    "is_scraped": stock_status != "不明",
                }

                response = requests.patch(url, headers=headers, json=payload)

                if response.status_code not in (200, 204):
                    logging.error(f"[❌失敗] {ebay_item_id} - {response.status_code} - {response.text}")
                    fail_count += 1
                else:
                    logging.info(f"[✅成功] {ebay_item_id} を {stock_status} に更新しました")
                    success_count += 1

    logging.info(f"📊 更新完了: 成功 {success_count} 件 / 失敗 {fail_count} 件")
    if fail_count > 0:
        raise RuntimeError(f"Supabase更新失敗: {fail_count}件")

if __name__ == "__main__":
    try:
        logging.info("🔍 summarizedフォルダを探索中...")
        folder = get_latest_summary_folder()
        if folder:
            logging.info(f"📂 最新フォルダ: {folder}")

        update_stock_to_supabase(folder)
        logging.info("🎉 Supabaseへの更新が完了しました。")
    except Exception as e:
        logging.exception(f"🚨 処理中にエラー発生: {e}")
        sys.exit(1)
