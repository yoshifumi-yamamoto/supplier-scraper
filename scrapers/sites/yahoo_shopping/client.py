import os
from typing import Any


YAHOO_SHOPPING_CLIENT_ID = os.getenv("YAHOO_SHOPPING_CLIENT_ID", "").strip()
YAHOO_SHOPPING_CLIENT_SECRET = os.getenv("YAHOO_SHOPPING_CLIENT_SECRET", "").strip()
YAHOO_SHOPPING_BASE_URL = os.getenv(
    "YAHOO_SHOPPING_BASE_URL",
    "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch",
).strip()


class YahooShoppingApiError(RuntimeError):
    pass


def auth_ready() -> bool:
    return bool(YAHOO_SHOPPING_CLIENT_ID and YAHOO_SHOPPING_CLIENT_SECRET and YAHOO_SHOPPING_BASE_URL)


def fetch_offer_by_item(*, seller_id: str, item_code: str) -> dict[str, Any] | None:
    if not auth_ready():
        raise YahooShoppingApiError("yahoo shopping auth not configured")

    # Placeholder until Yahoo Shopping auth/contract is fixed.
    # We keep the adapter/runner path alive so onboarding can proceed
    # without blocking on the rest of Phase 4 work.
    raise YahooShoppingApiError(
        f"yahoo shopping api client not implemented yet for seller={seller_id} item={item_code}"
    )
