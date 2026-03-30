import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
RUNSTORE_RETRIES = int(os.getenv("RUNSTORE_RETRIES", "4"))
RUNSTORE_BACKOFF_BASE = float(os.getenv("RUNSTORE_BACKOFF_BASE", "1.5"))


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _request(method: str, path: str, *, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20):
    last_exc = None
    for attempt in range(RUNSTORE_RETRIES):
        try:
            res = requests.request(
                method,
                f"{SUPABASE_URL}{path}",
                headers=headers or _headers(),
                json=json,
                timeout=timeout,
            )
            if res.status_code >= 500:
                preview = res.text[:300].replace("\n", " ")
                raise requests.HTTPError(f"Supabase {res.status_code}: {preview}", response=res)
            res.raise_for_status()
            return res
        except Exception as exc:
            last_exc = exc
            if attempt == RUNSTORE_RETRIES - 1:
                raise
            time.sleep(RUNSTORE_BACKOFF_BASE * (2 ** attempt))
    raise last_exc  # pragma: no cover


def create_run(run_id: str, site: str, trigger_type: str = "manual") -> None:
    if not _enabled():
        return
    payload = {
        "id": run_id,
        "site": site,
        "status": "running",
        "trigger_type": trigger_type,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _request('POST', '/rest/v1/scrape_runs', json=payload, timeout=20)


def finish_run(run_id: str, status: str, error_summary: str | None = None) -> None:
    if not _enabled():
        return
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["error_summary"] = error_summary[:1000] if error_summary else None
    _request('PATCH', f'/rest/v1/scrape_runs?id=eq.{run_id}', json=payload, timeout=20)


def start_step(run_id: str, step_name: str) -> str | None:
    if not _enabled():
        return None
    payload = {
        "run_id": run_id,
        "step_name": step_name,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    res = _request(
        'POST',
        '/rest/v1/scrape_run_steps',
        headers={**_headers(), 'Prefer': 'return=representation'},
        json=payload,
        timeout=20,
    )
    body = res.json()
    if isinstance(body, list) and body:
        return body[0].get('id')
    return None


def finish_step(step_id: str | None, status: str, message: str | None = None) -> None:
    if not _enabled() or not step_id:
        return
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if message:
        payload["message"] = message[:1000]
    _request('PATCH', f'/rest/v1/scrape_run_steps?id=eq.{step_id}', json=payload, timeout=20)
