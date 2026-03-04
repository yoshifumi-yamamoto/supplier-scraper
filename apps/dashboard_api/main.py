from fastapi import FastAPI

app = FastAPI(title="Supplier Scraper Dashboard API")


@app.get('/health')
def health() -> dict:
    return {"ok": True}


@app.get('/api/overview')
def overview() -> dict:
    return {
        "sites": [
            {"site": "yahoofleama", "latest_status": "unknown", "last_run": None},
        ],
        "today_runs": 0,
        "today_failures": 0,
    }
