import tempfile
import os
import csv
import glob
import time
import logging
import requests
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool, Manager
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import random
import shutil

load_dotenv()

SCRAPED_FOLDER = "scraped"
SPLIT_FOLDER = "split"
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", 80.0))
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "false").lower() == "true"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "items"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

log_date = datetime.now().strftime("%Y%m%d")
log_dir = f"logs/{log_date}"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "summary.log")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a",
    encoding="utf-8"
)

def get_latest_split_folder():
    folders = [f for f in glob.glob(os.path.join(SPLIT_FOLDER, "*")) if os.path.isdir(f)]
    if not folders:
        raise FileNotFoundError("split フォルダが空です")
    return max(folders, key=os.path.getmtime)

def get_csv_files(folder):
    return glob.glob(os.path.join(folder, "*.csv"))

def setup_driver(proxy=None):
    # tmp_user_dir = tempfile.mkdtemp(prefix="chrome_profile_")
    tmp_user_dir = os.path.join(os.getcwd(), "tmp_chrome", f"profile_{random.randint(0,99999)}")
    os.makedirs(tmp_user_dir, exist_ok=True)
    logging.info(f"[Chrome起動] user-data-dir: {tmp_user_dir}")

    options = Options()
    options.add_argument(f"--user-data-dir={tmp_user_dir}")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--start-maximized')
    # options.add_argument('--headless=new')
    options.add_argument('--headless')
    options.add_argument("user-agent=Mozilla/5.0")
    options.add_argument("accept-language=ja,en-US;q=0.9,en;q=0.8")

    if proxy:
        logging.info(f"[DEBUG] proxy使用中: {proxy}")
        options.add_argument(f'--proxy-server={proxy}')

    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver, tmp_user_dir

def bulk_update_supabase(buffer):
    for row in buffer:
        ebay_item_id = row.get("ebay_item_id")
        if not ebay_item_id:
            logging.error(f"[SKIP] ebay_item_idが空のためスキップ: {row}")
            continue

        url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?ebay_item_id=eq.{ebay_item_id}"
        payload = {
            "scraped_stock_status": row["scraped_stock_status"],
            "scraped_updated_at": row["scraped_updated_at"],
            "is_scraped": row["scraped_stock_status"] != "不明"
        }

        try:
            res = requests.patch(url, headers=SUPABASE_HEADERS, json=payload)
            if res.status_code not in (200, 204):
                logging.error(f"[FAIL] Supabase更新失敗: {ebay_item_id} → {res.status_code} - {res.text}")
            else:
                logging.info(f"[OK] Supabase更新: {ebay_item_id} → {row['scraped_stock_status']}")
        except Exception as e:
            logging.error(f"[ERROR] Supabase更新エラー: {ebay_item_id} → {e}")



