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

    def test_parse_saved_item_code(self) -> None:
        self.assertEqual(
            rakuten_adapter._parse_saved_item_code("rakuten:testshop:abc123"),
            ("confirmed", "testshop:abc123"),
        )
        self.assertEqual(
            rakuten_adapter._parse_saved_item_code("rakuten-pending:testshop:def456"),
            ("pending", "testshop:def456"),
        )

    def test_normalize_item_maps_availability(self) -> None:
        self.assertEqual(normalize_item({"availability": 1})[0], ScrapeStatus.IN_STOCK)
        self.assertEqual(normalize_item({"availability": 0})[0], ScrapeStatus.OUT_OF_STOCK)
        self.assertEqual(normalize_item({"availability": None})[0], ScrapeStatus.UNKNOWN)

    def test_build_search_keywords_prefers_title_and_skips_numeric_only_code(self) -> None:
        keywords = rakuten_adapter._build_search_keywords(
            title="テーラーメイド M2 ドライバー 10.5",
            local_code_hint="2100412572169",
            page_models=["TM1-217"],
        )

        self.assertIn("テーラーメイド M2 ドライバー 10 5", keywords)
        self.assertIn("TM1-217", keywords)
        self.assertNotIn("2100412572169", keywords)

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
        fetch_items_mock.assert_called_once_with(
            rakuten_adapter.RAKUTEN_DOMAINS,
            page_size=rakuten_adapter.FETCH_PAGE_SIZE,
            max_items=rakuten_adapter.FETCH_MAX_ITEMS or None,
        )
        fetch_item_mock.assert_called_once_with("abc123", shop_code="testshop")
        updates = bulk_update_mock.call_args.args[0]
        self.assertEqual(updates[0]["scraped_stock_status"], "在庫なし")

    @patch("scrapers.sites.rakuten.adapter.update_item_stock_bulk")
    @patch(
        "scrapers.sites.rakuten.adapter.search_items",
        return_value=[
            {
                "itemCode": "testshop:abc123",
                "shopCode": "testshop",
                "itemName": "Test Product ABC123",
                "availability": 0,
                "itemPrice": 1000,
            }
        ],
    )
    @patch("scrapers.sites.rakuten.adapter.fetch_active_items_by_domain")
    @patch("scrapers.sites.rakuten.adapter.auth_ready", return_value=True)
    def test_run_pipeline_confirms_discovery_candidate(self, _auth_ready, fetch_items_mock, _search_mock, bulk_update_mock) -> None:
        fetch_items_mock.return_value = [
            {
                "ebay_item_id": "148",
                "stocking_url": "https://item.rakuten.co.jp/testshop/abc123/",
                "title": "Test Product ABC123",
                "price": 1000,
                "image_url": None,
                "sku": None,
            }
        ]

        result = rakuten_adapter.run_pipeline("run-2")

        self.assertEqual(result["status"], "success")
        updates = bulk_update_mock.call_args.args[0]
        self.assertEqual(updates[0]["scraped_stock_status"], "在庫なし")
        self.assertEqual(updates[0]["sku"], "rakuten:testshop:abc123")


if __name__ == "__main__":
    unittest.main()
