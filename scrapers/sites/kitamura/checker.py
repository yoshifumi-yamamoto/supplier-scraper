from selenium.webdriver.common.by import By

from scrapers.common.browser import wait_ready
from scrapers.common.models import ScrapeStatus


SOLD_OUT_TOKEN = 'https://schema.org/SoldOut'


def _first_used_detail_url(driver) -> str | None:
    links: list[str] = []
    for anchor in driver.find_elements(By.TAG_NAME, 'a'):
        href = (anchor.get_attribute('href') or '').strip()
        if '/ec/used/' in href and href not in links:
            links.append(href.split('#')[0])
    return links[0] if links else None


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    driver.get(url)
    wait_ready(driver)
    source = driver.page_source.replace('\/', '/')

    if '/ec/list?' in url and 'type=u' in url:
        used_url = _first_used_detail_url(driver)
        return (ScrapeStatus.IN_STOCK, used_url or url) if used_url else (ScrapeStatus.OUT_OF_STOCK, url)
    if '/ec/used/' in url:
        return ScrapeStatus.IN_STOCK, url
    if '/ec/pd/' in url:
        if SOLD_OUT_TOKEN in source:
            return ScrapeStatus.OUT_OF_STOCK, url
        return ScrapeStatus.IN_STOCK, url
    return ScrapeStatus.UNKNOWN, url
