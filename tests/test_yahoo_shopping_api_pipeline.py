import unittest

from scrapers.common.models import ScrapeStatus
from scrapers.sites.yahoo_shopping import adapter as yahoo_adapter
from scrapers.sites.yahoo_shopping.normalizer import normalize_offer


class YahooShoppingApiPipelineTests(unittest.TestCase):
    def test_parse_item_ref_from_store_url(self) -> None:
        parsed = yahoo_adapter._parse_item_ref("https://store.shopping.yahoo.co.jp/testshop/abc123.html")
        self.assertEqual(parsed, ("testshop", "abc123"))

    def test_parse_item_ref_from_market_url(self) -> None:
        parsed = yahoo_adapter._parse_item_ref("https://shopping.yahoo.co.jp/testshop/abc123.html")
        self.assertEqual(parsed, ("testshop", "abc123"))

    def test_normalize_offer_maps_in_stock(self) -> None:
        self.assertEqual(normalize_offer({"inStock": True})[0], ScrapeStatus.IN_STOCK)

    def test_normalize_offer_maps_out_of_stock(self) -> None:
        self.assertEqual(normalize_offer({"inStock": False})[0], ScrapeStatus.OUT_OF_STOCK)


if __name__ == "__main__":
    unittest.main()
