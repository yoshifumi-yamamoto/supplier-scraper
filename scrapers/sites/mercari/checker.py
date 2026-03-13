from urllib.parse import urlparse

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scrapers.common.models import ScrapeStatus
from scrapers.common.browser import wait_ready


PURCHASE_BUTTON_XPATH = '//button[contains(text(), "購入手続きへ")]'
PURCHASE_DIV_BUTTON_XPATH = '//div[@name="purchase"]/button'
SHOPS_PURCHASE_XPATH = (
    '//button[normalize-space()="購入手続きへ" and not(@disabled)] | '
    '//a[normalize-space()="購入手続きへ"]'
)
DELETED_XPATH = '//p[contains(text(), "削除されています")]'
NOT_FOUND_XPATH = '//p[contains(text(), "見つかりませんでした")]'
SHOPS_OOS_XPATH = '//p[@data-testid="out-of-stock"]'
LOAD_FAILED_XPATH = '//*[contains(text(), "ページの読み込みに失敗しました")]'


def normalize_mercari_url(raw_url: str | None) -> str | None:
    if raw_url is None:
        return None

    url = str(raw_url).strip()
    if not url:
        return None

    url = url.replace('\ufeff', '').replace('\r', '').replace('\n', '')
    if url.startswith('//'):
        url = f'https:{url}'
    elif not urlparse(url).scheme:
        url = f"https://{url.lstrip('/')}"

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return None
    if not parsed.netloc:
        return None
    if 'mercari.com' not in parsed.netloc.lower():
        return None
    return url



def _detect_mercari_shops_status(driver) -> tuple[ScrapeStatus, str]:
    out_of_stock_tag = driver.find_elements(By.XPATH, SHOPS_OOS_XPATH)
    if out_of_stock_tag:
        return ScrapeStatus.OUT_OF_STOCK, 'shops_oos_tag'

    body_text = ''
    try:
        body_text = driver.find_element(By.TAG_NAME, 'body').text
    except Exception:
        body_text = ''

    sold_markers = ('売り切れました', '売り切れ', 'SOLD', '在庫なし')
    if any(marker in body_text for marker in sold_markers):
        return ScrapeStatus.OUT_OF_STOCK, 'shops_sold_marker'

    purchase_elements = driver.find_elements(By.XPATH, SHOPS_PURCHASE_XPATH)
    if any(el.is_displayed() for el in purchase_elements):
        return ScrapeStatus.IN_STOCK, 'shops_purchase_cta'

    return ScrapeStatus.UNKNOWN, 'shops_unknown'



def _detect_standard_status(driver) -> tuple[ScrapeStatus, str]:
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, PURCHASE_BUTTON_XPATH))
        )
        return ScrapeStatus.IN_STOCK, 'purchase_button'
    except TimeoutException:
        pass

    if driver.find_elements(By.XPATH, DELETED_XPATH):
        return ScrapeStatus.OUT_OF_STOCK, 'deleted'
    if driver.find_elements(By.XPATH, NOT_FOUND_XPATH):
        return ScrapeStatus.OUT_OF_STOCK, 'not_found'
    if driver.find_elements(By.XPATH, SHOPS_OOS_XPATH):
        return ScrapeStatus.OUT_OF_STOCK, 'shops_oos'

    error_text_elements = driver.find_elements(By.XPATH, LOAD_FAILED_XPATH)
    if error_text_elements:
        driver.refresh()
        wait_ready(driver)
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, PURCHASE_BUTTON_XPATH))
            )
            return ScrapeStatus.IN_STOCK, 'purchase_button_retry'
        except Exception:
            sold_out_button = driver.find_elements(By.XPATH, '//button[contains(text(), "売り切れました")]')
            if sold_out_button:
                return ScrapeStatus.OUT_OF_STOCK, 'sold_out_button'
            return ScrapeStatus.OUT_OF_STOCK, 'retry_failed'

    return ScrapeStatus.OUT_OF_STOCK, 'purchase_missing'



def check_stock_status(driver, url: str) -> tuple[ScrapeStatus, str]:
    normalized_url = normalize_mercari_url(url)
    if not normalized_url:
        return ScrapeStatus.UNKNOWN, 'invalid_url'

    try:
        driver.get(normalized_url)
    except WebDriverException as exc:
        if 'invalid argument' in str(exc).lower():
            return ScrapeStatus.UNKNOWN, 'invalid_url_argument'
        raise
    wait_ready(driver)
    is_shops = 'shops' in normalized_url
    if is_shops:
        return _detect_mercari_shops_status(driver)
    return _detect_standard_status(driver)
