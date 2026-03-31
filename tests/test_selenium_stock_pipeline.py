import unittest
import sys
import types


browser = types.ModuleType("scrapers.common.browser")
browser.build_chrome = lambda headless=True: object()
sys.modules.setdefault("scrapers.common.browser", browser)

items = types.ModuleType("scrapers.common.items")
items.fetch_active_items_by_domain = lambda *args, **kwargs: []
items.update_item_stock_bulk = lambda rows: None
sys.modules.setdefault("scrapers.common.items", items)

logging_utils = types.ModuleType("scrapers.common.logging_utils")
logging_utils.json_log = lambda *args, **kwargs: None
sys.modules.setdefault("scrapers.common.logging_utils", logging_utils)

models = types.ModuleType("scrapers.common.models")

class _ScrapeStatus:
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNKNOWN = "UNKNOWN"

models.ScrapeStatus = _ScrapeStatus
sys.modules.setdefault("scrapers.common.models", models)

run_store = types.ModuleType("scrapers.common.run_store")
run_store.start_step = lambda *args, **kwargs: None
run_store.finish_step = lambda *args, **kwargs: None
sys.modules.setdefault("scrapers.common.run_store", run_store)

from scrapers.common.selenium_stock_pipeline import _select_shard_items


class SeleniumStockPipelineShardTests(unittest.TestCase):
    def test_select_shard_items_keeps_every_nth_item(self):
        items = [{"ebay_item_id": str(i)} for i in range(10)]

        shard0 = _select_shard_items(items, 0, 2)
        shard1 = _select_shard_items(items, 1, 2)

        self.assertEqual([row["ebay_item_id"] for row in shard0], ["0", "2", "4", "6", "8"])
        self.assertEqual([row["ebay_item_id"] for row in shard1], ["1", "3", "5", "7", "9"])

    def test_select_shard_items_without_sharding_returns_all(self):
        items = [{"ebay_item_id": str(i)} for i in range(3)]
        self.assertEqual(_select_shard_items(items, 0, 1), items)


if __name__ == "__main__":
    unittest.main()
