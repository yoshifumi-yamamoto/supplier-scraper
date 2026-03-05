import os
import subprocess
from pathlib import Path

from scrapers.common.models import ScrapeStatus

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

    result = subprocess.run(
        ["python3", "main.py"],
        cwd=str(legacy_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    combined_output = f"{result.stdout}\n{result.stderr}".strip()

    if result.returncode != 0:
        return {
            "run_id": run_id,
            "site": "yahoofleama",
            "status": ScrapeStatus.ERROR.value,
            "message": "legacy pipeline failed (non-zero exit)",
        }

    if any(pattern in combined_output for pattern in FAIL_PATTERNS):
        return {
            "run_id": run_id,
            "site": "yahoofleama",
            "status": ScrapeStatus.ERROR.value,
            "message": "legacy pipeline failed (error pattern detected)",
        }

    return {
        "run_id": run_id,
        "site": "yahoofleama",
        "status": "success",
        "message": "legacy pipeline completed",
    }
