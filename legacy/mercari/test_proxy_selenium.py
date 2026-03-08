from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time

CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
PROXY = "http://185.219.160.4:21271"
URL = "https://www.mercari.com/jp/"

options = Options()

# ✅ プロキシを一旦外してテスト
# options.add_argument(f"--proxy-server={PROXY}")

options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
# options.add_argument("--headless")  # 今はONにしない方がいい
options.add_argument("--disable-gpu")

service = Service(CHROMEDRIVER_PATH)
driver = webdriver.Chrome(service=service, options=options)

driver.set_page_load_timeout(15)

try:
    print("[INFO] アクセス開始")
    driver.get(URL)
    time.sleep(3)
    print("[INFO] タイトル取得:", driver.title)
except Exception as e:
    print("[ERROR]", e)

driver.quit()
