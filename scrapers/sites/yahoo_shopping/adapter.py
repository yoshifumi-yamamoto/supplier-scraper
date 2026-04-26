from __future__ import annotations

from urllib.parse import urlparse

from scrapers.common.items import fetch_active_items_by_domain, update_item_stock_bulk
from scrapers.common.logging_utils import json_log
from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step
from scrapers.sites.yahoo_shopping.client import (
    YahooShoppingApiError,
    auth_ready,
    fetch_offer_by_item,
)
from scrapers.sites.yahoo_shopping.normalizer import normalize_offer


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: "在庫あり",
    ScrapeStatus.OUT_OF_STOCK: "在庫なし",
    ScrapeStatus.UNKNOWN: "不明",
    ScrapeStatus.ERROR: "エラー",
}

YAHOO_SHOPPING_DOMAINS = ["store.shopping.yahoo.co.jp", "shopping.yahoo.co.jp"]


def _parse_item_ref(stocking_url: str) -> tuple[str, str] | None:
    if not stocking_url:
        return None
    parsed = urlparse(stocking_url)
    host = (parsed.netloc or "").lower()
    if host not in YAHOO_SHOPPING_DOMAINS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    seller_id = parts[0]
    item_code = parts[1].replace(".html", "")
    if not seller_id or not item_code:
        return None
    return seller_id, item_code


def run_pipeline(run_id: str) -> dict:
    fetch_step = start_step(run_id=run_id, step_name="fetch_items")
    try:
        items = fetch_active_items_by_domain(YAHOO_SHOPPING_DOMAINS)
        if not items:
            finish_step(fetch_step, status="success", message="yahoo shopping no target items")
            return {
                "run_id": run_id,
                "site": "yahoo_shopping",
                "status": "success",
                "message": "yahoo shopping pipeline completed: 0 items",
                "source": "api",
            }
        finish_step(fetch_step, status="success", message=f"fetched {len(items)} items")
    except Exception as exc:  # noqa: BLE001
        finish_step(fetch_step, status="failed", message=str(exc))
        return {
            "run_id": run_id,
            "site": "yahoo_shopping",
            "status": ScrapeStatus.ERROR.value,
            "message": f"fetch failed: {exc}",
            "source": "api",
        }

    if not auth_ready():
        return {
            "run_id": run_id,
            "site": "yahoo_shopping",
            "status": ScrapeStatus.ERROR.value,
            "message": "yahoo shopping auth not configured",
            "source": "api",
        }

    processed = 0
    in_stock = 0
    out_of_stock = 0
    unknown = 0
    pending_updates: list[dict[str, object]] = []

    for row in items:
        ebay_item_id = row.get("ebay_item_id")
        if not ebay_item_id:
            continue
        stocking_url = row.get("stocking_url") or ""
        item_ref = _parse_item_ref(stocking_url)
        step_id = start_step(run_id=run_id, step_name=f"check:{ebay_item_id}")
        try:
            if not item_ref:
                status = ScrapeStatus.UNKNOWN
                message = "yahoo shopping seller/item code could not be resolved from stocking_url"
            else:
                seller_id, item_code = item_ref
                raw = fetch_offer_by_item(seller_id=seller_id, item_code=item_code)
                status, message = normalize_offer(raw)
            pending_updates.append(
                {
                    "ebay_item_id": ebay_item_id,
                    "scraped_stock_status": STATUS_MAP[status],
                    "is_scraped": status != ScrapeStatus.UNKNOWN,
                }
            )
            json_log(
                "info",
                "yahoo shopping item api result",
                run_id=run_id,
                site="yahoo_shopping",
                ebay_item_id=ebay_item_id,
                stocking_url=stocking_url,
                scrape_status=STATUS_MAP[status],
                scrape_message=message,
                source="api",
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
        except YahooShoppingApiError as exc:
            finish_step(step_id, status="failed", message=str(exc))
            return {
                "run_id": run_id,
                "site": "yahoo_shopping",
                "status": ScrapeStatus.ERROR.value,
                "message": f"check failed: {exc}",
                "source": "api",
            }
        except Exception as exc:  # noqa: BLE001
            finish_step(step_id, status="failed", message=str(exc))
            return {
                "run_id": run_id,
                "site": "yahoo_shopping",
                "status": ScrapeStatus.ERROR.value,
                "message": f"check failed: {exc}",
                "source": "api",
            }

    if pending_updates:
        update_item_stock_bulk(pending_updates)

    return {
        "run_id": run_id,
        "site": "yahoo_shopping",
        "status": "success",
        "message": f"yahoo shopping pipeline completed: checked={processed} in={in_stock} out={out_of_stock} unknown={unknown}",
        "source": "api",
    }
