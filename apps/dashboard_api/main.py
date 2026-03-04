import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests

app = FastAPI(title="Supplier Scraper Dashboard API")

JST = timezone(timedelta(hours=9))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
ITEMS_TABLE = os.getenv("ITEMS_TABLE", "items")


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


@app.get('/health')
def health() -> dict:
    return {"ok": True}


@app.get('/api/overview')
def overview() -> dict:
    try:
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
