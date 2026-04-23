import os
from typing import Any, Optional

import requests


RAKUTEN_APPLICATION_ID = os.getenv("RAKUTEN_APPLICATION_ID", "").strip()
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY", "").strip()
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID", "").strip()
RAKUTEN_BASE_URL = os.getenv(
    "RAKUTEN_BASE_URL",
    "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401",
).strip()


class RakutenApiError(RuntimeError):
    pass


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
        elif isinstance(item, dict):
            unwrapped.append(item)
    return unwrapped


def _request(params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(RAKUTEN_BASE_URL, params=params, timeout=20)
    preview = response.text[:300].replace("\n", " ")
    if response.status_code >= 400:
        raise RakutenApiError(f"rakuten api error {response.status_code}: {preview}")
    return response.json()


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
