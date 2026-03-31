import sys
import types
import unittest
from unittest.mock import patch


browser_stub = types.ModuleType("scrapers.common.browser")
browser_stub.build_chrome = lambda headless=True: None
sys.modules.setdefault("scrapers.common.browser", browser_stub)

run_store_stub = types.ModuleType("scrapers.common.run_store")
run_store_stub.start_step = lambda *args, **kwargs: None
run_store_stub.finish_step = lambda *args, **kwargs: None
sys.modules.setdefault("scrapers.common.run_store", run_store_stub)

models_stub = types.ModuleType("scrapers.common.models")


class _ScrapeStatus:
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


models_stub.ScrapeStatus = _ScrapeStatus
sys.modules.setdefault("scrapers.common.models", models_stub)

checker_stub = types.ModuleType("scrapers.sites.yafuoku.checker")
checker_stub.check_stock_status = lambda driver, url: (_ScrapeStatus.UNKNOWN, "stub")
sys.modules.setdefault("scrapers.sites.yafuoku.checker", checker_stub)

fleama_checker_stub = types.ModuleType("scrapers.sites.yahoofleama.checker")
fleama_checker_stub.check_stock_status = lambda driver, url: (_ScrapeStatus.UNKNOWN, "stub")
sys.modules.setdefault("scrapers.sites.yahoofleama.checker", fleama_checker_stub)

from scrapers.sites.yafuoku import adapter as yafuoku_adapter
from scrapers.sites.yahoofleama import adapter as yahoofleama_adapter


class YahooStockPipelineTests(unittest.TestCase):
    @patch("scrapers.sites.yafuoku.adapter.run_sequential_stock_pipeline", return_value={"status": "success"})
    def test_yafuoku_uses_shared_pipeline(self, pipeline_mock) -> None:
        result = yafuoku_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        kwargs = pipeline_mock.call_args.kwargs
        self.assertEqual(kwargs["site"], "yafuoku")
        self.assertEqual(kwargs["domains"], ["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"])
        self.assertEqual(kwargs["fetch_page_size"], 25)
        self.assertEqual(kwargs["rebuild_every_default"], 80)
        self.assertEqual(kwargs["batch_size_default"], 50)

    @patch("scrapers.sites.yahoofleama.adapter.run_sequential_stock_pipeline", return_value={"status": "success"})
    def test_yahoofleama_uses_shared_pipeline(self, pipeline_mock) -> None:
        result = yahoofleama_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        kwargs = pipeline_mock.call_args.kwargs
        self.assertEqual(kwargs["site"], "yahoofleama")
        self.assertEqual(kwargs["domains"], "paypayfleamarket.yahoo.co.jp")
        self.assertEqual(kwargs["fetch_page_size"], 50)
        self.assertEqual(kwargs["rebuild_every_default"], 120)
        self.assertEqual(kwargs["batch_size_default"], 50)


if __name__ == "__main__":
    unittest.main()
