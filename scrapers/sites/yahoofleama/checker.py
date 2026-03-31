import os

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready

BUY_BUTTON_XPATH = '//a[@id="item_buy_button"]'
SOLD_OUT_XPATH = (
    '//*[contains(text(), "売り切れ")] | '
    '//*[contains(text(), "この商品は売り切れです")] | '
    '//*[contains(text(), "購入できません")]'
)
READY_SLEEP_SECONDS = float(os.getenv("YAHOOFLEAMA_READY_SLEEP_SECONDS", "0.6"))
BUY_WAIT_SECONDS = float(os.getenv("YAHOOFLEAMA_BUY_WAIT_SECONDS", "1.5"))


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver, sleep_sec=READY_SLEEP_SECONDS)

    try:
        WebDriverWait(driver, BUY_WAIT_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, BUY_BUTTON_XPATH))
        )
        return ScrapeStatus.IN_STOCK, 'buy button present'
    except TimeoutException:
        if driver.find_elements(By.XPATH, SOLD_OUT_XPATH):
            return ScrapeStatus.OUT_OF_STOCK, 'sold out marker'
        return ScrapeStatus.UNKNOWN, 'buy button missing without sold-out marker'
