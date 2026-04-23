from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from scrapers.common.items import fetch_active_items_by_domain, update_item_stock_bulk
from scrapers.common.logging_utils import json_log
from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step
from scrapers.sites.rakuten.client import RakutenApiError, auth_ready, fetch_item_by_code
from scrapers.sites.rakuten.normalizer import normalize_item


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: "在庫あり",
    ScrapeStatus.OUT_OF_STOCK: "在庫なし",
    ScrapeStatus.UNKNOWN: "不明",
    ScrapeStatus.ERROR: "エラー",
}

RAKUTEN_DOMAINS = ["item.rakuten.co.jp", "www.rakuten.co.jp"]


def _parse_item_code_from_url(stocking_url: str) -> tuple[str, str] | None:
    if not stocking_url:
        return None
    parsed = urlparse(stocking_url)
    host = (parsed.netloc or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    shop_code, item_local_code = parts[0], parts[1]
    if not shop_code or not item_local_code:
        return None
    if host not in RAKUTEN_DOMAINS:
        return None
    return shop_code, item_local_code


def _log_item_result(*, run_id: str, ebay_item_id: str, stocking_url: str, item_code: str | None, shop_code: str | None, status: ScrapeStatus, message: str) -> None:
    json_log(
        "info",
        "rakuten item api result",
        run_id=run_id,
        site="rakuten",
        ebay_item_id=ebay_item_id,
        stocking_url=stocking_url,
        shop_code=shop_code,
        item_code=item_code,
        scrape_status=STATUS_MAP[status],
        scrape_message=message,
        source="api",
    )


def run_pipeline(run_id: str) -> dict[str, Any]:
    fetch_step = start_step(run_id=run_id, step_name="fetch_items")
    try:
        if not auth_ready():
            raise RakutenApiError("rakuten auth not configured")
        items = fetch_active_items_by_domain(RAKUTEN_DOMAINS, page_size=50)
        if not items:
            finish_step(fetch_step, status="success", message="rakuten no target items")
            return {
                "run_id": run_id,
                "site": "rakuten",
                "status": "success",
                "message": "rakuten api pipeline completed: 0 items",
                "source": "api",
            }
        finish_step(fetch_step, status="success", message=f"fetched {len(items)} items")
    except Exception as exc:  # noqa: BLE001
        finish_step(fetch_step, status="failed", message=str(exc))
        return {
            "run_id": run_id,
            "site": "rakuten",
            "status": ScrapeStatus.ERROR.value,
            "message": f"fetch failed: {exc}",
            "source": "api",
        }

    processed = 0
    in_stock = 0
    out_of_stock = 0
    unknown = 0
    pending_updates: list[dict[str, Any]] = []
    for row in items:
        ebay_item_id = row.get("ebay_item_id")
        if not ebay_item_id:
            continue
        stocking_url = row.get("stocking_url") or ""
        parsed = _parse_item_code_from_url(stocking_url)
        shop_code = parsed[0] if parsed else None
        item_code = parsed[1] if parsed else None
        step_id = start_step(run_id=run_id, step_name=f"check:{ebay_item_id}")
        try:
            if not item_code:
                status = ScrapeStatus.UNKNOWN
                message = "rakuten itemCode could not be resolved from stocking_url"
            else:
                raw = fetch_item_by_code(item_code, shop_code=shop_code)
                status, message = normalize_item(raw)
            pending_updates.append(
                {
                    "ebay_item_id": ebay_item_id,
                    "scraped_stock_status": STATUS_MAP[status],
                    "is_scraped": status != ScrapeStatus.UNKNOWN,
                }
            )
            _log_item_result(
                run_id=run_id,
                ebay_item_id=str(ebay_item_id),
                stocking_url=stocking_url,
                shop_code=shop_code,
                item_code=item_code,
                status=status,
                message=message,
            )
            if status == ScrapeStatus.IN_STOCK:
                in_stock += 1
            elif status == ScrapeStatus.OUT_OF_STOCK:
                out_of_stock += 1
            else:
                unknown += 1
            finish_step(step_id, status="success", message=message)
            processed += 1
            if len(pending_updates) >= 20:
                update_item_stock_bulk(pending_updates)
                pending_updates = []
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            json_log(
                "warning",
                "rakuten item api failed",
                run_id=run_id,
                site="rakuten",
                ebay_item_id=ebay_item_id,
                stocking_url=stocking_url,
                shop_code=shop_code,
                item_code=item_code,
                error=err[:300],
                source="api",
            )
            pending_updates.append(
                {
                    "ebay_item_id": ebay_item_id,
                    "scraped_stock_status": "不明",
                    "is_scraped": False,
                }
            )
            unknown += 1
            finish_step(step_id, status="success", message=f"rakuten api failed, marked unknown: {err[:300]}")
            processed += 1
            if len(pending_updates) >= 20:
                update_item_stock_bulk(pending_updates)
                pending_updates = []

    if pending_updates:
        update_item_stock_bulk(pending_updates)

    return {
        "run_id": run_id,
        "site": "rakuten",
        "status": "success",
        "message": f"rakuten api pipeline completed: checked={processed} in={in_stock} out={out_of_stock} unknown={unknown}",
        "source": "api",
    }
