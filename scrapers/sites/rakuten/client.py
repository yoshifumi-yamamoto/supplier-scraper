import os
import re
import time
from typing import Any, Optional

import requests


RAKUTEN_APPLICATION_ID = os.getenv("RAKUTEN_APPLICATION_ID", "").strip()
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY", "").strip()
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID", "").strip()
RAKUTEN_BASE_URL = os.getenv(
    "RAKUTEN_BASE_URL",
    "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401",
).strip()
RAKUTEN_REQUEST_INTERVAL_SECONDS = float(os.getenv("RAKUTEN_REQUEST_INTERVAL_SECONDS", "1.1"))
RAKUTEN_MAX_RETRIES = int(os.getenv("RAKUTEN_MAX_RETRIES", "3"))
_LAST_REQUEST_AT = 0.0


class RakutenApiError(RuntimeError):
    pass


class RakutenPageNotFoundError(RuntimeError):
    pass


def _html_title(html: str) -> str | None:
    patterns = [
        r'property="og:title"\s+content="([^"]+)"',
        r"<title>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip()
            if title:
                return title
    return None


def _html_models(html: str) -> list[str]:
    patterns = [
        r'itemprop="sku"\s+content="([^"]+)"',
        r"商品コード[:：\s]*([A-Za-z0-9\-_]+)",
        r"型番[:：\s]*([A-Za-z0-9\-_]+)",
        r"JAN[:：\s]*([0-9]{8,14})",
    ]
    models: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, html, re.IGNORECASE):
            value = re.sub(r"\s+", "", match).strip()
            if len(value) < 4:
                continue
            if value not in models:
                models.append(value)
    return models


def _html_sku(html: str) -> str | None:
    match = re.search(r'itemprop="sku"\s+content="([^"]+)"', html, re.IGNORECASE)
    if not match:
        return None
    value = re.sub(r"\s+", "", match.group(1)).strip()
    return value or None


def auth_ready() -> bool:
    return bool(RAKUTEN_APPLICATION_ID and RAKUTEN_ACCESS_KEY and RAKUTEN_BASE_URL)


def _base_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "applicationId": RAKUTEN_APPLICATION_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        "format": "json",
    }
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID
    return params


def _unwrap_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("Items") or body.get("items") or []
    unwrapped: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and "item" in item and isinstance(item["item"], dict):
            unwrapped.append(item["item"])
        elif isinstance(item, dict) and "Item" in item and isinstance(item["Item"], dict):
            unwrapped.append(item["Item"])
        elif isinstance(item, dict):
            unwrapped.append(item)
    return unwrapped


def _request(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_REQUEST_AT
    last_error: Optional[str] = None
    for attempt in range(RAKUTEN_MAX_RETRIES):
        elapsed = time.monotonic() - _LAST_REQUEST_AT
        if elapsed < RAKUTEN_REQUEST_INTERVAL_SECONDS:
            time.sleep(RAKUTEN_REQUEST_INTERVAL_SECONDS - elapsed)
        response = requests.get(RAKUTEN_BASE_URL, params=params, timeout=20)
        _LAST_REQUEST_AT = time.monotonic()
        preview = response.text[:300].replace("\n", " ")
        if response.status_code == 429:
            last_error = f"rakuten api error 429: {preview}"
            time.sleep(max(RAKUTEN_REQUEST_INTERVAL_SECONDS, 1.0) * (attempt + 1))
            continue
        if response.status_code >= 400:
            raise RakutenApiError(f"rakuten api error {response.status_code}: {preview}")
        return response.json()
    raise RakutenApiError(last_error or "rakuten api error 429")


def fetch_page_hints(stocking_url: str) -> dict[str, Any]:
    response = requests.get(
        stocking_url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    if response.status_code == 404:
        raise RakutenPageNotFoundError(f"rakuten page not found: {stocking_url}")
    response.raise_for_status()
    html = response.text
    return {
        "page_title": _html_title(html),
        "page_models": _html_models(html),
        "page_sku": _html_sku(html),
    }


def fetch_item_by_code(item_code: str, *, shop_code: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not auth_ready():
        raise RakutenApiError("rakuten auth not configured")

    params = _base_params()
    params.update(
        {
        "itemCode": item_code,
        }
    )
    if shop_code:
        params["shopCode"] = shop_code
    body = _request(params)
    items = _unwrap_items(body)
    if not items:
        return None
    return items[0]


def search_items(*, keyword: str, shop_code: Optional[str] = None, hits: int = 10) -> list[dict[str, Any]]:
    if not auth_ready():
        raise RakutenApiError("rakuten auth not configured")
    params = _base_params()
    params.update(
        {
            "keyword": keyword,
            "hits": hits,
        }
    )
    if shop_code:
        params["shopCode"] = shop_code
    body = _request(params)
    return _unwrap_items(body)