def scrape_file(args):
    csv_file, limit, progress_dict, total, proxy, lock = args
    success_count = 0
    fail_count = 0

    try:
        driver, tmp_user_dir = setup_driver(proxy)

        output_dir = os.path.join(SCRAPED_FOLDER, datetime.now().strftime("%Y%m%d%H%M%S"))
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, os.path.basename(csv_file))

        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader) if limit is None else list(reader)[:limit]

        with open(output_file, mode="w", encoding="utf-8", newline="") as f:
            fieldnames = ["ebay_item_id", "ebay_user_id", "stocking_url", "listing_status", "stock_status_checked", "stock_status", "scraped_stock_status"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            supabase_buffer = []

            for row in rows:
                url = row["stocking_url"]
                status = "不明"
                retries = 2
                for attempt in range(retries):
                    try:
                        driver.get(url)
                        WebDriverWait(driver, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')

                    except Exception as e:
                        if attempt < retries - 1:
                            logging.warning(f"[RETRY] driver.get()失敗（{attempt+1}回目）: {e} [URL: {url}]")
                            time.sleep(1)
                            continue
                        else:
                            logging.error(f"[FATAL] driver.get()失敗（最終）: {e} [URL: {url}] [PROXY: {proxy}]")
                            fail_count += 1
                            break

                    time.sleep(random.uniform(1.0, 3.0))

                    # 🛠️ 改訂版：まずボタンを最大3秒だけ待つ
                    # 🛠️ ハードオフ用：ボタンの有無で在庫判定
                    try:
                        # ボタンのテキストが「カートに入れる」のときのみ在庫あり
                        button = driver.find_element(By.XPATH, '//button[@class="cart-add-button "]/span[1]')
                        if "カートに入れる" in button.text:
                            status = "在庫あり"
                            pattern = "hardoff_available"
                        else:
                            status = "在庫なし"
                            pattern = "hardoff_disabled"
                    except:
                        status = "在庫なし"
                        pattern = "hardoff_not_found"

                    logging.info(f"[判定結果] {url} → {status} → {pattern}")

                    success_count += 1
                    break

                # ★ 行ごとのSupabase更新準備
                row["stock_status_checked"] = "done"
                row["stock_status"] = status
                row["scraped_stock_status"] = status

                writer.writerow(row)

                supabase_buffer.append({
                    "ebay_item_id": row["ebay_item_id"],
                    "ebay_user_id": row["ebay_user_id"],
                    "scraped_stock_status": status,
                    "scraped_updated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
                    "is_scraped": status != "不明"
                })

                if len(supabase_buffer) >= 100:
                    bulk_update_supabase(supabase_buffer)
                    supabase_buffer.clear()

            if supabase_buffer:
                bulk_update_supabase(supabase_buffer)

    finally:
        try:
            driver.quit()
        except Exception as e:
            logging.warning(f"[WARNING] driver.quit()失敗: {e}")

        try:
            shutil.rmtree(tmp_user_dir, ignore_errors=True)
            logging.info(f"[CLEANUP] 一時プロファイル削除: {tmp_user_dir}")
        except Exception as e:
            logging.warning(f"[WARNING] 一時ディレクトリ削除失敗: {e}")

    with lock:
        progress_dict["count"] += len(rows)
        current = progress_dict["count"]

    progress = (current / total) * 100
    logging.info(f"[進捗] {current} / {total} 件 処理完了（{progress:.2f}%）")
    logging.info(f"[ファイル完了] {csv_file} - 成功: {success_count} / 失敗: {fail_count} [PROXY: {proxy}]")


def read_total_count(folder):
    try:
        with open("input/fetch_summary.txt", "r") as f:
            return int(f.read().strip())
    except:
        total = 0
        for file in get_csv_files(folder):
            with open(file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                total += sum(1 for _ in reader)
        return total

if __name__ == "__main__":
    try:
        start_time = datetime.now()
        logging.info(f"=== スクレイピング開始: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")

        folder = get_latest_split_folder()
        files = get_csv_files(folder)
        raw_proxies = os.getenv("PROXIES", "")
        proxies = [p.strip() for p in raw_proxies.split(",") if p.strip()]

        limit_per_file = None
        max_processes = 12
        total_count = read_total_count(folder)

        with Manager() as manager:
            counter = manager.dict()
            counter["count"] = 0
            lock = manager.Lock()

            args = []
            for i, file in enumerate(files):
                proxy = proxies[i % len(proxies)] if proxies else None
                args.append((file, limit_per_file, counter, total_count, proxy, lock))

            with Pool(processes=max_processes) as pool:
                pool.map(scrape_file, args)

        end_time = datetime.now()
        elapsed = end_time - start_time
        logging.info(f"=== スクレイピング終了: {end_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
        logging.info(f"=== 所要時間: {elapsed} ===")

        print("すべてのスクレイピングが完了しました。")

    except Exception as e:
        print(f"エラー: {e}")
        logging.error(f"スクレイピング全体エラー: {e}")
