import unittest
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
        self.assertEqual(params["listing_status"], "eq.Active")

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
        result = mercari_adapter.run_pipeline("run-1")

        fetch_mock.assert_called_once_with(["mercari.com", "jp.mercari.com"], page_size=50)
        self.assertEqual(result["status"], "success")
        self.assertIn("0 items", result["message"])
        start_step_mock.assert_called_once_with("run-1", "fetch_items")
        finish_step_mock.assert_called_once_with("step-1", "success", "mercari no target items")


if __name__ == "__main__":
    unittest.main()
