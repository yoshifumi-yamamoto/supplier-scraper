import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock_bulk
from scrapers.common.logging_utils import json_log
from scrapers.common.run_store import finish_step, start_step
from scrapers.common.models import ScrapeStatus
from scrapers.sites.mercari.checker import check_stock_status


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: '在庫あり',
    ScrapeStatus.OUT_OF_STOCK: '在庫なし',
    ScrapeStatus.UNKNOWN: '不明',
}

MERCARI_REBUILD_EVERY = int(os.getenv("MERCARI_REBUILD_EVERY", "30"))
MERCARI_UPDATE_BATCH_SIZE = int(os.getenv("MERCARI_UPDATE_BATCH_SIZE", "50"))
MERCARI_BROWSER_WORKERS = int(os.getenv("MERCARI_BROWSER_WORKERS", "3"))


def _split_items(items: list[dict], worker_count: int) -> list[list[dict]]:
    if worker_count <= 1 or len(items) <= 1:
        return [items]
    chunks: list[list[dict]] = [[] for _ in range(worker_count)]
    for index, row in enumerate(items):
        chunks[index % worker_count].append(row)
    return [chunk for chunk in chunks if chunk]


def _process_chunk(run_id: str, rows: list[dict], rebuild_every: int, update_batch_size: int) -> int:
    driver = build_chrome(headless=True)
    processed = 0
    pending_updates: list[dict[str, object]] = []

    def flush_updates() -> None:
        nonlocal pending_updates
        if not pending_updates:
            return
        batch = pending_updates
        pending_updates = []
        update_item_stock_bulk(batch)

    try:
        for row in rows:
            if processed > 0 and processed % rebuild_every == 0:
                flush_updates()
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
                pending_updates.append(
                    {
                        'ebay_item_id': ebay_item_id,
                        'scraped_stock_status': STATUS_MAP[status],
                        'is_scraped': (status != ScrapeStatus.UNKNOWN),
                    }
                )
                finish_step(step, 'success', message)
                processed += 1
                if len(pending_updates) >= update_batch_size:
                    flush_updates()
            except Exception as exc:
                err = str(exc)
                timeout_like = 'Timed out receiving message from renderer' in err or 'timeout:' in err.lower()
                if timeout_like:
                    pending_updates.append(
                        {
                            'ebay_item_id': ebay_item_id,
                            'scraped_stock_status': '不明',
                            'is_scraped': False,
                        }
                    )
                    finish_step(step, 'success', f'renderer timeout skipped: {err[:300]}')
                    if len(pending_updates) >= update_batch_size:
                        flush_updates()
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = build_chrome(headless=True)
                    continue
                finish_step(step, 'failed', err)
                raise
        flush_updates()
        return processed
    except Exception:
        try:
            flush_updates()
        except Exception as flush_exc:  # noqa: BLE001
            json_log('warning', 'mercari bulk update flush failed', error=str(flush_exc)[:300])
        raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass


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

    rebuild_every = max(MERCARI_REBUILD_EVERY, 1)
    update_batch_size = max(MERCARI_UPDATE_BATCH_SIZE, 1)
    worker_count = max(1, min(MERCARI_BROWSER_WORKERS, len(items)))
    chunks = _split_items(items, worker_count)
    json_log('info', 'mercari worker plan', run_id=run_id, workers=worker_count, chunks=len(chunks), items=len(items))

    try:
        processed = 0
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(_process_chunk, run_id, chunk, rebuild_every, update_batch_size)
                for chunk in chunks
            ]
            for future in as_completed(futures):
                processed += future.result()
    except Exception:
        raise

    return {'status': 'success', 'message': f'mercari pipeline completed: {processed} items'}
