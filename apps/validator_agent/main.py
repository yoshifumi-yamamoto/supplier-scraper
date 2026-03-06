import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from scrapers.common.logging_utils import json_log
from scrapers.common.notifier import notify_chatwork

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
RUNS_TABLE = os.getenv("RUNS_TABLE", "scrape_runs")

LOOKBACK_MINUTES = int(os.getenv("VALIDATOR_LOOKBACK_MINUTES", "720"))
ALLOWLIST = {s.strip() for s in os.getenv("VALIDATOR_SITE_ALLOWLIST", "yahoofleama,secondstreet").split(",") if s.strip()}
AUTO_RETRY = os.getenv("VALIDATOR_AUTO_RETRY", "true").lower() == "true"
RETRY_MAX_PAGES = int(os.getenv("VALIDATOR_RETRY_MAX_PAGES", "1"))

TRANSIENT_PATTERNS = (
    "57014",
    "statement timeout",
    "timeout",
    "temporarily unavailable",
    "proxy",
)


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _fetch_runs(limit: int = 200) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{RUNS_TABLE}",
        headers=_headers(),
        params={
            "select": "id,site,status,error_summary,started_at,finished_at",
            "order": "started_at.desc",
            "limit": str(limit),
        },
        timeout=30,
    )
    res.raise_for_status()
    body = res.json()
    return body if isinstance(body, list) else []


def _is_recent(ts: str | None, now_utc: datetime) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt >= now_utc - timedelta(minutes=LOOKBACK_MINUTES)


def _is_transient(error_summary: str | None) -> bool:
    text = (error_summary or "").lower()
    return any(p in text for p in TRANSIENT_PATTERNS)


def _site_running(runs: list[dict[str, Any]], site: str) -> bool:
    return any((r.get("site") == site and r.get("status") == "running") for r in runs)


def _retry_site(site: str) -> dict[str, Any]:
    payload = {
        "name": "retry_failed_step",
        "arguments": {"site": site, "max_pages": RETRY_MAX_PAGES},
    }
    res = requests.post(f"{MCP_BASE_URL}/mcp/call", json=payload, timeout=20)
    res.raise_for_status()
    return res.json()


def run_validator() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    runs = _fetch_runs(limit=300)

    failed_recent = [
        r for r in runs
        if r.get("status") == "failed"
        and r.get("site") in ALLOWLIST
        and _is_recent(r.get("started_at"), now)
    ]

    retries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for run in failed_recent:
        site = run.get("site") or "unknown"
        run_id = run.get("id")
        err = run.get("error_summary")

        if not _is_transient(err):
            skipped.append({"site": site, "run_id": run_id, "reason": "non_transient_error"})
            continue

        if _site_running(runs, site):
            skipped.append({"site": site, "run_id": run_id, "reason": "site_running"})
            continue

        if not AUTO_RETRY:
            skipped.append({"site": site, "run_id": run_id, "reason": "auto_retry_disabled"})
            continue

        try:
            result = _retry_site(site)
            retries.append({"site": site, "failed_run_id": run_id, "retry_result": result})
            notify_chatwork(
                f"validator auto-retry triggered\nsite: {site}\nfailed_run_id: {run_id}\nreason: transient error"
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"site": site, "run_id": run_id, "reason": f"retry_failed: {exc}"})
            notify_chatwork(
                f"validator retry failed\nsite: {site}\nfailed_run_id: {run_id}\nerror: {exc}"
            )

    report = {
        "checked_at": now.isoformat(),
        "lookback_minutes": LOOKBACK_MINUTES,
        "failed_recent": len(failed_recent),
        "retried": retries,
        "skipped": skipped,
    }
    json_log("info", "validator run finished", **report)
    return report


if __name__ == "__main__":
    run_validator()
