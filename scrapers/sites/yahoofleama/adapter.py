from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock
from scrapers.common.error_text import describe_exception
from scrapers.common.run_store import finish_step, start_step
from scrapers.common.models import ScrapeStatus
from scrapers.sites.yahoofleama.checker import check_stock_status


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: '在庫あり',
    ScrapeStatus.OUT_OF_STOCK: '在庫なし',
    ScrapeStatus.UNKNOWN: '不明',
}



def run_pipeline(run_id: str) -> dict:
    fetch_step = start_step(run_id, 'fetch_items')
    try:
        items = fetch_active_items_by_domain('paypayfleamarket.yahoo.co.jp', page_size=50)
        if not items:
            finish_step(fetch_step, 'success', 'yahoofleama no target items')
            return {'status': 'success', 'message': 'yahoofleama pipeline completed: 0 items'}
        finish_step(fetch_step, 'success', f'fetched {len(items)} items')
    except Exception as exc:
        finish_step(fetch_step, 'failed', f'fetch failed: {exc}')
        raise

    driver = build_chrome(headless=True)
    processed = 0
    try:
        for row in items:
            ebay_item_id = row.get('ebay_item_id')
            if not ebay_item_id:
                continue

            step = start_step(run_id, f'check:{ebay_item_id}')
            try:
                status, message = check_stock_status(driver, row.get('stocking_url') or '')
                update_item_stock(
                    ebay_item_id=ebay_item_id,
                    scraped_stock_status=STATUS_MAP[status],
                    is_scraped=(status != ScrapeStatus.UNKNOWN),
                )
                finish_step(step, 'success', message)
                processed += 1
            except Exception as exc:
                finish_step(step, 'failed', describe_exception(exc))
                raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {'status': 'success', 'message': f'yahoofleama pipeline completed: {processed} items'}
