import json
import os
import signal
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
import re
import math

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import requests
import psutil
from pydantic import BaseModel

from scrapers.common.error_classifier import classify_error

app = FastAPI(title="Supplier Scraper Dashboard API")

JST = timezone(timedelta(hours=9))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
ITEMS_TABLE = os.getenv("ITEMS_TABLE", "items")
RUNS_TABLE = os.getenv("RUNS_TABLE", "scrape_runs")
RUN_STEPS_TABLE = os.getenv("RUN_STEPS_TABLE", "scrape_run_steps")
VALIDATOR_LOG_PATH = os.getenv("VALIDATOR_LOG_PATH", "/var/log/validator_agent.log")
MERCARI_EXTRACT_SCRIPT = os.getenv(
    "MERCARI_EXTRACT_SCRIPT",
    "/root/supplier-scraper-main/scripts/mercari_extract_search.py",
)
MERCARI_EXTRACT_OUTPUT_DIR = os.getenv(
    "MERCARI_EXTRACT_OUTPUT_DIR",
    "/root/supplier-scraper-main/output/mercari_extract",
)
MERCARI_EXTRACT_LOG_DIR = os.getenv(
    "MERCARI_EXTRACT_LOG_DIR",
    "/var/log",
)
MERCARI_EXTRACT_STATE_DIR = os.getenv(
    "MERCARI_EXTRACT_STATE_DIR",
    "/root/supplier-scraper-main/output/mercari_extract",
)
MERCARI_EXTRACT_ACTIVE_STATE = os.path.join(MERCARI_EXTRACT_STATE_DIR, "active_job.json")
MERCARI_EXTRACT_HISTORY_STATE = os.path.join(MERCARI_EXTRACT_STATE_DIR, "history.json")
KITAMURA_EXTRACT_SCRIPT = os.getenv(
    "KITAMURA_EXTRACT_SCRIPT",
    "/root/supplier-scraper-main/scripts/kitamura_extract_search.py",
)
KITAMURA_EXTRACT_OUTPUT_DIR = os.getenv(
    "KITAMURA_EXTRACT_OUTPUT_DIR",
    "/root/supplier-scraper-main/output/kitamura_extract",
)
KITAMURA_EXTRACT_LOG_DIR = os.getenv(
    "KITAMURA_EXTRACT_LOG_DIR",
    "/var/log",
)
KITAMURA_EXTRACT_STATE_DIR = os.getenv(
    "KITAMURA_EXTRACT_STATE_DIR",
    "/root/supplier-scraper-main/output/kitamura_extract",
)
KITAMURA_EXTRACT_ACTIVE_STATE = os.path.join(KITAMURA_EXTRACT_STATE_DIR, "active_job.json")
KITAMURA_EXTRACT_HISTORY_STATE = os.path.join(KITAMURA_EXTRACT_STATE_DIR, "history.json")
SURUGAYA_EXTRACT_SCRIPT = os.getenv(
    "SURUGAYA_EXTRACT_SCRIPT",
    "/root/supplier-scraper-main/scripts/surugaya_extract_search.py",
)
SURUGAYA_EXTRACT_OUTPUT_DIR = os.getenv(
    "SURUGAYA_EXTRACT_OUTPUT_DIR",
    "/root/supplier-scraper-main/output/surugaya_extract",
)
SURUGAYA_EXTRACT_LOG_DIR = os.getenv(
    "SURUGAYA_EXTRACT_LOG_DIR",
    "/var/log",
)
SURUGAYA_EXTRACT_STATE_DIR = os.getenv(
    "SURUGAYA_EXTRACT_STATE_DIR",
    "/root/supplier-scraper-main/output/surugaya_extract",
)
SURUGAYA_EXTRACT_ACTIVE_STATE = os.path.join(SURUGAYA_EXTRACT_STATE_DIR, "active_job.json")
SURUGAYA_EXTRACT_HISTORY_STATE = os.path.join(SURUGAYA_EXTRACT_STATE_DIR, "history.json")


CACHE_TTL_OVERVIEW = int(os.getenv("DASHBOARD_CACHE_TTL_OVERVIEW", "10"))
CACHE_TTL_MCP_SUMMARY = int(os.getenv("DASHBOARD_CACHE_TTL_MCP_SUMMARY", "10"))
CACHE_TTL_MEMORY = int(os.getenv("DASHBOARD_CACHE_TTL_MEMORY", "5"))
CACHE_TTL_SCHEDULE = int(os.getenv("DASHBOARD_CACHE_TTL_SCHEDULE", "60"))
CACHE_TTL_VALIDATOR = int(os.getenv("DASHBOARD_CACHE_TTL_VALIDATOR", "30"))
_API_CACHE: dict[str, dict[str, Any]] = {}
MCP_DEFAULT_INTERVAL_MIN = int(os.getenv("MCP_DEFAULT_INTERVAL_MIN", "720"))
MCP_ORCHESTRATOR_TICK_MIN = int(os.getenv("MCP_ORCHESTRATOR_TICK_MIN", "10"))

