from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from scrapers.common.browser import wait_ready
from scrapers.common.models import ScrapeStatus


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver, sleep_sec=1.0)
    final_url = driver.current_url
    try:
        button = driver.find_element(By.XPATH, '//button[@class="cart-add-button "]/span[1]')
        if 'カートに入れる' in (button.text or ''):
            return ScrapeStatus.IN_STOCK, final_url
        return ScrapeStatus.OUT_OF_STOCK, final_url
    except NoSuchElementException:
        return ScrapeStatus.OUT_OF_STOCK, final_url
