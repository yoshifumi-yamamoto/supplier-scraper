import os
import subprocess
from pathlib import Path
from typing import Iterable

from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step

DEFAULT_FAIL_PATTERNS = (
    "エラーが発生しました",
    "処理中にエラー発生",
    "Traceback (most recent call last)",
    "FileNotFoundError",
    "Server Error",
)


def run_legacy_pipeline(
    *,
    run_id: str,
    site: str,
    scripts: Iterable[str],
    fail_patterns: tuple[str, ...] = DEFAULT_FAIL_PATTERNS,
) -> dict:
    base_dir = Path(__file__).resolve().parents[2]
    legacy_dir = base_dir / "legacy" / site
    env = os.environ.copy()
    env["RUN_ID"] = run_id

    if not legacy_dir.exists():
        return {
            "run_id": run_id,
            "site": site,
            "status": ScrapeStatus.ERROR.value,
            "message": f"legacy dir not found: {legacy_dir}",
        }

    for script in scripts:
        script_path = legacy_dir / script
        step_id = start_step(run_id=run_id, step_name=script)
        if not script_path.exists():
            # Some sites do not have upload script in legacy implementation.
            finish_step(step_id, status="success", message=f"skipped: {script} not found")
            continue
        result = subprocess.run(
            ["python3", script],
            cwd=str(legacy_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            # In no-data runs, upload step may fail because summarized folder does not exist.
            if (
                script == "upload_to_supabase.py"
                and (
                    "summarized フォルダが見つかりません" in combined_output
                    or "summarized folder not found" in combined_output.lower()
                )
            ):
                finish_step(step_id, status="success", message="skipped: no summarized output")
                continue
            detail = (combined_output[:400] or "non-zero exit").replace("\n", " | ")
            finish_step(step_id, status="failed", message=detail)
            return {
                "run_id": run_id,
                "site": site,
                "status": ScrapeStatus.ERROR.value,
                "message": f"{script} failed (non-zero exit): {detail}",
            }
        if any(pattern in combined_output for pattern in fail_patterns):
            detail = (combined_output[:400] or "error pattern detected").replace("\n", " | ")
            finish_step(step_id, status="failed", message=detail)
            return {
                "run_id": run_id,
                "site": site,
                "status": ScrapeStatus.ERROR.value,
                "message": f"{script} failed (error pattern): {detail}",
            }
        finish_step(step_id, status="success")

    return {
        "run_id": run_id,
        "site": site,
        "status": "success",
        "message": "legacy pipeline completed",
    }