SITE_INTERVAL_MINUTES: dict[str, int] = {
    "mercari": int(os.getenv("MCP_INTERVAL_MERCARI_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "yafuoku": int(os.getenv("MCP_INTERVAL_YAFUOKU_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "hardoff": int(os.getenv("MCP_INTERVAL_HARDOFF_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "yodobashi": int(os.getenv("MCP_INTERVAL_YODOBASHI_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "rakuma": int(os.getenv("MCP_INTERVAL_RAKUMA_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "kitamura": int(os.getenv("MCP_INTERVAL_KITAMURA_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "yahoofleama": int(os.getenv("MCP_INTERVAL_YAHOOFLEAMA_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
    "secondstreet": int(os.getenv("MCP_INTERVAL_SECONDSTREET_MIN", str(MCP_DEFAULT_INTERVAL_MIN))),
}


def _cache_get(key: str) -> Any | None:
    row = _API_CACHE.get(key)
    if not row:
        return None
    if row["expires_at"] <= time.time():
        _API_CACHE.pop(key, None)
        return None
    return row["value"]


def _cache_set(key: str, value: Any, ttl: int) -> Any:
    _API_CACHE[key] = {"value": value, "expires_at": time.time() + max(ttl, 1)}
    return value


def _cached(key: str, ttl: int, builder):
    cached = _cache_get(key)
    if cached is not None:
        return cached
    return _cache_set(key, builder(), ttl)


class MercariExtractRequest(BaseModel):
    search_url: str
    display_name: str
    max_pages: int = 0
    max_items: int = 400
    headless: bool = True


class KitamuraExtractRequest(BaseModel):
    search_url: str
    display_name: str
    max_pages: int = 0
    max_items: int = 400
    headless: bool = True


class SurugayaExtractRequest(BaseModel):
    search_url: str
    display_name: str
    max_pages: int = 0
    max_items: int = 400
    headless: bool = True


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _site_from_url(url: str | None) -> str:
    if not url:
        return "unknown"
    text = url.lower()
    if "paypayfleamarket.yahoo.co.jp" in text:
        return "yahoofleama"
    if "2ndstreet.jp" in text:
        return "2ndstreet"
    if "mercari.com" in text or "jp.mercari.com" in text:
        return "mercari"
    if "fril.jp" in text or "rakuma" in text:
        return "rakuma"
    if "rakuten" in text:
        return "rakuten"
    if "auctions.yahoo.co.jp" in text or "yahoo.co.jp/auction" in text:
        return "yafuoku"
    if "yodobashi.com" in text:
        return "yodobashi"
    if "hardoff" in text:
        return "hardoff"
    if "suruga-ya.jp" in text:
        return "surugaya"
    return "other"


def _status_to_dashboard(status: str | None) -> str:
    if status in ("在庫あり", "in_stock"):
        return "success"
    if status in ("在庫なし", "out_of_stock"):
        return "success"
    if status in ("不明", "unknown", "error", None, ""):
        return "error"
    return "error"


def _fetch_items(limit: int = 5000) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{ITEMS_TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    params = {
        "select": "ebay_item_id,ebay_user_id,stocking_url,listing_status,scraped_stock_status,scraped_updated_at,updated_at",
        "listing_status": "eq.Active",
        "limit": str(limit),
        "order": "scraped_updated_at.desc.nullslast",
    }
    res = requests.get(url, headers=headers, params=params, timeout=30)
    res.raise_for_status()
    data = res.json()
    return data if isinstance(data, list) else []


def _fetch_runs(limit: int = 200) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{RUNS_TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    params = {
        "select": "id,site,status,trigger_type,started_at,finished_at,error_summary",
        "order": "started_at.desc",
        "limit": str(limit),
    }
    res = requests.get(url, headers=headers, params=params, timeout=30)
    if res.status_code >= 400:
        return []
    data = res.json()
    return data if isinstance(data, list) else []


def _fetch_run_steps(run_id: str, limit: int = 20000) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY or not run_id:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{RUN_STEPS_TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    params = {
        "select": "id,run_id,step_name,status,started_at,finished_at,message,updated_at",
        "run_id": f"eq.{run_id}",
        "order": "started_at.asc",
        "limit": str(limit),
    }
    res = requests.get(url, headers=headers, params=params, timeout=60)
    if res.status_code >= 400:
        return []
    data = res.json()
    return data if isinstance(data, list) else []


def _site_interval_minutes(site: str) -> int:
    return SITE_INTERVAL_MINUTES.get(site, MCP_DEFAULT_INTERVAL_MIN)


def _ceil_to_tick(dt: datetime, tick_minutes: int) -> datetime:
    tick_seconds = max(tick_minutes, 1) * 60
    ts = int(dt.timestamp())
    rounded = math.ceil(ts / tick_seconds) * tick_seconds
    return datetime.fromtimestamp(rounded, tz=timezone.utc)


def _extract_total_items_from_steps(steps: list[dict[str, Any]]) -> int | None:
    for step in steps:
        if step.get("step_name") != "fetch_items":
            continue
        message = (step.get("message") or "").strip()
        m = re.search(r"fetched\s+(\d+)\s+items", message)
        if m:
            return int(m.group(1))
    return None


def _summarize_run_steps(run: dict[str, Any]) -> dict[str, Any]:
    run_id = run.get("id")
    steps = _fetch_run_steps(run_id) if run_id else []
    total_items = _extract_total_items_from_steps(steps)
    check_steps = [s for s in steps if str(s.get("step_name") or "").startswith("check:")]
    success_steps = [s for s in check_steps if s.get("status") == "success"]
    failed_steps = [s for s in check_steps if s.get("status") == "failed"]
    running_steps = [s for s in check_steps if s.get("status") == "running"]
    processed = len(success_steps) + len(failed_steps) + len(running_steps)
    remaining = max((total_items or 0) - processed, 0) if total_items is not None else None

    last_step_at: datetime | None = None
    for step in steps:
        for raw in (step.get("updated_at"), step.get("finished_at"), step.get("started_at")):
            dt = _parse_ts(raw)
            if dt and (last_step_at is None or dt > last_step_at):
                last_step_at = dt

    durations_sec: list[float] = []
    for step in success_steps + failed_steps:
        started = _parse_ts(step.get("started_at"))
        finished = _parse_ts(step.get("finished_at"))
        if started and finished and finished >= started:
            durations_sec.append((finished - started).total_seconds())
    avg_step_sec = round(sum(durations_sec) / len(durations_sec), 1) if durations_sec else None
    eta_at = None
    if avg_step_sec and remaining is not None and remaining > 0:
        eta_at = (datetime.now(timezone.utc) + timedelta(seconds=avg_step_sec * remaining)).isoformat()

    return {
        "total_items": total_items,
        "processed_items": processed,
        "remaining_items": remaining,
        "success_items": len(success_steps),
        "failed_items": len(failed_steps),
        "running_items": len(running_steps),
        "progress_percent": round((processed / total_items) * 100) if total_items else None,
        "last_step_at": last_step_at.isoformat() if last_step_at else None,
        "avg_step_sec": avg_step_sec,
        "eta_at": eta_at,
    }


def _site_process_running(site: str) -> bool:
    site = (site or "").strip()
    if not site:
        return False
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
        except Exception:  # noqa: BLE001
            continue
        if not cmdline:
            continue
        if "apps/runner/main.py" not in cmdline:
            continue
        if "--site" not in cmdline:
            continue
        try:
            idx = cmdline.index("--site")
        except ValueError:
            continue
        if idx + 1 < len(cmdline) and cmdline[idx + 1] == site:
            return True
    return False


def _derive_dashboard_status(
    row: dict[str, Any],
    step_summary: dict[str, Any] | None,
    process_alive: bool,
    now_utc: datetime,
) -> tuple[str, str | None]:
    status = row.get("status") or "unknown"
    if status != "running":
        return status, None

    last_activity = _parse_ts(
        (step_summary or {}).get("last_step_at")
        or row.get("finished_at")
        or row.get("started_at")
    )
    activity_age_minutes = None
    if last_activity:
        activity_age_minutes = max(int((now_utc - last_activity).total_seconds() // 60), 0)

    total_items = (step_summary or {}).get("total_items")
    processed_items = (step_summary or {}).get("processed_items")
    running_items = (step_summary or {}).get("running_items")

    if activity_age_minutes is not None and activity_age_minutes >= 60:
        return "stalled", "no_recent_step_activity"
    if process_alive:
        return "running", None
    if total_items is not None and processed_items is not None and processed_items >= total_items and (running_items or 0) == 0:
        return "success", "process_missing_but_all_items_processed"
    if activity_age_minutes is not None and activity_age_minutes >= 15:
        return "stalled", "process_missing_and_no_recent_step_activity"
    return "running", "process_missing_recent_activity"


def _process_counts() -> dict[str, int]:
    chrome = 0
    runner = 0
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if "chrome" in name or "chromedriver" in name:
                chrome += 1
            if "apps/runner/main.py" in cmd or "scrape_status.py" in cmd:
                runner += 1
        except Exception:  # noqa: BLE001
            continue
    return {"chrome_processes": chrome, "runner_processes": runner}


def _is_valid_mercari_search_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc not in ("jp.mercari.com", "mercari.com"):
        return False
    return parsed.path == "/search"


def _is_valid_kitamura_search_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc != "shop.kitamura.jp":
        return False
    return parsed.path == "/ec/list"


def _extract_state_dir() -> None:
    os.makedirs(MERCARI_EXTRACT_OUTPUT_DIR, exist_ok=True)
    os.makedirs(MERCARI_EXTRACT_LOG_DIR, exist_ok=True)
    os.makedirs(MERCARI_EXTRACT_STATE_DIR, exist_ok=True)


def _kitamura_extract_state_dir() -> None:
    os.makedirs(KITAMURA_EXTRACT_OUTPUT_DIR, exist_ok=True)
    os.makedirs(KITAMURA_EXTRACT_LOG_DIR, exist_ok=True)
    os.makedirs(KITAMURA_EXTRACT_STATE_DIR, exist_ok=True)


def _surugaya_extract_state_dir() -> None:
    os.makedirs(SURUGAYA_EXTRACT_OUTPUT_DIR, exist_ok=True)
    os.makedirs(SURUGAYA_EXTRACT_LOG_DIR, exist_ok=True)
    os.makedirs(SURUGAYA_EXTRACT_STATE_DIR, exist_ok=True)


def _sanitize_output_name(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", (value or "").strip())
    slug = slug.strip("._-")
    return slug[:80]


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:  # noqa: BLE001
        return default


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def _read_progress(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    data = _read_json(path, None)
    return data if isinstance(data, dict) else None


def _enrich_extract_job(item: dict[str, Any]) -> dict[str, Any]:
    job = dict(item)
    job["status"] = _job_status(job)
    output_path = job.get("output_path") or ""
    filename = _history_filename(job)
    job["filename"] = filename
    job["download_url"] = f"/api/extract/mercari/download/{filename}" if filename and os.path.exists(output_path) else None
    progress = _read_progress(job.get("progress_path"))
    if progress:
        job["progress"] = progress
    return job


def _enrich_kitamura_extract_job(item: dict[str, Any]) -> dict[str, Any]:
    job = dict(item)
    job["status"] = _job_status(job)
    output_path = job.get("output_path") or ""
    filename = _history_filename(job)
    job["filename"] = filename
    job["download_url"] = f"/api/extract/kitamura/download/{filename}" if filename and os.path.exists(output_path) else None
    progress = _read_progress(job.get("progress_path"))
    if progress:
        job["progress"] = progress
    return job


def _pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    proc_state = f"/proc/{pid}/stat"
    if os.path.exists(proc_state):
        try:
            stat = open(proc_state, "r", encoding="utf-8").read().split()
            if len(stat) > 2 and stat[2] == "Z":
                return False
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _history_filename(row: dict[str, Any]) -> str:
    output_path = row.get("output_path") or ""
    return os.path.basename(output_path) if output_path else ""


def _job_status(job: dict[str, Any]) -> str:
    pid = job.get("pid")
    output_path = job.get("output_path") or ""
    progress = _read_progress(job.get("progress_path"))
    if _pid_running(pid):
        return "running"
    if progress and progress.get("status") in {"cancelled", "failed"}:
        return str(progress.get("status"))
    if job.get("status") in {"cancelled", "failed"}:
        return str(job.get("status"))
    if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return "completed"
    return "failed"


def _cancel_extract_job(job: dict[str, Any], active_state_path: str) -> dict[str, Any]:
    pid = job.get("pid")
    if not pid or not _pid_running(pid):
        raise HTTPException(status_code=409, detail="extract job is not running")

    progress_path = job.get("progress_path")
    progress = _read_progress(progress_path) or {}
    progress.update({
        "status": "cancelling",
        "message": "cancellation requested",
    })
    if progress_path:
        _write_json(progress_path, progress)

    try:
        os.kill(pid, signal.SIGINT)
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"failed to signal process: {exc}") from exc

    deadline = time.time() + 8
    while time.time() < deadline:
        if not _pid_running(pid):
            break
        time.sleep(0.25)

    if _pid_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    progress = _read_progress(progress_path) or {}
    if progress.get("status") not in {"cancelled", "completed"}:
        progress.update({
            "status": "cancelled",
            "message": progress.get("message") or "cancelled by user",
        })
        if progress_path:
            _write_json(progress_path, progress)

    stopped = dict(job)
    stopped["status"] = "cancelled"
    _write_json(active_state_path, {})
    return {"cancelled": True, "job": stopped}


def _load_active_job() -> dict[str, Any] | None:
    job = _read_json(MERCARI_EXTRACT_ACTIVE_STATE, None)
    if not isinstance(job, dict):
        return None
    if _job_status(job) != "running":
        _write_json(MERCARI_EXTRACT_ACTIVE_STATE, {})
        return None
    return _enrich_extract_job(job)


def _load_kitamura_active_job() -> dict[str, Any] | None:
    job = _read_json(KITAMURA_EXTRACT_ACTIVE_STATE, None)
    if not isinstance(job, dict):
        return None
    if _job_status(job) != "running":
        _write_json(KITAMURA_EXTRACT_ACTIVE_STATE, {})
        return None
    return _enrich_kitamura_extract_job(job)


def _load_history() -> list[dict[str, Any]]:
    rows = _read_json(MERCARI_EXTRACT_HISTORY_STATE, [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        out.append(_enrich_extract_job(row))
    return out


def _load_kitamura_history() -> list[dict[str, Any]]:
    rows = _read_json(KITAMURA_EXTRACT_HISTORY_STATE, [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        out.append(_enrich_kitamura_extract_job(row))
    return out


def _append_history(job: dict[str, Any]) -> None:
    rows = _load_history()
    rows = [job] + [r for r in rows if r.get("started_at") != job.get("started_at")][:99]
    _write_json(MERCARI_EXTRACT_HISTORY_STATE, rows)


def _append_kitamura_history(job: dict[str, Any]) -> None:
    rows = _load_kitamura_history()
    rows = [job] + [r for r in rows if r.get("started_at") != job.get("started_at")][:99]
    _write_json(KITAMURA_EXTRACT_HISTORY_STATE, rows)


@app.get('/health')
def health() -> dict:
    return {"ok": True}


@app.get("/api/extract/mercari/status")
def mercari_extract_status() -> dict:
    _extract_state_dir()
    active = _load_active_job()
    return {"active_job": active}


@app.post("/api/extract/mercari/stop")
def mercari_extract_stop() -> dict:
    _extract_state_dir()
    active = _load_active_job()
    if not active:
        raise HTTPException(status_code=404, detail="no active extract")
    return _cancel_extract_job(active, MERCARI_EXTRACT_ACTIVE_STATE)


@app.get("/api/extract/mercari/history")
def mercari_extract_history() -> dict:
    _extract_state_dir()
    return {"items": _load_history()}


@app.get("/api/extract/mercari/download/{filename}")
def mercari_extract_download(filename: str) -> FileResponse:
    safe_name = os.path.basename(filename)
    target = os.path.abspath(os.path.join(MERCARI_EXTRACT_OUTPUT_DIR, safe_name))
    root = os.path.abspath(MERCARI_EXTRACT_OUTPUT_DIR)
    if not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target, filename=safe_name, media_type="text/csv")


@app.delete("/api/extract/mercari/history/{filename}")
def mercari_extract_delete(filename: str) -> dict:
    _extract_state_dir()
    safe_name = os.path.basename(filename)
    active = _load_active_job()
    if active and _history_filename(active) == safe_name:
        raise HTTPException(status_code=409, detail="cannot delete active extract")

    target = os.path.abspath(os.path.join(MERCARI_EXTRACT_OUTPUT_DIR, safe_name))
    root = os.path.abspath(MERCARI_EXTRACT_OUTPUT_DIR)
    if not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="invalid filename")

    history = _read_json(MERCARI_EXTRACT_HISTORY_STATE, [])
    if not isinstance(history, list):
        history = []
    removed = False
    kept: list[dict[str, Any]] = []
    log_path = None
    for row in history:
        if not isinstance(row, dict):
            continue
        if _history_filename(row) == safe_name:
            removed = True
            log_path = row.get("log_path") or log_path
            continue
        kept.append(row)
    _write_json(MERCARI_EXTRACT_HISTORY_STATE, kept)

    if os.path.exists(target):
        os.remove(target)
        removed = True
    if log_path and os.path.exists(log_path):
        os.remove(log_path)

    if not removed:
        raise HTTPException(status_code=404, detail="history file not found")

    return {"deleted": True, "filename": safe_name}


@app.post("/api/extract/mercari/start")
def start_mercari_extract(req: MercariExtractRequest) -> dict:
    if not _is_valid_mercari_search_url(req.search_url):
        raise HTTPException(status_code=400, detail="search_url must be a Mercari search URL")
    if req.max_pages < 0 or req.max_pages > 100:
        raise HTTPException(status_code=400, detail="max_pages must be between 0 and 100")
    if req.max_items < 1 or req.max_items > 10000:
        raise HTTPException(status_code=400, detail="max_items must be between 1 and 10000")
    display_name = (req.display_name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    base_name = _sanitize_output_name(display_name) or "kitamura_extract" or "mercari_extract" or "mercari_extract"
    if not os.path.exists(MERCARI_EXTRACT_SCRIPT):
        raise HTTPException(status_code=500, detail="extract script not found")

    _extract_state_dir()
    active_job = _load_active_job()
    if active_job:
        raise HTTPException(status_code=409, detail={"message": "extract already running", "active_job": active_job})

    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(MERCARI_EXTRACT_OUTPUT_DIR, f"{base_name}_{ts}.csv")
    log_path = os.path.join(MERCARI_EXTRACT_LOG_DIR, f"{base_name}_{ts}.log")
    progress_path = os.path.join(MERCARI_EXTRACT_STATE_DIR, f"{base_name}_{ts}.progress.json")

    command = [
        "python3",
        MERCARI_EXTRACT_SCRIPT,
        "--search-url",
        req.search_url,
        "--output",
        output_path,
        "--max-pages",
        str(req.max_pages),
        "--progress",
        progress_path,
    ]
    if req.max_items:
        command.extend(["--max-items", str(req.max_items)])
    if req.headless:
        command.append("--headless")

    with open(log_path, "a", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(  # noqa: S603
            command,
            stdout=log_fp,
            stderr=log_fp,
            cwd="/root/supplier-scraper-main",
        )

    job = {
        "accepted": True,
        "pid": proc.pid,
        "display_name": display_name,
        "output_name": base_name,
        "output_path": output_path,
        "log_path": log_path,
        "progress_path": progress_path,
        "search_url": req.search_url,
        "max_pages": req.max_pages,
        "max_items": req.max_items,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(MERCARI_EXTRACT_ACTIVE_STATE, job)
    _append_history(job)
    job["status"] = "running"
    job["filename"] = os.path.basename(output_path)
    job["download_url"] = None
    return job


@app.get("/api/extract/kitamura/status")
def kitamura_extract_status() -> dict:
    _kitamura_extract_state_dir()
    active = _load_kitamura_active_job()
    return {"active_job": active}


@app.post("/api/extract/kitamura/stop")
def kitamura_extract_stop() -> dict:
    _kitamura_extract_state_dir()
    active = _load_kitamura_active_job()
    if not active:
        raise HTTPException(status_code=404, detail="no active extract")
    return _cancel_extract_job(active, KITAMURA_EXTRACT_ACTIVE_STATE)


@app.get("/api/extract/kitamura/history")
def kitamura_extract_history() -> dict:
    _kitamura_extract_state_dir()
    return {"items": _load_kitamura_history()}


@app.get("/api/extract/kitamura/download/{filename}")
def kitamura_extract_download(filename: str) -> FileResponse:
    safe_name = os.path.basename(filename)
    target = os.path.abspath(os.path.join(KITAMURA_EXTRACT_OUTPUT_DIR, safe_name))
    root = os.path.abspath(KITAMURA_EXTRACT_OUTPUT_DIR)
    if not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target, filename=safe_name, media_type="text/csv")


@app.delete("/api/extract/kitamura/history/{filename}")
def kitamura_extract_delete(filename: str) -> dict:
    _kitamura_extract_state_dir()
    safe_name = os.path.basename(filename)
    active = _load_kitamura_active_job()
    if active and _history_filename(active) == safe_name:
        raise HTTPException(status_code=409, detail="cannot delete active extract")

    target = os.path.abspath(os.path.join(KITAMURA_EXTRACT_OUTPUT_DIR, safe_name))
    root = os.path.abspath(KITAMURA_EXTRACT_OUTPUT_DIR)
    if not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="invalid filename")

    history = _read_json(KITAMURA_EXTRACT_HISTORY_STATE, [])
    if not isinstance(history, list):
        history = []
    removed = False
    kept: list[dict[str, Any]] = []
    log_path = None
    for row in history:
        if not isinstance(row, dict):
            continue
        if _history_filename(row) == safe_name:
            removed = True
            log_path = row.get("log_path") or log_path
            continue
        kept.append(row)
    _write_json(KITAMURA_EXTRACT_HISTORY_STATE, kept)

    if os.path.exists(target):
        os.remove(target)
        removed = True
    if log_path and os.path.exists(log_path):
        os.remove(log_path)

    if not removed:
        raise HTTPException(status_code=404, detail="history file not found")

    return {"deleted": True, "filename": safe_name}


@app.post("/api/extract/kitamura/start")
def start_kitamura_extract(req: KitamuraExtractRequest) -> dict:
    if not _is_valid_kitamura_search_url(req.search_url):
        raise HTTPException(status_code=400, detail="search_url must be a Kitamura listing URL")
    if req.max_pages < 0 or req.max_pages > 100:
        raise HTTPException(status_code=400, detail="max_pages must be between 0 and 100")
    if req.max_items < 1 or req.max_items > 10000:
        raise HTTPException(status_code=400, detail="max_items must be between 1 and 10000")
    display_name = (req.display_name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    base_name = _sanitize_output_name(display_name) or "kitamura_extract"
    if not os.path.exists(KITAMURA_EXTRACT_SCRIPT):
        raise HTTPException(status_code=500, detail="extract script not found")

    _kitamura_extract_state_dir()
    active_job = _load_kitamura_active_job()
    if active_job:
        raise HTTPException(status_code=409, detail={"message": "extract already running", "active_job": active_job})

    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(KITAMURA_EXTRACT_OUTPUT_DIR, f"{base_name}_{ts}.csv")
    log_path = os.path.join(KITAMURA_EXTRACT_LOG_DIR, f"{base_name}_{ts}.log")
    progress_path = os.path.join(KITAMURA_EXTRACT_STATE_DIR, f"{base_name}_{ts}.progress.json")

    command = [
        "python3",
        KITAMURA_EXTRACT_SCRIPT,
        "--search-url",
        req.search_url,
        "--output",
        output_path,
        "--max-pages",
        str(req.max_pages),
        "--progress",
        progress_path,
    ]
    if req.max_items:
        command.extend(["--max-items", str(req.max_items)])
    if req.headless:
        command.append("--headless")

    with open(log_path, "a", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            command,
            stdout=log_fp,
            stderr=log_fp,
            cwd="/root/supplier-scraper-main",
        )

    job = {
        "accepted": True,
        "pid": proc.pid,
        "display_name": display_name,
        "output_name": base_name,
        "output_path": output_path,
        "log_path": log_path,
        "progress_path": progress_path,
        "search_url": req.search_url,
        "max_pages": req.max_pages,
        "max_items": req.max_items,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(KITAMURA_EXTRACT_ACTIVE_STATE, job)
    _append_kitamura_history(job)
    job["status"] = "running"
    job["filename"] = os.path.basename(output_path)
    job["download_url"] = None
    return job




def _is_valid_surugaya_search_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    return parsed.netloc == "www.suruga-ya.jp" and parsed.path == "/search"


def _enrich_surugaya_extract_job(item: dict[str, Any]) -> dict[str, Any]:
    job = dict(item)
    job["status"] = _job_status(job)
    output_path = job.get("output_path") or ""
    filename = _history_filename(job)
    job["filename"] = filename
    job["download_url"] = f"/api/extract/surugaya/download/{filename}" if filename and os.path.exists(output_path) else None
    progress = _read_progress(job.get("progress_path"))
    if progress:
        job["progress"] = progress
    return job


def _load_surugaya_active_job() -> dict | None:
    _surugaya_extract_state_dir()
    job = _read_json(SURUGAYA_EXTRACT_ACTIVE_STATE, None)
    if not isinstance(job, dict):
        return None
    if _job_status(job) != "running":
        _write_json(SURUGAYA_EXTRACT_ACTIVE_STATE, {})
        return None
    return _enrich_surugaya_extract_job(job)


def _load_surugaya_history() -> list[dict]:
    _surugaya_extract_state_dir()
    rows = _read_json(SURUGAYA_EXTRACT_HISTORY_STATE, [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        enriched = _enrich_surugaya_extract_job(row)
        progress = enriched.get("progress") or {}
        enriched["extracted_count"] = progress.get("extracted_count", row.get("extracted_count", 0))
        enriched["skip_count"] = progress.get("skip_count", row.get("skip_count", 0))
        enriched["page"] = progress.get("page", row.get("page", 0))
        out.append(enriched)
    return out


def _append_surugaya_history(job: dict) -> None:
    history = _read_json(SURUGAYA_EXTRACT_HISTORY_STATE, [])
    if not isinstance(history, list):
        history = []
    history = [row for row in history if row.get("output_path") != job.get("output_path")]
    history.insert(0, job)
    _write_json(SURUGAYA_EXTRACT_HISTORY_STATE, history[:100])


@app.get("/api/extract/surugaya/status")
def surugaya_extract_status() -> dict:
    return {"active_job": _load_surugaya_active_job()}


@app.post("/api/extract/surugaya/stop")
def surugaya_extract_stop() -> dict:
    _surugaya_extract_state_dir()
    active = _load_surugaya_active_job()
    if not active:
        raise HTTPException(status_code=404, detail="no active extract")
    return _cancel_extract_job(active, SURUGAYA_EXTRACT_ACTIVE_STATE)


@app.get("/api/extract/surugaya/history")
def surugaya_extract_history() -> dict:
    return {"items": _load_surugaya_history()}


@app.get("/api/extract/surugaya/download/{filename}")
def surugaya_extract_download(filename: str):
    _surugaya_extract_state_dir()
    file_path = os.path.join(SURUGAYA_EXTRACT_OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(file_path, filename=filename, media_type="text/csv")


@app.delete("/api/extract/surugaya/history/{filename}")
def surugaya_extract_delete(filename: str) -> dict:
    _surugaya_extract_state_dir()
    history = _read_json(SURUGAYA_EXTRACT_HISTORY_STATE, [])
    if not isinstance(history, list):
        history = []
    target = None
    remaining = []
    for row in history:
        if os.path.basename(row.get("output_path") or "") == filename:
            target = row
        else:
            remaining.append(row)
    if not target:
        raise HTTPException(status_code=404, detail="history not found")
    active = _load_surugaya_active_job()
    if active and os.path.basename(active.get("output_path") or "") == filename:
        raise HTTPException(status_code=409, detail="extract job is running")
    for path in (target.get("output_path"), target.get("log_path"), target.get("progress_path")):
        if path and os.path.exists(path):
            os.remove(path)
    _write_json(SURUGAYA_EXTRACT_HISTORY_STATE, remaining)
    return {"deleted": True, "filename": filename}


@app.post("/api/extract/surugaya/start")
def surugaya_extract_start(req: SurugayaExtractRequest) -> dict:
    if not _is_valid_surugaya_search_url(req.search_url):
        raise HTTPException(status_code=400, detail="invalid surugaya search url")
    if _load_surugaya_active_job():
        raise HTTPException(status_code=409, detail="extract already running")
    display_name = (req.display_name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    _surugaya_extract_state_dir()
    base_name = _sanitize_output_name(display_name) or 'surugaya_extract'
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_name = f"{base_name}_{timestamp}.csv"
    output_path = os.path.join(SURUGAYA_EXTRACT_OUTPUT_DIR, output_name)
    log_path = os.path.join(SURUGAYA_EXTRACT_LOG_DIR, f"surugaya_extract_{timestamp}.log")
    progress_path = os.path.join(SURUGAYA_EXTRACT_OUTPUT_DIR, f"surugaya_extract_{timestamp}.progress.json")
    command = ["python3", SURUGAYA_EXTRACT_SCRIPT, "--search-url", req.search_url, "--output", output_path, "--max-pages", str(req.max_pages), "--progress", progress_path]
    if req.max_items:
        command.extend(["--max-items", str(req.max_items)])
    if req.headless:
        command.append("--headless")
    with open(log_path, 'a', encoding='utf-8') as log_fp:
        proc = subprocess.Popen(command, stdout=log_fp, stderr=log_fp, cwd="/root/supplier-scraper-main")
    job = {"accepted": True, "pid": proc.pid, "display_name": display_name, "output_name": base_name, "output_path": output_path, "log_path": log_path, "progress_path": progress_path, "search_url": req.search_url, "max_pages": req.max_pages, "max_items": req.max_items, "started_at": datetime.now(timezone.utc).isoformat()}
    _write_json(SURUGAYA_EXTRACT_ACTIVE_STATE, job)
    _append_surugaya_history(job)
    job["status"] = "running"
    job["filename"] = os.path.basename(output_path)
    job["download_url"] = None
    return job


@app.get('/api/overview')
def overview() -> dict:
    try:
        def build() -> dict:
            runs_data = _fetch_runs(limit=500)
            if runs_data:
                now_jst = datetime.now(JST).date()
                latest_by_site: dict[str, dict[str, Any]] = {}
                today_runs = 0
                today_failures = 0
                run_stats: dict[str, dict[str, int]] = {}
                for run in runs_data:
                    site = run.get("site") or "unknown"
                    started_at = run.get("started_at")
                    raw_status = run.get("status") or "unknown"
                    status = "success" if raw_status == "success" else ("running" if raw_status == "running" else "error")
                    stat = run_stats.setdefault(site, {"recent_runs": 0, "recent_success": 0})
                    if stat["recent_runs"] < 7:
                        stat["recent_runs"] += 1
                        if raw_status == "success":
                            stat["recent_success"] += 1
                    if started_at:
                        dt_obj = _parse_ts(started_at)
                        if not dt_obj:
                            continue
                        dt = dt_obj.astimezone(JST)
                        if dt.date() == now_jst:
                            today_runs += 1
                            if status == "error":
                                today_failures += 1
                    prev = latest_by_site.get(site)
                    if not prev or (started_at and started_at > (prev.get("last_run") or "")):
                        latest_by_site[site] = {
                            "site": site,
                            "latest_status": status,
                            "last_run": started_at,
                            "last_run_status": raw_status,
                            "run_success_rate": 0,
                            "success_rate": 100 if raw_status == "success" else (70 if raw_status == "running" else 0),
                        }
                for site, stat in run_stats.items():
                    if site in latest_by_site:
                        latest_by_site[site]["run_success_rate"] = round((stat["recent_success"] / stat["recent_runs"]) * 100) if stat["recent_runs"] else 0
                return {
                    "sites": sorted(latest_by_site.values(), key=lambda x: x["site"]),
                    "today_runs": today_runs,
                    "today_failures": today_failures,
                    "source": "supabase_scrape_runs",
                }

            items = _fetch_items()
            if not items:
                return {
                    "sites": [],
                    "today_runs": 0,
                    "today_failures": 0,
                    "source": "fallback_empty",
                }

            now_jst = datetime.now(JST).date()
            latest_by_site: dict[str, dict[str, Any]] = {}
            today_runs = 0
            today_failures = 0

            counters: dict[str, dict[str, int]] = {}
            for row in items:
                site = _site_from_url(row.get("stocking_url"))
                scraped_at = row.get("scraped_updated_at")
                status = _status_to_dashboard(row.get("scraped_stock_status"))
                bucket = counters.setdefault(site, {"total": 0, "known": 0})
                bucket["total"] += 1
                if status != "error":
                    bucket["known"] += 1
                if scraped_at:
                    dt_obj = _parse_ts(scraped_at)
                    if not dt_obj:
                        continue
                    dt = dt_obj.astimezone(JST)
                    if dt.date() == now_jst:
                        today_runs += 1
                        if status == "error":
                            today_failures += 1

                prev = latest_by_site.get(site)
                if not prev:
                    latest_by_site[site] = {
                        "site": site,
                        "latest_status": status,
                        "last_run": scraped_at,
                        "last_run_status": status,
                    }
                    continue
                prev_ts = prev.get("last_run")
                if scraped_at and (not prev_ts or scraped_at > prev_ts):
                    latest_by_site[site] = {
                        "site": site,
                        "latest_status": status,
                        "last_run": scraped_at,
                        "last_run_status": status,
                    }
            for site, count in counters.items():
                if site in latest_by_site:
                    latest_by_site[site]["success_rate"] = round((count["known"] / count["total"]) * 100) if count["total"] else 0
                    latest_by_site[site]["run_success_rate"] = None

            return {
                "sites": sorted(latest_by_site.values(), key=lambda x: x["site"]),
                "today_runs": today_runs,
                "today_failures": today_failures,
                "source": "supabase_items",
            }

        return _cached("overview", CACHE_TTL_OVERVIEW, build)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={
                "error": "overview_fetch_failed",
                "message": str(exc),
            },
        )


@app.get("/api/runs")
def runs() -> dict:
    try:
        runs_data = _fetch_runs(limit=200)
        if runs_data:
            out = [
                {
                    "run_id": row.get("id"),
                    "site": row.get("site"),
                    "status": "success" if row.get("status") == "success" else "error",
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                    "items": None,
                    "errors": 1 if row.get("status") == "failed" else 0,
                    "error_summary": row.get("error_summary"),
                }
                for row in runs_data
            ]
            return {"items": out, "source": "supabase_scrape_runs"}

        items = _fetch_items(limit=1000)
        buckets: dict[str, dict[str, Any]] = {}
        for row in items:
            site = _site_from_url(row.get("stocking_url"))
            scraped_at = row.get("scraped_updated_at")
            if not scraped_at:
                continue
            key = f"{site}:{scraped_at[:13]}"
            status = _status_to_dashboard(row.get("scraped_stock_status"))
            bucket = buckets.setdefault(
                key,
                {
                    "run_id": key.replace(":", "-"),
                    "site": site,
                    "status": "success",
                    "started_at": scraped_at,
                    "finished_at": scraped_at,
                    "items": 0,
                    "errors": 0,
                },
            )
            bucket["items"] += 1
            if status == "error":
                bucket["errors"] += 1
                bucket["status"] = "error"
            if scraped_at < bucket["started_at"]:
                bucket["started_at"] = scraped_at
            if scraped_at > bucket["finished_at"]:
                bucket["finished_at"] = scraped_at
        out = sorted(buckets.values(), key=lambda x: x["finished_at"], reverse=True)[:100]
        return {"items": out, "source": "supabase_items_derived"}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "runs_fetch_failed", "message": str(exc)})


@app.get("/api/errors")
def errors() -> dict:
    try:
        runs_data = _fetch_runs(limit=500)
        if runs_data:
            counter: Counter[tuple[str, str]] = Counter()
            latest_seen: dict[tuple[str, str], str] = {}
            for row in runs_data:
                if row.get("status") != "failed":
                    continue
                site = row.get("site") or "unknown"
                error_type = "pipeline_failed"
                key = (site, error_type)
                counter[key] += 1
                ts = row.get("finished_at") or row.get("started_at")
                if ts and (key not in latest_seen or ts > latest_seen[key]):
                    latest_seen[key] = ts
            out = [
                {
                    "site": site,
                    "error_type": error_type,
                    "count": count,
                    "latest_seen": latest_seen.get((site, error_type)),
                }
                for (site, error_type), count in counter.items()
            ]
            out.sort(key=lambda x: x["count"], reverse=True)
            return {"items": out, "source": "supabase_scrape_runs"}

        items = _fetch_items(limit=5000)
        counter: Counter[tuple[str, str]] = Counter()
        latest_seen: dict[tuple[str, str], str] = {}
        for row in items:
            raw = row.get("scraped_stock_status")
            if raw not in ("不明", "unknown", "error", None, ""):
                continue
            site = _site_from_url(row.get("stocking_url"))
            error_type = "unknown_status"
            key = (site, error_type)
            counter[key] += 1
            ts = row.get("scraped_updated_at") or row.get("updated_at")
            if ts and (key not in latest_seen or ts > latest_seen[key]):
                latest_seen[key] = ts
        out = [
            {
                "site": site,
                "error_type": error_type,
                "count": count,
                "latest_seen": latest_seen.get((site, error_type)),
            }
            for (site, error_type), count in counter.items()
        ]
        out.sort(key=lambda x: x["count"], reverse=True)
        return {"items": out, "source": "supabase_items_derived"}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "errors_fetch_failed", "message": str(exc)})


@app.get("/api/system/memory")
def system_memory() -> dict:
    def build() -> dict:
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        return {
            "memory": {
                "total_mb": round(vm.total / 1024 / 1024, 2),
                "used_mb": round(vm.used / 1024 / 1024, 2),
                "available_mb": round(vm.available / 1024 / 1024, 2),
                "percent": vm.percent,
            },
            "swap": {
                "total_mb": round(sm.total / 1024 / 1024, 2),
                "used_mb": round(sm.used / 1024 / 1024, 2),
                "free_mb": round(sm.free / 1024 / 1024, 2),
                "percent": sm.percent,
            },
        }

    return _cached("system_memory", CACHE_TTL_MEMORY, build)


@app.get("/api/system/schedule")
def system_schedule() -> dict:
    try:
        def build() -> dict:
            proc = subprocess.run(
                ["crontab", "-l"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = proc.stdout if proc.returncode == 0 else ""
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            items: list[dict[str, str]] = []
            for ln in lines:
                parts = ln.split(maxsplit=5)
                if len(parts) < 6:
                    continue
                schedule = " ".join(parts[:5])
                command = parts[5]
                if (
                    "run_all_scrapes.sh" in command
                    or "mcp_watchdog.sh" in command
                    or "mcp_run_site.sh" in command
                ):
                    items.append({"schedule": schedule, "command": command})
            return {"timezone": "Asia/Tokyo", "items": items}

        return _cached("system_schedule", CACHE_TTL_SCHEDULE, build)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "schedule_fetch_failed", "message": str(exc)})


@app.get("/api/mcp/summary")
def mcp_summary() -> dict:
    try:
        def build() -> dict:
            runs_data = _fetch_runs(limit=500)
            now_utc = datetime.now(timezone.utc)
            since_24h = now_utc - timedelta(hours=24)
            success_24h = 0
            failed_24h = 0
            running = 0
            latest_by_site: dict[str, dict[str, Any]] = {}
            error_counter: Counter[str] = Counter()
            error_last_seen: dict[str, str] = {}

            for row in runs_data:
                site = row.get("site") or "unknown"
                status = row.get("status") or "unknown"
                started_at = row.get("started_at")
                finished_at = row.get("finished_at")
                error_summary = row.get("error_summary") or ""

                if started_at:
                    ts = _parse_ts(started_at)
                    if ts and ts >= since_24h:
                        if status == "success":
                            success_24h += 1
                        elif status == "failed":
                            failed_24h += 1

                if status == "running":
                    running += 1

                prev = latest_by_site.get(site)
                if not prev or ((started_at or "") > (prev.get("started_at") or "")):
                    latest_by_site[site] = {
                        "id": row.get("id"),
                        "site": site,
                        "status": status,
                        "trigger_type": row.get("trigger_type"),
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "error_summary": error_summary,
                        "error_type": classify_error(error_summary),
                    }

                if status == "failed":
                    error_type = classify_error(error_summary)
                    key = f"{error_type}:{error_summary[:120] if error_summary else 'failed_without_summary'}"
                    error_counter[key] += 1
                    seen_at = finished_at or started_at or ""
                    if seen_at and seen_at > error_last_seen.get(key, ""):
                        error_last_seen[key] = seen_at

            for site, row in list(latest_by_site.items()):
                started_dt = _parse_ts(row.get("started_at"))
                finished_dt = _parse_ts(row.get("finished_at"))
                current_dt = started_dt or finished_dt
                elapsed_minutes = None
                if current_dt:
                    end_dt = now_utc if row.get("status") == "running" else (finished_dt or now_utc)
                    elapsed_minutes = max(int((end_dt - current_dt).total_seconds() // 60), 0)
                interval_min = _site_interval_minutes(site)
                next_run_at = None
                if row.get("status") == "running":
                    next_run_at = None
                elif started_dt:
                    eligible_at = started_dt + timedelta(minutes=interval_min)
                    next_run_at = _ceil_to_tick(eligible_at, MCP_ORCHESTRATOR_TICK_MIN).isoformat()

                process_alive = _site_process_running(site)
                step_summary = _summarize_run_steps(row) if row.get("status") == "running" else None
                display_status, status_reason = _derive_dashboard_status(row, step_summary, process_alive, now_utc)

                row["elapsed_minutes"] = elapsed_minutes
                row["next_run_at"] = next_run_at
                row["interval_minutes"] = interval_min
                row["step_summary"] = step_summary
                row["process_alive"] = process_alive
                row["display_status"] = display_status
                row["display_status_reason"] = status_reason

            proc = _process_counts()
            vm = psutil.virtual_memory()
            return {
                "kpis": {
                    "success_24h": success_24h,
                    "failed_24h": failed_24h,
                    "running_runs": running,
                    "sites_tracked": len(latest_by_site),
                },
                "latest_by_site": sorted(latest_by_site.values(), key=lambda x: x["site"]),
                "top_errors": [
                    {
                        "message": m.split(":", 1)[1] if ":" in m else m,
                        "error_type": m.split(":", 1)[0] if ":" in m else "unknown",
                        "count": c,
                        "last_seen_at": error_last_seen.get(m),
                    }
                    for m, c in error_counter.most_common(5)
                ],
                "server": {
                    "cpu_percent": psutil.cpu_percent(interval=0.2),
                    "memory_percent": vm.percent,
                    "chrome_processes": proc["chrome_processes"],
                    "runner_processes": proc["runner_processes"],
                },
            }

        return _cached("mcp_summary", CACHE_TTL_MCP_SUMMARY, build)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "mcp_summary_failed", "message": str(exc)})


@app.get("/api/validator/summary")
def validator_summary() -> dict:
    fallback = {
        "checked_at": None,
        "failed_recent": 0,
        "retried_count": 0,
        "skipped_count": 0,
        "retried": [],
        "skipped": [],
        "ai_notification": None,
        "status": "unknown",
    }
    try:
        def build() -> dict:
            if not os.path.exists(VALIDATOR_LOG_PATH):
                return fallback
            with open(VALIDATOR_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-300:]
            for line in reversed(lines):
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if row.get("message") != "validator run finished":
                    continue
                ctx = row.get("context") or {}
                retried = ctx.get("retried") or []
                skipped = ctx.get("skipped") or []
                ai_notification = ctx.get("ai_notification")
                return {
                    "checked_at": ctx.get("checked_at"),
                    "failed_recent": int(ctx.get("failed_recent") or 0),
                    "retried_count": len(retried),
                    "skipped_count": len(skipped),
                    "retried": retried[:10],
                    "skipped": skipped[:10],
                    "ai_notification": ai_notification if isinstance(ai_notification, dict) else None,
                    "status": "ok",
                }
            return fallback

        return _cached("validator_summary", CACHE_TTL_VALIDATOR, build)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "validator_summary_failed", "message": str(exc)})
