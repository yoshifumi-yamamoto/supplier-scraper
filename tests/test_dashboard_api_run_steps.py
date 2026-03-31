import unittest
import sys
import types
from unittest.mock import patch


def _install_dashboard_stubs():
    fastapi = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

        def delete(self, *args, **kwargs):
            return lambda fn: fn

    class _HTTPException(Exception):
        pass

    fastapi.FastAPI = _FastAPI
    fastapi.HTTPException = _HTTPException
    sys.modules.setdefault("fastapi", fastapi)

    responses = types.ModuleType("fastapi.responses")
    responses.FileResponse = object
    responses.JSONResponse = object
    sys.modules.setdefault("fastapi.responses", responses)

    pydantic = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    pydantic.BaseModel = _BaseModel
    sys.modules.setdefault("pydantic", pydantic)

    psutil = types.ModuleType("psutil")
    sys.modules.setdefault("psutil", psutil)


_install_dashboard_stubs()

from apps.dashboard_api import main as dashboard_api


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class DashboardRunStepsPaginationTests(unittest.TestCase):
    @patch.object(dashboard_api, "SUPABASE_URL", "https://example.supabase.co")
    @patch.object(dashboard_api, "SUPABASE_KEY", "test-key")
    @patch.object(dashboard_api, "RUN_STEPS_PAGE_SIZE", 1000)
    def test_fetch_run_steps_paginates_past_supabase_default_limit(self):
        pages = [
            [{"id": str(i)} for i in range(1000)],
            [{"id": str(i)} for i in range(1000, 1500)],
        ]
        offsets: list[int] = []

        def fake_get(url, headers, params, timeout):
            offsets.append(int(params["offset"]))
            return _FakeResponse(pages.pop(0))

        with patch.object(dashboard_api.requests, "get", side_effect=fake_get):
            rows = dashboard_api._fetch_run_steps("run-1", limit=20000)

        self.assertEqual(offsets, [0, 1000])
        self.assertEqual(len(rows), 1500)


if __name__ == "__main__":
    unittest.main()
