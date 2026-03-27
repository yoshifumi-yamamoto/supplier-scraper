import os
import time
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Any, Iterable, Union

import requests

from scrapers.common.logging_utils import json_log

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


def _normalize_stocking_domain(domain: str) -> str:
    return domain.strip().lower()


def _normalize_stocking_domains(domains: Union[str, Iterable[str]]) -> list[str]:
    if isinstance(domains, str):
        values = [domains]
    else:
        values = list(domains)

    normalized: list[str] = []
    for domain in values:
        value = _normalize_stocking_domain(domain)
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _build_fetch_params(domains: list[str], size: int, last_item_id: Union[str, None], *, use_stocking_domain: bool) -> dict[str, str]:
    params = {
        "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status,stocking_domain",
        "listing_status": "eq.Active",
        "order": "ebay_item_id.asc",
        "limit": str(size),
    }
    domain_patterns = ",".join(f"*{domain}*" for domain in domains)
    if use_stocking_domain:
        if len(domains) == 1:
            params["stocking_domain"] = f"eq.{quote(domains[0], safe='')}"
        else:
            quoted = ",".join(quote(domain, safe="") for domain in domains)
            params["stocking_domain"] = f"in.({quoted})"
    else:
        params["and"] = f"(stocking_url.not.is.null,stocking_url.ilike.any.{{{domain_patterns}}})"
    if last_item_id:
        params["ebay_item_id"] = f"gt.{last_item_id}"
    return params


def fetch_active_items_by_domain(domain: Union[str, Iterable[str]], page_size: Union[int, None] = None) -> list[dict[str, Any]]:
    if not _enabled():
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY is not set")
    started = time.monotonic()
    url = f"{SUPABASE_URL}/rest/v1/{ITEMS_TABLE}"
    size = page_size or DEFAULT_PAGE_SIZE
    normalized_domains = _normalize_stocking_domains(domain)
    if not normalized_domains:
        return []
    all_rows: list[dict[str, Any]] = []
    last_item_id = None
    page = 1
    use_stocking_domain = True
    fallback_used = False
    while True:
        params = _build_fetch_params(normalized_domains, size, last_item_id, use_stocking_domain=use_stocking_domain)
        data = None
        for attempt in range(FETCH_MAX_RETRIES):
            try:
                res = requests.get(url, headers=_headers(), params=params, timeout=45)
                if use_stocking_domain and res.status_code == 400 and "stocking_domain" in res.text:
                    use_stocking_domain = False
                    fallback_used = True
                    params = _build_fetch_params(
                        normalized_domains,
                        size,
                        last_item_id,
                        use_stocking_domain=False,
                    )
                    continue
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
        all_rows.extend(data)
        last_item_id = data[-1]["ebay_item_id"]
        if len(data) < size:
            break
        page += 1
    elapsed_ms = int((time.monotonic() - started) * 1000)
    json_log(
        "info",
        "items fetch finished",
        domain=",".join(normalized_domains),
        match_mode="stocking_domain" if use_stocking_domain else "stocking_url_ilike",
        fallback_used=fallback_used,
        rows=len(all_rows),
        pages=page,
        page_size=size,
        elapsed_ms=elapsed_ms,
    )
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
