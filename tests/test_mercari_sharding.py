import os
import sys
import types
import unittest
from unittest.mock import patch

browser = types.ModuleType("scrapers.common.browser")
browser.build_chrome = lambda headless=True: object()
sys.modules.setdefault("scrapers.common.browser", browser)

run_store = types.ModuleType("scrapers.common.run_store")
run_store.start_step = lambda *args, **kwargs: None
run_store.finish_step = lambda *args, **kwargs: None
sys.modules.setdefault("scrapers.common.run_store", run_store)

checker = types.ModuleType("scrapers.sites.mercari.checker")
checker.check_stock_status = lambda driver, url: ("UNKNOWN", "stub")
sys.modules.setdefault("scrapers.sites.mercari.checker", checker)

from scrapers.sites.mercari import adapter


class MercariShardingTests(unittest.TestCase):
    @patch.object(adapter, "start_step", return_value="step-1")
    @patch.object(adapter, "finish_step")
    @patch.object(adapter, "fetch_active_items_by_domain")
    def test_run_pipeline_uses_runtime_shard_env(self, fetch_items, finish_step, start_step):
        fetch_items.return_value = [{"ebay_item_id": str(i), "stocking_url": f"https://mercari.com/item/{i}"} for i in range(6)]
        env = {"SCRAPER_SHARD_INDEX": "1", "SCRAPER_SHARD_TOTAL": "3", "MERCARI_BROWSER_WORKERS": "1"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(adapter, "_process_chunk", return_value=2) as process_chunk:
                result = adapter.run_pipeline("run-1")

        self.assertEqual(result["status"], "success")
        finish_step.assert_any_call("step-1", "success", "fetched 2 items")
        process_chunk.assert_called_once()
        processed_rows = process_chunk.call_args.args[1]
        self.assertEqual([row["ebay_item_id"] for row in processed_rows], ["1", "4"])


if __name__ == "__main__":
    unittest.main()
