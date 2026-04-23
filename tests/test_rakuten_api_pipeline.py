import unittest
from unittest.mock import patch

from scrapers.common.models import ScrapeStatus
from scrapers.sites.rakuten import adapter as rakuten_adapter
from scrapers.sites.rakuten.normalizer import normalize_item


class RakutenApiPipelineTests(unittest.TestCase):
    def test_parse_item_code_from_item_url(self) -> None:
        parsed = rakuten_adapter._parse_item_code_from_url("https://item.rakuten.co.jp/testshop/abc123/")
        self.assertEqual(parsed, ("testshop", "abc123"))

    def test_parse_item_code_from_www_url(self) -> None:
        parsed = rakuten_adapter._parse_item_code_from_url("https://www.rakuten.co.jp/testshop/abc123/")
        self.assertEqual(parsed, ("testshop", "abc123"))

    def test_normalize_item_maps_availability(self) -> None:
        self.assertEqual(normalize_item({"availability": 1})[0], ScrapeStatus.IN_STOCK)
        self.assertEqual(normalize_item({"availability": 0})[0], ScrapeStatus.OUT_OF_STOCK)
        self.assertEqual(normalize_item({"availability": None})[0], ScrapeStatus.UNKNOWN)

    @patch("scrapers.sites.rakuten.adapter.update_item_stock_bulk")
    @patch("scrapers.sites.rakuten.adapter.fetch_item_by_code", return_value={"availability": 0})
    @patch("scrapers.sites.rakuten.adapter.fetch_active_items_by_domain")
    @patch("scrapers.sites.rakuten.adapter.auth_ready", return_value=True)
    def test_run_pipeline_uses_api_flow(self, _auth_ready, fetch_items_mock, fetch_item_mock, bulk_update_mock) -> None:
        fetch_items_mock.return_value = [
            {
                "ebay_item_id": "147",
                "stocking_url": "https://item.rakuten.co.jp/testshop/abc123/",
            }
        ]

        result = rakuten_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        fetch_items_mock.assert_called_once_with(rakuten_adapter.RAKUTEN_DOMAINS, page_size=50)
        fetch_item_mock.assert_called_once_with("abc123", shop_code="testshop")
        updates = bulk_update_mock.call_args.args[0]
        self.assertEqual(updates[0]["scraped_stock_status"], "在庫なし")


if __name__ == "__main__":
    unittest.main()
