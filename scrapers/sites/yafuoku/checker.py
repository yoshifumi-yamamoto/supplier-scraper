from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready

BUY_BUTTON_XPATH = '//button[contains(text(), "今すぐ落札") or contains(text(), "購入手続きへ") or contains(text(), "入札")]'
ENDED_TEXT_XPATH = '//p[contains(text(), "このオークションは終了しています")]'


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver)

    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, BUY_BUTTON_XPATH))
        )
        return ScrapeStatus.IN_STOCK, "buy button present"
    except TimeoutException:
        pass

    ended = driver.find_elements(By.XPATH, ENDED_TEXT_XPATH)
    if ended:
        return ScrapeStatus.OUT_OF_STOCK, "auction ended"

    return ScrapeStatus.OUT_OF_STOCK, "buy button missing"
