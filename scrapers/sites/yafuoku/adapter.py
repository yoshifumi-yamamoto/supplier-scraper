from scrapers.common.selenium_stock_pipeline import run_sequential_stock_pipeline
from scrapers.sites.yafuoku.checker import check_stock_status


def run_pipeline(run_id: str) -> dict:
    return run_sequential_stock_pipeline(
        run_id=run_id,
        site="yafuoku",
        domains=["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"],
        checker=check_stock_status,
        fetch_page_size=25,
        rebuild_every_env="YAFUOKU_REBUILD_EVERY",
        rebuild_every_default=80,
        batch_size_env="YAFUOKU_UPDATE_BATCH_SIZE",
        batch_size_default=50,
    )
