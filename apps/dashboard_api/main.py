import os
from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(title="Supplier Scraper Dashboard API")


@app.get('/health')
def health() -> dict:
    return {"ok": True}


@app.get('/api/overview')
def overview() -> dict:
    # TODO: Supabase/Postgres接続に置換
    return {
        "sites": [
            {"site": "yahoofleama", "latest_status": "error", "last_run": datetime.now(timezone.utc).isoformat()},
            {"site": "2ndstreet", "latest_status": "success", "last_run": datetime.now(timezone.utc).isoformat()},
        ],
        "today_runs": int(os.getenv("DUMMY_TODAY_RUNS", "12")),
        "today_failures": int(os.getenv("DUMMY_TODAY_FAILURES", "2")),
    }


@app.get("/api/runs")
def runs() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "items": [
            {"run_id": "run-001", "site": "yahoofleama", "status": "error", "started_at": now, "finished_at": now},
            {"run_id": "run-002", "site": "2ndstreet", "status": "success", "started_at": now, "finished_at": now},
        ]
    }


@app.get("/api/errors")
def errors() -> dict:
    return {
        "items": [
            {"site": "yahoofleama", "error_type": "network", "count": 7, "latest_seen": datetime.now(timezone.utc).isoformat()},
            {"site": "2ndstreet", "error_type": "selector", "count": 2, "latest_seen": datetime.now(timezone.utc).isoformat()},
        ]
    }
