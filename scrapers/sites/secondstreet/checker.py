from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready

ADD_CART_XPATH = '//p[@class="addCartText"]'
ACCESS_DENIED_TEXT = 'Access Denied'


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver)

    final_url = driver.current_url
    if final_url != url:
        driver.get(final_url)
        wait_ready(driver)

    page_source = driver.page_source
    if ACCESS_DENIED_TEXT in page_source:
        return ScrapeStatus.UNKNOWN, 'access denied'

    try:
        elem = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, ADD_CART_XPATH))
        )
        return ScrapeStatus.IN_STOCK, elem.text or 'cart present'
    except Exception:
        return ScrapeStatus.OUT_OF_STOCK, 'cart missing'
