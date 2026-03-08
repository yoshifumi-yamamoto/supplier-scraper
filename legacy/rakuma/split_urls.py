import os
import csv
import glob
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MAX_ROWS_PER_FILE = int(os.getenv("MAX_ROWS_PER_FILE", 1000))
INPUT_FOLDER = "input"
OUTPUT_BASE_FOLDER = "split"

def get_latest_input_csv():
    csv_files = glob.glob(os.path.join(INPUT_FOLDER, "rakuma_urls_*.csv"))
    if not csv_files:
        raise FileNotFoundError("input フォルダにCSVファイルが見つかりません。")
    return max(csv_files, key=os.path.getmtime)

def create_output_folder():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = os.path.join(OUTPUT_BASE_FOLDER, timestamp)
    os.makedirs(path, exist_ok=True)
    return path

def split_csv_by_user(input_csv, output_folder):
    writers = {}
    row_counts = {}

    with open(input_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            user_id = row["ebay_user_id"]
            if user_id not in row_counts:
                row_counts[user_id] = 0

            file_index = row_counts[user_id] // MAX_ROWS_PER_FILE + 1
            filename = f"{user_id}_urls_{file_index}.csv"
            filepath = os.path.join(output_folder, filename)

            if filepath not in writers:
                wf = open(filepath, mode="w", encoding="utf-8", newline="")
                writer = csv.DictWriter(wf, fieldnames=reader.fieldnames)
                writer.writeheader()
                writers[filepath] = (writer, wf)

            writer, _ = writers[filepath]
            writer.writerow(row)
            row_counts[user_id] += 1

    for _, f in writers.values():
        f.close()

if __name__ == "__main__":
    try:
        input_csv = get_latest_input_csv()
        output_folder = create_output_folder()
        split_csv_by_user(input_csv, output_folder)
        print(f"{output_folder} にファイルを分割して出力しました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
