from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock
from scrapers.common.run_store import finish_step, start_step
from scrapers.common.models import ScrapeStatus
from scrapers.sites.secondstreet.checker import check_stock_status


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: '在庫あり',
    ScrapeStatus.OUT_OF_STOCK: '在庫なし',
    ScrapeStatus.UNKNOWN: '不明',
}


def run_pipeline(run_id: str) -> dict:
    fetch_step = start_step(run_id, 'fetch_items')
    try:
        items = fetch_active_items_by_domain(['2ndstreet.jp', 'www.2ndstreet.jp'])
        if not items:
            finish_step(fetch_step, 'success', 'secondstreet no target items')
            return {'status': 'success', 'message': 'secondstreet pipeline completed: 0 items'}
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
                target_url = (row.get('stocking_url') or '').strip()
                if not target_url.startswith(('http://', 'https://')):
                    update_item_stock(
                        ebay_item_id=ebay_item_id,
                        scraped_stock_status='不明',
                        is_scraped=False,
                    )
                    finish_step(step, 'success', f'invalid url skipped: {target_url}')
                    continue
                status, message = check_stock_status(driver, target_url)
                update_item_stock(
                    ebay_item_id=ebay_item_id,
                    scraped_stock_status=STATUS_MAP[status],
                    is_scraped=(status != ScrapeStatus.UNKNOWN),
                )
                finish_step(step, 'success', message)
                processed += 1
            except Exception as exc:
                finish_step(step, 'failed', str(exc))
                raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {'status': 'success', 'message': f'secondstreet pipeline completed: {processed} items'}
