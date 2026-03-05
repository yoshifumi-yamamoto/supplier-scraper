import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Supplier Scraper MCP Server")

ROOT_DIR = Path(__file__).resolve().parents[2]
JOB_LOG_DIR = Path(os.getenv("MCP_JOB_LOG_DIR", "/tmp/supplier-mcp-jobs"))
JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

ALLOWED_SITES = {"yahoofleama", "secondstreet"}
JOBS: dict[str, dict[str, Any]] = {}


class MCPCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _require_supabase() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=400, detail="SUPABASE_URL / SUPABASE_KEY is not set")


def _poll_job(job_id: str) -> dict[str, Any]:
    job = JOBS[job_id]
    proc: subprocess.Popen[str] = job["process"]
    if job["status"] == "running":
        code = proc.poll()
        if code is not None:
            job["status"] = "success" if code == 0 else "failed"
            job["return_code"] = code
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": job_id,
        "site": job["site"],
        "status": job["status"],
        "run_id": job["run_id"],
        "started_at": job["started_at"],
        "finished_at": job.get("finished_at"),
        "return_code": job.get("return_code"),
        "log_path": str(job["log_path"]),
    }


def _tool_run_scrape(args: dict[str, Any]) -> dict[str, Any]:
    site = str(args.get("site", ""))
    if site not in ALLOWED_SITES:
        raise HTTPException(status_code=400, detail=f"unsupported site: {site}")

    max_pages = args.get("max_pages")
    run_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    log_path = JOB_LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{site}_{job_id}.log"
    log_file = open(log_path, "w", encoding="utf-8")

    env = os.environ.copy()
    env["RUN_ID"] = run_id
    if max_pages is not None:
        env["MAX_PAGES"] = str(max_pages)

    cmd = [sys.executable, "apps/runner/main.py", "--site", site]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    JOBS[job_id] = {
        "job_id": job_id,
        "process": proc,
        "site": site,
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "log_path": log_path,
    }
    return {
        "job_id": job_id,
        "site": site,
        "run_id": run_id,
        "status": "running",
        "log_path": str(log_path),
    }


def _tool_get_job_status(args: dict[str, Any]) -> dict[str, Any]:
    job_id = str(args.get("job_id", ""))
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return _poll_job(job_id)


def _tool_get_run_status(args: dict[str, Any]) -> dict[str, Any]:
    _require_supabase()
    site = args.get("site")
    run_id = args.get("run_id")
    limit = int(args.get("limit", 10))
    params: dict[str, str] = {
        "select": "id,site,status,error_summary,trigger_type,started_at,finished_at",
        "order": "started_at.desc",
        "limit": str(limit),
    }
    if site:
        params["site"] = f"eq.{site}"
    if run_id:
        params["id"] = f"eq.{run_id}"
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/scrape_runs",
        headers=_supabase_headers(),
        params=params,
        timeout=20,
    )
    res.raise_for_status()
    return {"items": res.json()}


def _tool_get_run_steps(args: dict[str, Any]) -> dict[str, Any]:
    _require_supabase()
    run_id = args.get("run_id")
    limit = int(args.get("limit", 50))
    params: dict[str, str] = {
        "select": "id,run_id,step_name,status,message,started_at,finished_at",
        "order": "started_at.desc",
        "limit": str(limit),
    }
    if run_id:
        params["run_id"] = f"eq.{run_id}"
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/scrape_run_steps",
        headers=_supabase_headers(),
        params=params,
        timeout=20,
    )
    res.raise_for_status()
    return {"items": res.json()}


def _tool_get_server_health(_: dict[str, Any]) -> dict[str, Any]:
    vm = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.2)
    chromes = 0
    runners = 0
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if "chrome" in name or "chromedriver" in name:
                chromes += 1
            if "apps/runner/main.py" in cmdline or "scrape_status.py" in cmdline:
                runners += 1
        except Exception:
            continue
    return {
        "cpu_percent": cpu,
        "memory_percent": vm.percent,
        "memory_used_mb": round(vm.used / 1024 / 1024, 1),
        "memory_total_mb": round(vm.total / 1024 / 1024, 1),
        "chrome_processes": chromes,
        "runner_processes": runners,
    }


def _tool_retry_failed_step(args: dict[str, Any]) -> dict[str, Any]:
    site = str(args.get("site", ""))
    if site not in ALLOWED_SITES:
        raise HTTPException(status_code=400, detail="retry_failed_step requires valid `site`")
    retried = _tool_run_scrape({"site": site, "max_pages": args.get("max_pages")})
    retried["note"] = "Current retry strategy reruns the site pipeline."
    return retried


TOOLS = {
    "run_scrape": _tool_run_scrape,
    "get_job_status": _tool_get_job_status,
    "get_run_status": _tool_get_run_status,
    "get_run_steps": _tool_get_run_steps,
    "get_server_health": _tool_get_server_health,
    "retry_failed_step": _tool_retry_failed_step,
}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    return {
        "tools": [
            {"name": "run_scrape", "description": "Start scraper run asynchronously", "input": ["site", "max_pages"]},
            {"name": "get_job_status", "description": "Get async job status", "input": ["job_id"]},
            {"name": "get_run_status", "description": "Fetch scrape_runs from Supabase", "input": ["site", "run_id", "limit"]},
            {"name": "get_run_steps", "description": "Fetch scrape_run_steps from Supabase", "input": ["run_id", "limit"]},
            {"name": "get_server_health", "description": "Check CPU/memory/process health", "input": []},
            {"name": "retry_failed_step", "description": "Retry by rerunning pipeline for site", "input": ["site", "max_pages"]},
        ]
    }


@app.post("/mcp/call")
def mcp_call(req: MCPCallRequest) -> dict[str, Any]:
    fn = TOOLS.get(req.name)
    if not fn:
        raise HTTPException(status_code=404, detail=f"tool not found: {req.name}")
    return {"tool": req.name, "result": fn(req.arguments)}
