from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from scrapers.common.browser import wait_ready
from scrapers.common.models import ScrapeStatus


def _resolve_target_url(driver, url: str) -> str | None:
    if '/product/other/' not in url:
        return url
    driver.get(url)
    wait_ready(driver)
    candidates = []
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        if not href:
            continue
        full = urljoin(url, href).replace('&amp;', '&')
        if '/product/detail/' in full and 'tenpo_cd=' in full and full not in candidates:
            candidates.append(full.split('#')[0])
    if candidates:
        return candidates[0]
    return None


def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    target = _resolve_target_url(driver, url)
    if not target:
        return ScrapeStatus.OUT_OF_STOCK, 'detail_not_found'
    driver.get(target)
    wait_ready(driver)
    source = driver.page_source
    if 'カートに入れる' in source:
        return ScrapeStatus.IN_STOCK, 'cart_available'
    if '品切れ' in source or '売り切れ' in source:
        return ScrapeStatus.OUT_OF_STOCK, 'sold_out_marker'
    return ScrapeStatus.UNKNOWN, 'status_unknown'
