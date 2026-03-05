import os
from datetime import datetime, timezone
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


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
    requests.post(
        f"{SUPABASE_URL}/rest/v1/scrape_runs",
        headers=_headers(),
        json=payload,
        timeout=20,
    ).raise_for_status()


def finish_run(run_id: str, status: str, error_summary: str | None = None) -> None:
    if not _enabled():
        return
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_summary:
        payload["error_summary"] = error_summary
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/scrape_runs?id=eq.{run_id}",
        headers=_headers(),
        json=payload,
        timeout=20,
    ).raise_for_status()


def start_step(run_id: str, step_name: str) -> str | None:
    if not _enabled():
        return None
    payload = {
        "run_id": run_id,
        "step_name": step_name,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/scrape_run_steps",
        headers={**_headers(), "Prefer": "return=representation"},
        json=payload,
        timeout=20,
    )
    res.raise_for_status()
    body = res.json()
    if isinstance(body, list) and body:
        return body[0].get("id")
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
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/scrape_run_steps?id=eq.{step_id}",
        headers=_headers(),
        json=payload,
        timeout=20,
    ).raise_for_status()
