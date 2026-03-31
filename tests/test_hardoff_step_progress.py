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

logging_stub = types.ModuleType("scrapers.common.logging_utils")
logging_stub.json_log = lambda *args, **kwargs: None
sys.modules.setdefault("scrapers.common.logging_utils", logging_stub)

models_stub = types.ModuleType("scrapers.common.models")


class _ScrapeStatus:
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"
    ERROR = types.SimpleNamespace(value="error")


models_stub.ScrapeStatus = _ScrapeStatus
sys.modules.setdefault("scrapers.common.models", models_stub)

checker_stub = types.ModuleType("scrapers.sites.hardoff.checker")
checker_stub.check_stock_status = lambda driver, url: (_ScrapeStatus.UNKNOWN, "stub")
sys.modules.setdefault("scrapers.sites.hardoff.checker", checker_stub)

from scrapers.sites.hardoff import adapter as hardoff_adapter


class DummyDriver:
    def quit(self) -> None:
        return None


class HardoffStepProgressTests(unittest.TestCase):
    @patch("scrapers.sites.hardoff.adapter.update_item_stock")
    @patch("scrapers.sites.hardoff.adapter.check_stock_status")
    @patch("scrapers.sites.hardoff.adapter.fetch_active_items_by_domain")
    @patch("scrapers.sites.hardoff.adapter.finish_step")
    @patch("scrapers.sites.hardoff.adapter.start_step")
    @patch("scrapers.sites.hardoff.adapter.build_chrome", return_value=DummyDriver())
    def test_hardoff_uses_fetch_and_per_item_check_steps(
        self,
        _build_chrome,
        start_step_mock,
        finish_step_mock,
        fetch_mock,
        check_mock,
        update_mock,
    ) -> None:
        fetch_mock.return_value = [
            {"ebay_item_id": "item-1", "stocking_url": "https://netmall.hardoff.co.jp/item-1"},
            {"ebay_item_id": "item-2", "stocking_url": "https://netmall.hardoff.co.jp/item-2"},
        ]
        check_mock.side_effect = [
            (_ScrapeStatus.IN_STOCK, "在庫あり"),
            (_ScrapeStatus.OUT_OF_STOCK, "在庫なし"),
        ]
        start_step_mock.side_effect = ["fetch-step", "check-step-1", "check-step-2"]

        result = hardoff_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        self.assertEqual(start_step_mock.call_args_list[0].kwargs, {"run_id": "run-1", "step_name": "fetch_items"})
        self.assertEqual(start_step_mock.call_args_list[1].kwargs, {"run_id": "run-1", "step_name": "check:item-1"})
        self.assertEqual(start_step_mock.call_args_list[2].kwargs, {"run_id": "run-1", "step_name": "check:item-2"})
        finish_step_mock.assert_any_call("fetch-step", status="success", message="fetched 2 items")
        finish_step_mock.assert_any_call("check-step-1", status="success", message="在庫あり")
        finish_step_mock.assert_any_call("check-step-2", status="success", message="在庫なし")
        self.assertEqual(update_mock.call_count, 2)

    @patch("scrapers.sites.hardoff.adapter.fetch_active_items_by_domain", return_value=[])
    @patch("scrapers.sites.hardoff.adapter.finish_step")
    @patch("scrapers.sites.hardoff.adapter.start_step", return_value="fetch-step")
    def test_hardoff_empty_fetch_uses_canonical_message(self, _start_mock, finish_step_mock, _fetch_mock) -> None:
        result = hardoff_adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        finish_step_mock.assert_called_once_with("fetch-step", status="success", message="hardoff no target items")


if __name__ == "__main__":
    unittest.main()
