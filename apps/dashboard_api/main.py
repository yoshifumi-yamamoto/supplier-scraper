import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
import psutil

app = FastAPI(title="Supplier Scraper Dashboard API")

JST = timezone(timedelta(hours=9))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
ITEMS_TABLE = os.getenv("ITEMS_TABLE", "items")
RUNS_TABLE = os.getenv("RUNS_TABLE", "scrape_runs")
VALIDATOR_LOG_PATH = os.getenv("VALIDATOR_LOG_PATH", "/var/log/validator_agent.log")


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


@app.get('/health')
def health() -> dict:
    return {"ok": True}


@app.get('/api/overview')
def overview() -> dict:
    try:
        runs_data = _fetch_runs(limit=500)
        if runs_data:
            now_jst = datetime.now(JST).date()
            latest_by_site: dict[str, dict[str, Any]] = {}
            today_runs = 0
            today_failures = 0
            for run in runs_data:
                site = run.get("site") or "unknown"
                started_at = run.get("started_at")
                status = "success" if run.get("status") == "success" else "error"
                if started_at:
                    dt = datetime.fromisoformat(started_at.replace("Z", "+00:00")).astimezone(JST)
                    if dt.date() == now_jst:
                        today_runs += 1
                        if status == "error":
                            today_failures += 1
                prev = latest_by_site.get(site)
                if not prev or (started_at and started_at > (prev.get("last_run") or "")):
                    latest_by_site[site] = {"site": site, "latest_status": status, "last_run": started_at}
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

        for row in items:
            site = _site_from_url(row.get("stocking_url"))
            scraped_at = row.get("scraped_updated_at")
            status = _status_to_dashboard(row.get("scraped_stock_status"))
            if scraped_at:
                dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00")).astimezone(JST)
                if dt.date() == now_jst:
                    today_runs += 1
                    if status == "error":
                        today_failures += 1

            prev = latest_by_site.get(site)
            if not prev:
                latest_by_site[site] = {"site": site, "latest_status": status, "last_run": scraped_at}
                continue
            prev_ts = prev.get("last_run")
            if scraped_at and (not prev_ts or scraped_at > prev_ts):
                latest_by_site[site] = {"site": site, "latest_status": status, "last_run": scraped_at}

        return {
            "sites": sorted(latest_by_site.values(), key=lambda x: x["site"]),
            "today_runs": today_runs,
            "today_failures": today_failures,
            "source": "supabase_items",
        }
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


@app.get("/api/system/schedule")
def system_schedule() -> dict:
    try:
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
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "schedule_fetch_failed", "message": str(exc)})


@app.get("/api/mcp/summary")
def mcp_summary() -> dict:
    try:
        runs_data = _fetch_runs(limit=500)
        now_utc = datetime.now(timezone.utc)
        since_24h = now_utc - timedelta(hours=24)
        success_24h = 0
        failed_24h = 0
        running = 0
        latest_by_site: dict[str, dict[str, Any]] = {}
        error_counter: Counter[str] = Counter()

        for row in runs_data:
            site = row.get("site") or "unknown"
            status = row.get("status") or "unknown"
            started_at = row.get("started_at")
            finished_at = row.get("finished_at")
            error_summary = row.get("error_summary") or ""

            ts = None
            if started_at:
                try:
                    ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                except ValueError:
                    ts = None
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
                    "site": site,
                    "status": status,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "error_summary": error_summary,
                }

            if status == "failed":
                key = error_summary[:120] if error_summary else "failed_without_summary"
                error_counter[key] += 1

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
            "top_errors": [{"message": m, "count": c} for m, c in error_counter.most_common(5)],
            "server": {
                "cpu_percent": psutil.cpu_percent(interval=0.2),
                "memory_percent": vm.percent,
                "chrome_processes": proc["chrome_processes"],
                "runner_processes": proc["runner_processes"],
            },
        }
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
        "status": "unknown",
    }
    try:
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
            retried = row.get("retried") or []
            skipped = row.get("skipped") or []
            return {
                "checked_at": row.get("checked_at"),
                "failed_recent": int(row.get("failed_recent") or 0),
                "retried_count": len(retried),
                "skipped_count": len(skipped),
                "retried": retried[:10],
                "skipped": skipped[:10],
                "status": "ok",
            }
        return fallback
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": "validator_summary_failed", "message": str(exc)})
