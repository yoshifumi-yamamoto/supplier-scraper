from typing import Any

from scrapers.common.models import ScrapeStatus


def normalize_item(raw: dict[str, Any] | None) -> tuple[ScrapeStatus, str]:
    if not raw:
        return ScrapeStatus.UNKNOWN, "rakuten api returned no item"

    availability = raw.get("availability")
    try:
        availability_value = int(availability)
    except (TypeError, ValueError):
        availability_value = None

    if availability_value == 1:
        return ScrapeStatus.IN_STOCK, "rakuten availability=1"
    if availability_value == 0:
        return ScrapeStatus.OUT_OF_STOCK, "rakuten availability=0"
    return ScrapeStatus.UNKNOWN, f"rakuten availability unknown: {availability}"
