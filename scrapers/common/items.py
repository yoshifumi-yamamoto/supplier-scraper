import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Union

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
ITEM_UPDATE_MAX_WORKERS = int(os.getenv("ITEM_UPDATE_MAX_WORKERS", "4"))


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
        "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status,listing_state,stocking_domain,sku,title,price,image_url",
        "or": "(listing_status.eq.Active,listing_state.eq.ACTIVE)",
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


def _is_fetch_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        pattern in text
        for pattern in (
            "57014",
            "statement timeout",
            "canceling statement due to statement timeout",
            "read timed out",
            "readtimeout",
            "supabase 500",
            "supabase 502",
        )
    )


def _fetch_domain_rows(
    *,
    url: str,
    domains: list[str],
    size: int,
    use_stocking_domain: bool,
) -> tuple[list[dict[str, Any]], int, bool]:
    all_rows: list[dict[str, Any]] = []
    last_item_id = None
    page = 1
    fallback_used = False
    current_size = size
    while True:
        params = _build_fetch_params(domains, current_size, last_item_id, use_stocking_domain=use_stocking_domain)
        data = None
        for attempt in range(FETCH_MAX_RETRIES):
            try:
                res = requests.get(url, headers=_headers(), params=params, timeout=45)
                if use_stocking_domain and res.status_code == 400 and "stocking_domain" in res.text:
                    raise ValueError("stocking_domain unavailable")
                if res.status_code >= 500:
                    preview = res.text[:300].replace("\n", " ")
                    raise requests.HTTPError(f"Supabase {res.status_code} on page {page}: {preview}", response=res)
                res.raise_for_status()
                data = res.json()
                break
            except ValueError:
                raise
            except Exception as exc:
                if _is_fetch_timeout_error(exc) and current_size > MIN_PAGE_SIZE:
                    next_size = max(MIN_PAGE_SIZE, current_size // 2)
                    if next_size != current_size:
                        json_log(
                            "warning",
                            "items fetch reducing page size after timeout",
                            domain=",".join(domains),
                            page=page,
                            previous_page_size=current_size,
                            next_page_size=next_size,
                            error=str(exc)[:300],
                        )
                    current_size = next_size
                    params = _build_fetch_params(domains, current_size, last_item_id, use_stocking_domain=use_stocking_domain)
                if attempt == FETCH_MAX_RETRIES - 1:
                    raise
                time.sleep(FETCH_BACKOFF_BASE * (2 ** attempt))
        if not data:
            break
        all_rows.extend(data)
        last_item_id = data[-1]["ebay_item_id"]
        if len(data) < current_size:
            break
        page += 1
    return all_rows, page, fallback_used


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
    use_stocking_domain = True
    fallback_used = False
    page = 0
    try:
        if len(normalized_domains) == 1:
            rows, pages, _ = _fetch_domain_rows(
                url=url,
                domains=normalized_domains,
                size=size,
                use_stocking_domain=True,
            )
            all_rows.extend(rows)
            page += pages
        else:
            for normalized_domain in normalized_domains:
                rows, pages, _ = _fetch_domain_rows(
                    url=url,
                    domains=[normalized_domain],
                    size=size,
                    use_stocking_domain=True,
                )
                all_rows.extend(rows)
                page += pages
    except ValueError as exc:
        if "stocking_domain unavailable" not in str(exc):
            raise
        use_stocking_domain = False
        fallback_used = True
        all_rows, page, _ = _fetch_domain_rows(
            url=url,
            domains=normalized_domains,
            size=size,
            use_stocking_domain=False,
        )
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


def update_item_stock(
    ebay_item_id: str,
    scraped_stock_status: str,
    *,
    is_scraped: bool = True,
    sku: Optional[str] = None,
) -> None:
    if not _enabled():
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY is not set")
    payload = {
        "scraped_stock_status": scraped_stock_status,
        "scraped_updated_at": datetime.now(timezone.utc).isoformat(),
        "is_scraped": is_scraped,
    }
    if sku is not None:
        payload["sku"] = sku
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


def update_item_stock_bulk(
    updates: list[dict[str, Any]],
    *,
    max_workers: Optional[int] = None,
) -> None:
    if not updates:
        return

    worker_count = max(1, max_workers or ITEM_UPDATE_MAX_WORKERS)
    failed_updates: list[tuple[dict[str, Any], str]] = []

    def _apply(update: dict[str, Any]) -> None:
        update_item_stock(
            ebay_item_id=str(update["ebay_item_id"]),
            scraped_stock_status=str(update["scraped_stock_status"]),
            is_scraped=bool(update.get("is_scraped", True)),
            sku=update.get("sku"),
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(_apply, update): update for update in updates}
        for future in as_completed(future_map):
            update = future_map[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                failed_updates.append((update, str(exc)))

    if not failed_updates:
        return

    json_log(
        "warning",
        "items bulk update retrying sequentially after parallel failures",
        failed_count=len(failed_updates),
        total_count=len(updates),
        worker_count=worker_count,
        preview=" | ".join(error for _, error in failed_updates[:3])[:500],
    )

    final_errors: list[str] = []
    for update, original_error in failed_updates:
        try:
            time.sleep(0.25)
            _apply(update)
        except Exception as exc:  # noqa: BLE001
            final_errors.append(f"{update.get('ebay_item_id')}: {exc}")
        else:
            json_log(
                "info",
                "items bulk update recovered in sequential retry",
                ebay_item_id=str(update.get("ebay_item_id", "")),
                original_error=original_error[:300],
            )

    if final_errors:
        preview = " | ".join(final_errors[:3])
        raise RuntimeError(f"bulk update failed: {preview}")
