import os
import shutil

# 削除対象のフォルダ
FOLDERS_TO_DELETE = ["input", "split", "scraped", "summarized"]

def delete_folders(folders):
    for folder in folders:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"[削除済み] {folder}")
            except Exception as e:
                print(f"[エラー] {folder} の削除に失敗しました: {e}")
        else:
            print(f"[スキップ] {folder} は存在しません。")

if __name__ == "__main__":
    delete_folders(FOLDERS_TO_DELETE)
