from typing import Any

from scrapers.common.models import ScrapeStatus


def normalize_offer(raw: dict[str, Any] | None) -> tuple[ScrapeStatus, str]:
    if not raw:
        return ScrapeStatus.UNKNOWN, "yahoo shopping api returned no item"

    in_stock = raw.get("inStock")
    if in_stock is True:
        return ScrapeStatus.IN_STOCK, "yahoo shopping inStock=true"
    if in_stock is False:
        return ScrapeStatus.OUT_OF_STOCK, "yahoo shopping inStock=false"

    availability = raw.get("availability")
    if availability in ("in_stock", "available", 1, "1"):
        return ScrapeStatus.IN_STOCK, f"yahoo shopping availability={availability}"
    if availability in ("out_of_stock", "sold_out", 0, "0"):
        return ScrapeStatus.OUT_OF_STOCK, f"yahoo shopping availability={availability}"

    return ScrapeStatus.UNKNOWN, f"yahoo shopping availability unknown: {availability}"
