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
STALE_RUNNING_MINUTES = int(os.getenv("VALIDATOR_STALE_RUNNING_MINUTES", "120"))

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


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_transient(error_summary: str | None) -> bool:
    text = (error_summary or "").lower()
    return any(p in text for p in TRANSIENT_PATTERNS)


def _site_running(runs: list[dict[str, Any]], site: str) -> bool:
    now = datetime.now(timezone.utc)
    for r in runs:
        if r.get("site") != site or r.get("status") != "running":
            continue
        started_at = _parse_iso(r.get("started_at"))
        # Ignore stale running records; they are handled by stale cleanup below.
        if started_at and started_at < now - timedelta(minutes=STALE_RUNNING_MINUTES):
            continue
        return True
    return False


def _mark_run_failed(run_id: str, error_summary: str) -> None:
    payload = {
        "status": "failed",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error_summary": error_summary[:1000],
    }
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/{RUNS_TABLE}?id=eq.{run_id}",
        headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        json=payload,
        timeout=20,
    ).raise_for_status()


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
    stale_marked: list[dict[str, Any]] = []

    for r in runs:
        if r.get("status") != "running":
            continue
        dt = _parse_iso(r.get("started_at"))
        if not dt:
            continue
        if dt >= now - timedelta(minutes=STALE_RUNNING_MINUTES):
            continue
        run_id = r.get("id")
        site = r.get("site") or "unknown"
        if not run_id:
            continue
        try:
            _mark_run_failed(run_id, f"auto-marked failed by validator: stale running over {STALE_RUNNING_MINUTES}m")
            stale_marked.append({"site": site, "run_id": run_id})
        except Exception as exc:  # noqa: BLE001
            json_log("warning", "failed to mark stale running", site=site, run_id=run_id, error=str(exc))

    if stale_marked:
        runs = _fetch_runs(limit=300)

    failed_recent = [
        r for r in runs
        if (r.get("status") in ("failed", "error"))
        and ((not ALLOWLIST) or r.get("site") in ALLOWLIST)
        and _is_recent(r.get("finished_at") or r.get("started_at"), now)
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
        "stale_running_marked": stale_marked,
        "failed_recent": len(failed_recent),
        "retried": retries,
        "skipped": skipped,
    }
    json_log("info", "validator run finished", **report)
    return report


if __name__ == "__main__":
    run_validator()
