import csv
import glob
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()

SCRAPED_FOLDER = "scraped"
SPLIT_FOLDER = "split"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "items"
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def get_latest_split_folder():
    folders = [f for f in glob.glob(os.path.join(SPLIT_FOLDER, "*")) if os.path.isdir(f)]
    if not folders:
        raise FileNotFoundError("split フォルダが空です")
    return max(folders, key=os.path.getmtime)


def get_csv_files(folder):
    return glob.glob(os.path.join(folder, "*.csv"))


def setup_driver():
    options = Options()
    if CHROME_HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1600,2400')
    options.add_argument('user-agent=Mozilla/5.0')
    tmp_user_dir = os.path.join(os.getcwd(), 'tmp_chrome', datetime.now().strftime('%Y%m%d%H%M%S%f'))
    os.makedirs(tmp_user_dir, exist_ok=True)
    options.add_argument(f'--user-data-dir={tmp_user_dir}')
    driver = webdriver.Chrome(service=Service('/usr/local/bin/chromedriver'), options=options)
    driver.set_page_load_timeout(60)
    return driver, tmp_user_dir


def wait_ready(driver):
    WebDriverWait(driver, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)


def is_sold_out_source(source: str) -> bool:
    return ('SoldOut' in source) or ('availability\": \"https://schema.org/SoldOut' in source)


def first_used_detail_url(driver):
    links = []
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        if '/ec/used/' in href and href not in links:
            links.append(href.split('#')[0])
    return links[0] if links else None


def detect_stock_status(driver, url: str) -> str:
    driver.get(url)
    wait_ready(driver)
    source = driver.page_source.replace('\/', '/')
    if '/ec/list?' in url and 'type=u' in url:
        used_url = first_used_detail_url(driver)
        return '在庫あり' if used_url else '在庫なし'
    if '/ec/used/' in url:
        return '在庫あり'
    if '/ec/pd/' in url:
        return '在庫なし' if is_sold_out_source(source) else '在庫あり'
    return '不明'


def bulk_update_supabase(rows):
    now_jst = datetime.now(timezone(timedelta(hours=9))).isoformat()
    for row in rows:
        ebay_item_id = row.get('ebay_item_id')
        if not ebay_item_id:
            continue
        url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?ebay_item_id=eq.{ebay_item_id}"
        payload = {
            'scraped_stock_status': row['scraped_stock_status'],
            'scraped_updated_at': now_jst,
            'is_scraped': True,
        }
        requests.patch(url, headers=SUPABASE_HEADERS, json=payload, timeout=30)


def scrape_file(csv_file):
    driver, tmp_user_dir = setup_driver()
    output_dir = os.path.join(SCRAPED_FOLDER, datetime.now().strftime('%Y%m%d%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, os.path.basename(csv_file))
    buffer = []
    try:
        with open(csv_file, mode='r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        with open(output_file, mode='w', encoding='utf-8', newline='') as wf:
            fieldnames = ["ebay_item_id", "ebay_user_id", "stocking_url", "listing_status", "stock_status_checked", "stock_status", "scraped_stock_status"]
            writer = csv.DictWriter(wf, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                status = '不明'
                try:
                    status = detect_stock_status(driver, row['stocking_url'])
                except Exception as exc:  # noqa: BLE001
                    print(f"[WARN] {row['stocking_url']} {exc}")
                row['stock_status_checked'] = 'done'
                row['stock_status'] = status
                row['scraped_stock_status'] = status
                writer.writerow(row)
                buffer.append({
                    'ebay_item_id': row['ebay_item_id'],
                    'scraped_stock_status': status,
                })
        bulk_update_supabase(buffer)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if os.path.isdir(tmp_user_dir):
            shutil.rmtree(tmp_user_dir, ignore_errors=True)


if __name__ == '__main__':
    split_folder = get_latest_split_folder()
    files = get_csv_files(split_folder)
    for csv_file in files:
        scrape_file(csv_file)
    print('kitamura scrape complete')
