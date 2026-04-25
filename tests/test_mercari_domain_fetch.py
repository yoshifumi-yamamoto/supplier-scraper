import unittest
import os
import sys
import types
from unittest.mock import patch

from scrapers.common import items


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

checker_stub = types.ModuleType("scrapers.sites.mercari.checker")
checker_stub.check_stock_status = lambda driver, url: (_ScrapeStatus.UNKNOWN, "stub")
sys.modules.setdefault("scrapers.sites.mercari.checker", checker_stub)

from scrapers.sites.mercari import adapter as mercari_adapter


class FetchParamsTests(unittest.TestCase):
    def test_build_fetch_params_uses_in_for_multiple_stocking_domains(self) -> None:
        params = items._build_fetch_params(
            ["mercari.com", "jp.mercari.com"],
            size=50,
            last_item_id=None,
            use_stocking_domain=True,
        )

        self.assertEqual(params["stocking_domain"], "in.(mercari.com,jp.mercari.com)")
        self.assertEqual(params["or"], "(listing_status.eq.Active,listing_state.eq.ACTIVE)")

    def test_build_fetch_params_uses_ilike_any_fallback_for_multiple_domains(self) -> None:
        params = items._build_fetch_params(
            ["mercari.com", "jp.mercari.com"],
            size=50,
            last_item_id=None,
            use_stocking_domain=False,
        )

        self.assertEqual(
            params["and"],
            "(stocking_url.not.is.null,stocking_url.ilike.any.{*mercari.com*,*jp.mercari.com*})",
        )


class MercariAdapterTests(unittest.TestCase):
    @patch("scrapers.sites.mercari.adapter.finish_step")
    @patch("scrapers.sites.mercari.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.mercari.adapter.fetch_active_items_by_domain", return_value=[])
    def test_mercari_pipeline_fetches_both_domains(self, fetch_mock, start_step_mock, finish_step_mock) -> None:
        with patch.dict(os.environ, {"MERCARI_BROWSER_WORKERS": "1"}, clear=False):
            result = mercari_adapter.run_pipeline("run-1")

        fetch_mock.assert_called_once_with(["mercari.com", "jp.mercari.com"], page_size=50)
        self.assertEqual(result["status"], "success")
        self.assertIn("0 items", result["message"])
        start_step_mock.assert_called_once_with("run-1", "fetch_items")
        finish_step_mock.assert_called_once_with("step-1", "success", "mercari no target items")

    @patch("scrapers.sites.mercari.adapter.update_item_stock_bulk")
    @patch("scrapers.sites.mercari.adapter.finish_step")
    @patch("scrapers.sites.mercari.adapter.start_step")
    @patch("scrapers.sites.mercari.adapter.check_stock_status")
    @patch("scrapers.sites.mercari.adapter.build_chrome")
    @patch("scrapers.sites.mercari.adapter.fetch_active_items_by_domain")
    def test_mercari_batches_item_updates(
        self,
        fetch_mock,
        build_chrome_mock,
        check_mock,
        start_step_mock,
        finish_step_mock,
        update_bulk_mock,
    ) -> None:
        class DummyDriver:
            def quit(self) -> None:
                return None

        build_chrome_mock.return_value = DummyDriver()
        fetch_mock.return_value = [
            {"ebay_item_id": "item-1", "stocking_url": "https://jp.mercari.com/item-1"},
            {"ebay_item_id": "item-2", "stocking_url": "https://jp.mercari.com/item-2"},
        ]
        check_mock.side_effect = [
            (_ScrapeStatus.IN_STOCK, "purchase_button"),
            (_ScrapeStatus.OUT_OF_STOCK, "sold_out_button"),
        ]
        start_step_mock.side_effect = ["fetch-step", "check-step-1", "check-step-2"]

        with patch.dict(os.environ, {"MERCARI_BROWSER_WORKERS": "1", "MERCARI_UPDATE_BATCH_SIZE": "2"}, clear=False):
            result = mercari_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        update_bulk_mock.assert_called_once()
        sent_updates = update_bulk_mock.call_args.args[0]
        self.assertEqual(len(sent_updates), 2)
        self.assertEqual(sent_updates[0]["ebay_item_id"], "item-1")
        self.assertEqual(sent_updates[1]["ebay_item_id"], "item-2")

    def test_split_items_balances_rows(self) -> None:
        rows = [{"ebay_item_id": f"item-{idx}"} for idx in range(7)]

        chunks = mercari_adapter._split_items(rows, 3)

        self.assertEqual(len(chunks), 3)
        self.assertEqual([len(chunk) for chunk in chunks], [3, 2, 2])

    def test_select_shard_items_picks_subset(self) -> None:
        rows = [{"ebay_item_id": f"item-{idx}"} for idx in range(6)]

        shard_rows = mercari_adapter._select_shard_items(rows, 1, 3)

        self.assertEqual([row["ebay_item_id"] for row in shard_rows], ["item-1", "item-4"])


if __name__ == "__main__":
    unittest.main()
