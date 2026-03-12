import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
ITEMS_TABLE = os.getenv("ITEMS_TABLE", "items")
DEFAULT_PAGE_SIZE = int(os.getenv("SUPABASE_PAGE_SIZE", "50"))
MIN_PAGE_SIZE = int(os.getenv("SUPABASE_MIN_PAGE_SIZE", "10"))
FETCH_MAX_RETRIES = int(os.getenv("FETCH_MAX_RETRIES", "5"))
FETCH_BACKOFF_BASE = float(os.getenv("FETCH_BACKOFF_BASE", "2.0"))
UPDATE_MAX_RETRIES = int(os.getenv("UPDATE_MAX_RETRIES", "4"))


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def fetch_active_items_by_domain(domain: str, page_size: int | None = None) -> list[dict[str, Any]]:
    if not _enabled():
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY is not set")
    url = f"{SUPABASE_URL}/rest/v1/{ITEMS_TABLE}"
    size = page_size or DEFAULT_PAGE_SIZE
    all_rows: list[dict[str, Any]] = []
    last_item_id = None
    page = 1
    domain_lc = domain.lower()
    while True:
        params = {
            "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status",
            "listing_status": "eq.Active",
            "stocking_url": "not.is.null",
            "order": "ebay_item_id.asc",
            "limit": str(size),
        }
        if last_item_id:
            params["ebay_item_id"] = f"gt.{last_item_id}"
        data = None
        for attempt in range(FETCH_MAX_RETRIES):
            try:
                res = requests.get(url, headers=_headers(), params=params, timeout=45)
                if res.status_code >= 500:
                    preview = res.text[:300].replace("\n", " ")
                    raise requests.HTTPError(f"Supabase {res.status_code} on page {page}: {preview}", response=res)
                res.raise_for_status()
                data = res.json()
                break
            except Exception as exc:
                if '57014' in str(exc) and size > MIN_PAGE_SIZE:
                    size = max(MIN_PAGE_SIZE, size // 2)
                if attempt == FETCH_MAX_RETRIES - 1:
                    raise
                time.sleep(FETCH_BACKOFF_BASE * (2 ** attempt))
        if not data:
            break
        filtered = []
        for row in data:
            stocking_url = (row.get("stocking_url") or "").lower()
            if domain_lc in stocking_url:
                filtered.append(row)
        all_rows.extend(filtered)
        last_item_id = data[-1]["ebay_item_id"]
        if len(data) < size:
            break
        page += 1
    return all_rows


def update_item_stock(ebay_item_id: str, scraped_stock_status: str, *, is_scraped: bool = True) -> None:
    if not _enabled():
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY is not set")
    payload = {
        "scraped_stock_status": scraped_stock_status,
        "scraped_updated_at": datetime.now(timezone.utc).isoformat(),
        "is_scraped": is_scraped,
    }
    last_exc = None
    for attempt in range(UPDATE_MAX_RETRIES):
        try:
            res = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{ITEMS_TABLE}?ebay_item_id=eq.{ebay_item_id}",
                headers=_headers(),
                json=payload,
                timeout=30,
            )
            if res.status_code >= 500:
                preview = res.text[:300].replace("\n", " ")
                raise requests.HTTPError(f"Supabase {res.status_code}: {preview}", response=res)
            res.raise_for_status()
            return
        except Exception as exc:
            last_exc = exc
            if attempt == UPDATE_MAX_RETRIES - 1:
                raise
            time.sleep(1.5 * (2 ** attempt))
    raise last_exc  # pragma: no cover
