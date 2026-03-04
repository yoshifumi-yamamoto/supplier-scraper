import os
import subprocess
from pathlib import Path

from scrapers.common.models import ScrapeStatus


def run_pipeline(run_id: str) -> dict:
    base_dir = Path(__file__).resolve().parents[3]
    legacy_dir = base_dir / "legacy" / "yahoofleama"
    env = os.environ.copy()
    env["RUN_ID"] = run_id

    if not legacy_dir.exists():
        return {
            "run_id": run_id,
            "site": "yahoofleama",
            "status": ScrapeStatus.ERROR.value,
            "message": f"legacy dir not found: {legacy_dir}",
        }

    result = subprocess.run(["python3", "main.py"], cwd=str(legacy_dir), env=env)
    if result.returncode != 0:
        return {
            "run_id": run_id,
            "site": "yahoofleama",
            "status": ScrapeStatus.ERROR.value,
            "message": "legacy pipeline failed",
        }

    return {
        "run_id": run_id,
        "site": "yahoofleama",
        "status": ScrapeStatus.UNKNOWN.value,
        "message": "legacy pipeline completed",
    }
