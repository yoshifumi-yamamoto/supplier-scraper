import subprocess
import os
import platform
import sys

def main():
    scripts = [
        "fetch_urls.py",
        "split_urls.py",
        "scrape_status.py",
        "summarize_results.py",
        "upload_to_supabase.py",
        "delete_temp_data.py"
    ]

    for script in scripts:
        print(f"{script} を実行中...")
        result = subprocess.run(["python3", script])
        if result.returncode != 0:
            print(f"{script} でエラーが発生しました。処理を中断します。")
            sys.exit(1)  # エラーをcronに通知

        print(f"{script} の実行が完了しました。\n")

    # print("すべてのスクリプトが正常に完了しました。シャットダウンします。")
    # if platform.system() == "Linux":
    #     os.system("sudo /sbin/shutdown -h now")

if __name__ == "__main__":
    main()
