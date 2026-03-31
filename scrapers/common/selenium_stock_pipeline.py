import os
from typing import Callable, Optional, Union

from scrapers.common.browser import build_chrome
from scrapers.common.items import fetch_active_items_by_domain, update_item_stock_bulk
from scrapers.common.logging_utils import json_log
from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step

STATUS_MAP = {
    ScrapeStatus.IN_STOCK: "在庫あり",
    ScrapeStatus.OUT_OF_STOCK: "在庫なし",
    ScrapeStatus.UNKNOWN: "不明",
}


def _env_int(name: str, default: int) -> int:
    return max(int(os.getenv(name, str(default))), 1)


def _select_shard_items(items: list[dict], shard_index: int, shard_total: int) -> list[dict]:
    if shard_total <= 1:
        return items
    return [row for idx, row in enumerate(items) if idx % shard_total == shard_index]


def run_sequential_stock_pipeline(
    *,
    run_id: str,
    site: str,
    domains: Union[str, list[str]],
    checker: Callable[[object, str], tuple[ScrapeStatus, str]],
    fetch_page_size: Optional[int] = None,
    fetch_kwargs: Optional[dict] = None,
    rebuild_every_env: str,
    rebuild_every_default: int,
    batch_size_env: str,
    batch_size_default: int,
) -> dict:
    shard_total = max(int(os.getenv("SCRAPER_SHARD_TOTAL", "1")), 1)
    shard_index = max(int(os.getenv("SCRAPER_SHARD_INDEX", "0")), 0)
    fetch_step = start_step(run_id, "fetch_items")
    fetch_kwargs = dict(fetch_kwargs or {})
    if fetch_page_size is not None:
        fetch_kwargs["page_size"] = fetch_page_size

    try:
        all_items = fetch_active_items_by_domain(domains, **fetch_kwargs)
        items = _select_shard_items(all_items, shard_index, shard_total)
        if not items:
            if shard_total > 1:
                finish_step(fetch_step, "success", f"{site} shard {shard_index + 1}/{shard_total} no target items")
            else:
                finish_step(fetch_step, "success", f"{site} no target items")
            return {"status": "success", "message": f"{site} pipeline completed: 0 items"}
        finish_step(fetch_step, "success", f"fetched {len(items)} items")
    except Exception as exc:
        finish_step(fetch_step, "failed", f"fetch failed: {exc}")
        raise

    if shard_total > 1:
        json_log(
            "info",
            f"{site} shard plan",
            run_id=run_id,
            shard_index=shard_index,
            shard_total=shard_total,
            items=len(items),
        )

    driver = build_chrome(headless=True)
    processed = 0
    rebuild_every = _env_int(rebuild_every_env, rebuild_every_default)
    update_batch_size = _env_int(batch_size_env, batch_size_default)
    pending_updates: list[dict[str, object]] = []

    def flush_updates() -> None:
        nonlocal pending_updates
        if not pending_updates:
            return
        batch = pending_updates
        pending_updates = []
        update_item_stock_bulk(batch)

    try:
        for row in items:
            if processed > 0 and processed % rebuild_every == 0:
                flush_updates()
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = build_chrome(headless=True)

            ebay_item_id = row.get("ebay_item_id")
            if not ebay_item_id:
                continue

            step = start_step(run_id, f"check:{ebay_item_id}")
            try:
                status, message = checker(driver, row.get("stocking_url") or "")
                pending_updates.append(
                    {
                        "ebay_item_id": ebay_item_id,
                        "scraped_stock_status": STATUS_MAP[status],
                        "is_scraped": (status != ScrapeStatus.UNKNOWN),
                    }
                )
                finish_step(step, "success", message)
                processed += 1
                if len(pending_updates) >= update_batch_size:
                    flush_updates()
            except Exception as exc:
                finish_step(step, "failed", str(exc))
                raise

        flush_updates()
    except Exception:
        try:
            flush_updates()
        except Exception as flush_exc:  # noqa: BLE001
            json_log("warning", f"{site} bulk update flush failed", error=str(flush_exc)[:300])
        raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {"status": "success", "message": f"{site} pipeline completed: {processed} items"}
