from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock
from scrapers.common.logging_utils import json_log
from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step
from scrapers.sites.yodobashi.checker import check_stock_status


def _to_japanese(status: ScrapeStatus) -> str:
    if status == ScrapeStatus.IN_STOCK:
        return "在庫あり"
    if status == ScrapeStatus.OUT_OF_STOCK:
        return "在庫なし"
    return "不明"


def run_pipeline(run_id: str) -> dict:
    fetch_step = start_step(run_id=run_id, step_name='fetch_items')
    try:
        items = fetch_active_items_by_domain('yodobashi.com')
        finish_step(fetch_step, status='success', message=f'fetched={len(items)}')
    except Exception as exc:  # noqa: BLE001
        finish_step(fetch_step, status='failed', message=str(exc))
        return {
            'run_id': run_id,
            'site': 'yodobashi',
            'status': ScrapeStatus.ERROR.value,
            'message': f'fetch failed: {exc}',
        }

    if not items:
        json_log('info', 'yodobashi no target items', run_id=run_id, site='yodobashi')
        return {
            'run_id': run_id,
            'site': 'yodobashi',
            'status': 'success',
            'message': 'yodobashi pipeline completed: 0 items',
        }

    driver = build_chrome(headless=True)
    checked = 0
    in_stock = 0
    out_of_stock = 0
    unknown = 0
    step_id = start_step(run_id=run_id, step_name='check_stock')
    try:
        for row in items:
            status = ScrapeStatus.UNKNOWN
            try:
                status, _ = check_stock_status(driver, row.get('stocking_url') or '')
            except Exception as exc:  # noqa: BLE001
                json_log('warning', 'yodobashi check failed', site='yodobashi', ebay_item_id=row.get('ebay_item_id'), error=str(exc))
                status = ScrapeStatus.UNKNOWN
            jp = _to_japanese(status)
            update_item_stock(row['ebay_item_id'], jp, is_scraped=True)
            checked += 1
            if status == ScrapeStatus.IN_STOCK:
                in_stock += 1
            elif status == ScrapeStatus.OUT_OF_STOCK:
                out_of_stock += 1
            else:
                unknown += 1
        finish_step(step_id, status='success', message=f'checked={checked} in={in_stock} out={out_of_stock} unknown={unknown}')
    except Exception as exc:  # noqa: BLE001
        finish_step(step_id, status='failed', message=str(exc))
        return {
            'run_id': run_id,
            'site': 'yodobashi',
            'status': ScrapeStatus.ERROR.value,
            'message': f'check failed: {exc}',
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {
        'run_id': run_id,
        'site': 'yodobashi',
        'status': 'success',
        'message': f'yodobashi pipeline completed: checked={checked} in={in_stock} out={out_of_stock} unknown={unknown}',
    }
