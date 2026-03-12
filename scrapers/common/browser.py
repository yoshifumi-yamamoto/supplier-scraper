import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait


def build_chrome(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,2400")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-features=Translate,BackForwardCache,AcceptCHFrame")
    options.add_argument("--dns-prefetch-disable")
    options.add_argument("user-agent=Mozilla/5.0")
    options.page_load_strategy = 'eager'
    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(45)
    return driver


def wait_ready(driver: webdriver.Chrome, sleep_sec: float = 2.0) -> None:
    WebDriverWait(driver, 45).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
    time.sleep(sleep_sec)
