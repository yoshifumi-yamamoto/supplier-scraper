import os
import glob
import csv
from datetime import datetime

SCRAPED_FOLDER = "scraped"
OUTPUT_BASE_FOLDER = "summarized"

def get_latest_scraped_folder():
    subfolders = [f for f in glob.glob(os.path.join(SCRAPED_FOLDER, "*")) if os.path.isdir(f)]
    if not subfolders:
        raise FileNotFoundError("scraped フォルダに処理済みCSVが見つかりません。")
    return max(subfolders, key=os.path.getmtime)

def create_output_folder():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_folder = os.path.join(OUTPUT_BASE_FOLDER, timestamp)
    os.makedirs(output_folder, exist_ok=True)
    return output_folder

def summarize_scraped_data(input_folder, output_folder):
    writers = {}

    for csv_file in glob.glob(os.path.join(input_folder, "*.csv")):
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ebay_user_id = row["ebay_user_id"]

                if ebay_user_id not in writers:
                    out_path = os.path.join(output_folder, f"{ebay_user_id}_summary.csv")
                    out_file = open(out_path, mode="w", encoding="utf-8", newline="")
                    writer = csv.DictWriter(out_file, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    writers[ebay_user_id] = (writer, out_file)

                writer, _ = writers[ebay_user_id]
                writer.writerow(row)

    for _, file_obj in writers.values():
        file_obj.close()

if __name__ == "__main__":
    try:
        input_folder = get_latest_scraped_folder()
        output_folder = create_output_folder()
        summarize_scraped_data(input_folder, output_folder)
        print(f"{output_folder} にユーザーごとの集約結果を書き出しました。")
    except Exception as e:
        print(f"エラー: {e}")
