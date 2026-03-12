from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready

BUY_BUTTON_XPATH = '//a[@id="item_buy_button"]'


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver)

    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, BUY_BUTTON_XPATH))
        )
        return ScrapeStatus.IN_STOCK, 'buy button present'
    except TimeoutException:
        return ScrapeStatus.OUT_OF_STOCK, 'buy button missing'
