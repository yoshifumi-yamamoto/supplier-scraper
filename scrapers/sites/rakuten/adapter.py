from scrapers.common.models import ScrapeStatus


def run_pipeline(run_id: str) -> dict:
    # Rakuten is monitored via official API, not HTML scraping.
    return {
        "run_id": run_id,
        "site": "rakuten",
        "status": ScrapeStatus.UNKNOWN.value,
        "message": "rakuten uses API monitoring pipeline (not scraper)",
    }
