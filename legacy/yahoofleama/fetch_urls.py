import requests
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "items"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

def fetch_data_from_supabase():
    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Range-Unit": "items",
    }

    all_data = []
    page_size = 1000
    page = 0

    while True:
        from_idx = page * page_size
        to_idx = from_idx + page_size - 1
        range_header = f"{from_idx}-{to_idx}"
        headers["Range"] = range_header

        params = {
            "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status",
            "listing_status": "eq.Active",
            "stocking_url": "not.is.null",
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            break

        all_data.extend(data)
        print(f"[DEBUG] {from_idx}〜{to_idx}件を取得（累計: {len(all_data)}件）")

        if len(data) < page_size:
            break

        page += 1

    return all_data

# ヤフーフリマ URLだけ抽出してCSV保存
def save_filtered_csv(data):
    # 🔽 テスト用に ebay_user_id=japangolfhub のみ対象（後で消してOK！）
    # data = [row for row in data if row["ebay_user_id"] == "japangolfhub"]

    filtered = [row for row in data if "paypayfleamarket.yahoo.co.jp" in row["stocking_url"]]

    os.makedirs("input", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = f"input/yahoofleama_urls_{timestamp}.csv"

    with open(file_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ebay_item_id", "ebay_user_id", "stocking_url", "listing_status", "stock_status_checked", "scraped_stock_status"
        ])
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
            print(f"[DEBUG] データは0件でした")

        save_filtered_csv(data)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
