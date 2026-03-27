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
    ERROR = types.SimpleNamespace(value="error")


models_stub.ScrapeStatus = _ScrapeStatus
sys.modules.setdefault("scrapers.common.models", models_stub)


def _install_checker_stub(module_name: str) -> None:
    checker_stub = types.ModuleType(module_name)
    checker_stub.check_stock_status = lambda driver, url: (_ScrapeStatus.UNKNOWN, "stub")
    sys.modules.setdefault(module_name, checker_stub)


_install_checker_stub("scrapers.sites.secondstreet.checker")
_install_checker_stub("scrapers.sites.surugaya.checker")
_install_checker_stub("scrapers.sites.yodobashi.checker")
_install_checker_stub("scrapers.sites.rakuma.checker")
_install_checker_stub("scrapers.sites.yafuoku.checker")

from scrapers.sites.secondstreet import adapter as secondstreet_adapter
from scrapers.sites.surugaya import adapter as surugaya_adapter
from scrapers.sites.yodobashi import adapter as yodobashi_adapter
from scrapers.sites.rakuma import adapter as rakuma_adapter
from scrapers.sites.yafuoku import adapter as yafuoku_adapter


class SiteAliasDomainTests(unittest.TestCase):
    @patch("scrapers.sites.secondstreet.adapter.finish_step")
    @patch("scrapers.sites.secondstreet.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.secondstreet.adapter.fetch_active_items_by_domain", return_value=[])
    def test_secondstreet_fetches_alias_domains(self, fetch_mock, _start_mock, _finish_mock) -> None:
        result = secondstreet_adapter.run_pipeline("run-1")
        fetch_mock.assert_called_once_with(["2ndstreet.jp", "www.2ndstreet.jp"])
        self.assertEqual(result["status"], "success")

    @patch("scrapers.sites.surugaya.adapter.finish_step")
    @patch("scrapers.sites.surugaya.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.surugaya.adapter.fetch_active_items_by_domain", return_value=[])
    def test_surugaya_fetches_alias_domains(self, fetch_mock, _start_mock, _finish_mock) -> None:
        result = surugaya_adapter.run_pipeline("run-1")
        fetch_mock.assert_called_once_with(["suruga-ya.jp", "www.suruga-ya.jp"], page_size=25)
        self.assertEqual(result["status"], "success")

    @patch("scrapers.sites.yodobashi.adapter.finish_step")
    @patch("scrapers.sites.yodobashi.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.yodobashi.adapter.fetch_active_items_by_domain", return_value=[])
    def test_yodobashi_fetches_alias_domains(self, fetch_mock, _start_mock, _finish_mock) -> None:
        result = yodobashi_adapter.run_pipeline("run-1")
        fetch_mock.assert_called_once_with(["yodobashi.com", "www.yodobashi.com"])
        self.assertEqual(result["status"], "success")

    @patch("scrapers.sites.rakuma.adapter.finish_step")
    @patch("scrapers.sites.rakuma.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.rakuma.adapter.fetch_active_items_by_domain", return_value=[])
    def test_rakuma_fetches_alias_domains(self, fetch_mock, _start_mock, _finish_mock) -> None:
        result = rakuma_adapter.run_pipeline("run-1")
        fetch_mock.assert_called_once_with(["fril.jp", "item.fril.jp"])
        self.assertEqual(result["status"], "success")

    @patch("scrapers.sites.yafuoku.adapter.finish_step")
    @patch("scrapers.sites.yafuoku.adapter.start_step", return_value="step-1")
    @patch("scrapers.sites.yafuoku.adapter.fetch_active_items_by_domain", return_value=[])
    def test_yafuoku_fetches_alias_domains(self, fetch_mock, _start_mock, _finish_mock) -> None:
        result = yafuoku_adapter.run_pipeline("run-1")
        fetch_mock.assert_called_once_with(["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"])
        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
