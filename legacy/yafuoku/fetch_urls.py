import csv
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "items"

PAGE_SIZE = int(os.getenv("SUPABASE_PAGE_SIZE", 200))
FETCH_MAX_RETRIES = int(os.getenv("FETCH_MAX_RETRIES", 5))
FETCH_BACKOFF_BASE = float(os.getenv("FETCH_BACKOFF_BASE", 2.0))
MAX_PAGES = int(os.getenv("MAX_PAGES", 0))


def fetch_data_from_supabase():
    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    all_data = []
    page = 0
    last_item_id = None

    while True:
        if MAX_PAGES > 0 and page >= MAX_PAGES:
            print(f"[INFO] MAX_PAGES={MAX_PAGES} に到達したため取得を打ち切ります")
            break

        params = {
            "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status",
            "listing_status": "eq.Active",
            "stocking_url": "ilike.*auctions.yahoo.co.jp*",
            "order": "ebay_item_id.asc",
            "limit": str(PAGE_SIZE),
        }
        if last_item_id:
            params["ebay_item_id"] = f"gt.{last_item_id}"

        data = None
        for attempt in range(FETCH_MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=45)
                if response.status_code >= 500:
                    body_preview = response.text[:300].replace("\n", " ")
                    raise requests.HTTPError(
                        f"Supabase {response.status_code} on page {page + 1}: {body_preview}",
                        response=response,
                    )
                response.raise_for_status()
                data = response.json()
                break
            except Exception as e:  # noqa: BLE001
                if attempt == FETCH_MAX_RETRIES - 1:
                    raise
                sleep_sec = FETCH_BACKOFF_BASE * (2 ** attempt)
                print(
                    f"[WARN] fetch retry {attempt + 1}/{FETCH_MAX_RETRIES} failed "
                    f"(page={page + 1}): {e} / sleep={sleep_sec:.1f}s"
                )
                time.sleep(sleep_sec)

        if not data:
            break

        all_data.extend(data)
        last_item_id = data[-1]["ebay_item_id"]
        print(f"[DEBUG] page={page + 1} 取得={len(data)}件（累計: {len(all_data)}件）")

        if len(data) < PAGE_SIZE:
            break

        page += 1

    return all_data


def save_filtered_csv(data):
    filtered = [row for row in data if "auctions.yahoo.co.jp" in row["stocking_url"]]

    os.makedirs("input", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = f"input/yafuoku_urls_{timestamp}.csv"

    with open(file_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ebay_item_id",
                "ebay_user_id",
                "stocking_url",
                "listing_status",
                "stock_status_checked",
                "scraped_stock_status",
            ],
        )
        writer.writeheader()
        for row in filtered:
            row["stock_status_checked"] = ""
            writer.writerow(row)

    print(f"{len(filtered)} 件のURLを {file_path} に保存しました。")


if __name__ == "__main__":
    try:
        data = fetch_data_from_supabase()

        print(f"[DEBUG] Supabase から取得したデータ件数: {len(data)}")
        if data:
            print(f"[DEBUG] 先頭データの中身: {data[0]}")
        else:
            print("[DEBUG] データは0件でした")

        save_filtered_csv(data)
    except Exception as e:  # noqa: BLE001
        print(f"エラーが発生しました: {e}")
        sys.exit(1)
