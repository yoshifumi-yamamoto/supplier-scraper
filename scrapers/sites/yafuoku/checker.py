import os

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready

BUY_BUTTON_XPATH = '//button[contains(text(), "今すぐ落札") or contains(text(), "購入手続きへ") or contains(text(), "入札")]'
ENDED_TEXT_XPATH = '//p[contains(text(), "このオークションは終了しています")]'
SOLD_OUT_XPATH = '//*[contains(text(), "売り切れ") or contains(text(), "落札されました")]'
READY_SLEEP_SECONDS = float(os.getenv("YAFUOKU_READY_SLEEP_SECONDS", "0.6"))
BUY_WAIT_SECONDS = float(os.getenv("YAFUOKU_BUY_WAIT_SECONDS", "1.5"))


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver, sleep_sec=READY_SLEEP_SECONDS)

    try:
        WebDriverWait(driver, BUY_WAIT_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, BUY_BUTTON_XPATH))
        )
        return ScrapeStatus.IN_STOCK, "buy button present"
    except TimeoutException:
        pass

    ended = driver.find_elements(By.XPATH, ENDED_TEXT_XPATH)
    if ended:
        return ScrapeStatus.OUT_OF_STOCK, "auction ended"

    if driver.find_elements(By.XPATH, SOLD_OUT_XPATH):
        return ScrapeStatus.OUT_OF_STOCK, "sold out marker"

    return ScrapeStatus.UNKNOWN, "buy button missing without end marker"
