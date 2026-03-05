import os
import subprocess
from pathlib import Path

from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step

FAIL_PATTERNS = (
    "エラーが発生しました",
    "処理中にエラー発生",
    "Traceback (most recent call last)",
    "FileNotFoundError",
    "Server Error",
)


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

    scripts = [
        "fetch_urls.py",
        "split_urls.py",
        "scrape_status.py",
        "summarize_results.py",
        "upload_to_supabase.py",
        "delete_temp_data.py",
    ]
    for script in scripts:
        step_id = start_step(run_id=run_id, step_name=script)
        result = subprocess.run(
            ["python3", script],
            cwd=str(legacy_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            detail = (combined_output[:400] or "non-zero exit").replace("\n", " | ")
            finish_step(step_id, status="failed", message=detail)
            return {
                "run_id": run_id,
                "site": "yahoofleama",
                "status": ScrapeStatus.ERROR.value,
                "message": f"{script} failed (non-zero exit): {detail}",
            }
        if any(pattern in combined_output for pattern in FAIL_PATTERNS):
            detail = (combined_output[:400] or "error pattern detected").replace("\n", " | ")
            finish_step(step_id, status="failed", message=detail)
            return {
                "run_id": run_id,
                "site": "yahoofleama",
                "status": ScrapeStatus.ERROR.value,
                "message": f"{script} failed (error pattern): {detail}",
            }
        finish_step(step_id, status="success")

    return {
        "run_id": run_id,
        "site": "yahoofleama",
        "status": "success",
        "message": "legacy pipeline completed",
    }
