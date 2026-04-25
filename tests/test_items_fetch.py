import unittest
from unittest.mock import Mock, patch

from scrapers.common import items


class FetchActiveItemsByDomainTests(unittest.TestCase):
    @patch("scrapers.common.items._enabled", return_value=True)
    @patch("scrapers.common.items.requests.get")
    def test_multiple_domains_use_separate_stocking_domain_queries(self, get_mock: Mock, _enabled_mock: Mock) -> None:
        def response(item_id) -> Mock:
            mock = Mock()
            mock.status_code = 200
            mock.json.return_value = [] if item_id is None else [{"ebay_item_id": item_id}]
            mock.raise_for_status.return_value = None
            return mock

        get_mock.side_effect = [
            response("1"),   # auctions yahoo active
            response(None),  # auctions yahoo listing_state_only
            response("2"),   # page auctions active
            response(None),  # page auctions listing_state_only
        ]

        rows = items.fetch_active_items_by_domain(["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"], page_size=50)

        self.assertEqual([row["ebay_item_id"] for row in rows], ["1", "2"])
        self.assertEqual(get_mock.call_args_list[0].kwargs["params"]["stocking_domain"], "eq.auctions.yahoo.co.jp")
        self.assertEqual(get_mock.call_args_list[0].kwargs["params"]["listing_status"], "eq.Active")
        self.assertEqual(get_mock.call_args_list[1].kwargs["params"]["stocking_domain"], "eq.auctions.yahoo.co.jp")
        self.assertEqual(get_mock.call_args_list[1].kwargs["params"]["listing_state"], "eq.ACTIVE")
        self.assertEqual(get_mock.call_args_list[2].kwargs["params"]["stocking_domain"], "eq.page.auctions.yahoo.co.jp")
        self.assertEqual(get_mock.call_args_list[2].kwargs["params"]["listing_status"], "eq.Active")
        self.assertEqual(get_mock.call_args_list[3].kwargs["params"]["stocking_domain"], "eq.page.auctions.yahoo.co.jp")
        self.assertEqual(get_mock.call_args_list[3].kwargs["params"]["listing_state"], "eq.ACTIVE")

    @patch("scrapers.common.items._enabled", return_value=True)
    @patch("scrapers.common.items.requests.get")
    def test_falls_back_to_ilike_when_stocking_domain_is_unavailable(self, get_mock: Mock, _enabled_mock: Mock) -> None:
        missing_column = Mock()
        missing_column.status_code = 400
        missing_column.text = "column stocking_domain does not exist"

        fallback = Mock()
        fallback.status_code = 200
        fallback.json.return_value = []
        fallback.raise_for_status.return_value = None

        get_mock.side_effect = [missing_column, fallback]

        rows = items.fetch_active_items_by_domain(["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"], page_size=50)

        self.assertEqual(rows, [])
        self.assertIn("stocking_url.ilike.any", get_mock.call_args_list[1].kwargs["params"]["and"])

    def test_is_fetch_timeout_error_matches_statement_timeout_variants(self) -> None:
        self.assertTrue(items._is_fetch_timeout_error(RuntimeError("Supabase 500 on page 97: statement timeout")))
        self.assertTrue(items._is_fetch_timeout_error(RuntimeError("canceling statement due to statement timeout")))
        self.assertFalse(items._is_fetch_timeout_error(RuntimeError("unauthorized")))


if __name__ == "__main__":
    unittest.main()
