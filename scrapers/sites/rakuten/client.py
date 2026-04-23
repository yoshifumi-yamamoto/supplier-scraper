import os
from typing import Any

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


def fetch_item_by_code(item_code: str, *, shop_code: str | None = None) -> dict[str, Any] | None:
    if not auth_ready():
        raise RakutenApiError("rakuten auth not configured")

    params = {
        "applicationId": RAKUTEN_APPLICATION_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        "itemCode": item_code,
        "format": "json",
    }
    if shop_code:
        params["shopCode"] = shop_code
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    response = requests.get(RAKUTEN_BASE_URL, params=params, timeout=20)
    if response.status_code >= 500:
        preview = response.text[:300].replace("\n", " ")
        raise RakutenApiError(f"rakuten api server error {response.status_code}: {preview}")
    response.raise_for_status()
    body = response.json()
    items = body.get("Items") or body.get("items") or []
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict) and "item" in first and isinstance(first["item"], dict):
        return first["item"]
    if isinstance(first, dict):
        return first
    raise RakutenApiError("rakuten api returned unsupported payload")
