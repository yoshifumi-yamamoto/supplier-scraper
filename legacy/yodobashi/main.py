import subprocess
import os
import platform
import sys
import shutil

def cleanup_processes_and_tmp():
    # 残骸プロセスを殺す
    print("古い Chrome / chromedriver プロセスを終了します...")
    subprocess.run("pkill -f chromedriver", shell=True)
    subprocess.run("pkill -f -- 'chrome'", shell=True)

    # tmp_chrome フォルダを初期化
    tmp_base = os.path.join(os.getcwd(), "tmp_chrome")
    print(f"tmp_chrome フォルダを初期化します: {tmp_base}")
    shutil.rmtree(tmp_base, ignore_errors=True)
    os.makedirs(tmp_base, exist_ok=True)

def main():
    # 🟢 ここで一度だけ前処理
    cleanup_processes_and_tmp()

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
