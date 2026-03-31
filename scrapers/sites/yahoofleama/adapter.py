from scrapers.common.selenium_stock_pipeline import run_sequential_stock_pipeline
from scrapers.sites.yahoofleama.checker import check_stock_status


def run_pipeline(run_id: str) -> dict:
    return run_sequential_stock_pipeline(
        run_id=run_id,
        site="yahoofleama",
        domains="paypayfleamarket.yahoo.co.jp",
        checker=check_stock_status,
        fetch_page_size=50,
        rebuild_every_env="YAHOOFLEAMA_REBUILD_EVERY",
        rebuild_every_default=120,
        batch_size_env="YAHOOFLEAMA_UPDATE_BATCH_SIZE",
        batch_size_default=50,
    )
