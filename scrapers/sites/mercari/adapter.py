import os

from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock
from scrapers.common.run_store import finish_step, start_step
from scrapers.common.models import ScrapeStatus
from scrapers.sites.mercari.checker import check_stock_status


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: '在庫あり',
    ScrapeStatus.OUT_OF_STOCK: '在庫なし',
    ScrapeStatus.UNKNOWN: '不明',
}

MERCARI_REBUILD_EVERY = int(os.getenv("MERCARI_REBUILD_EVERY", "30"))



def run_pipeline(run_id: str) -> dict:
    fetch_step = start_step(run_id, 'fetch_items')
    try:
        items = fetch_active_items_by_domain(['mercari.com', 'jp.mercari.com'], page_size=50)
        if not items:
            finish_step(fetch_step, 'success', 'mercari no target items')
            return {'status': 'success', 'message': 'mercari pipeline completed: 0 items'}
        finish_step(fetch_step, 'success', f'fetched {len(items)} items')
    except Exception as exc:
        finish_step(fetch_step, 'failed', f'fetch failed: {exc}')
        raise

    driver = build_chrome(headless=True)
    processed = 0
    rebuild_every = max(MERCARI_REBUILD_EVERY, 1)
    try:
        for row in items:
            if processed > 0 and processed % rebuild_every == 0:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = build_chrome(headless=True)
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
                err = str(exc)
                timeout_like = 'Timed out receiving message from renderer' in err or 'timeout:' in err.lower()
                if timeout_like:
                    try:
                        update_item_stock(
                            ebay_item_id=ebay_item_id,
                            scraped_stock_status='不明',
                            is_scraped=False,
                        )
                    except Exception:
                        pass
                    finish_step(step, 'success', f'renderer timeout skipped: {err[:300]}')
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = build_chrome(headless=True)
                    continue
                finish_step(step, 'failed', err)
                raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {'status': 'success', 'message': f'mercari pipeline completed: {processed} items'}
