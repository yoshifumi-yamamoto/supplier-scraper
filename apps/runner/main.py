import argparse
import uuid

from scrapers.common.logging_utils import json_log
from scrapers.common.run_store import create_run, finish_run
from scrapers.sites.yahoofleama.adapter import run_pipeline as run_yahoofleama


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified supplier scraper runner")
    parser.add_argument("--site", required=True, choices=["yahoofleama"], help="target site")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    json_log("info", "run started", run_id=run_id, site=args.site)
    create_run(run_id=run_id, site=args.site, trigger_type="manual")

    try:
        if args.site == "yahoofleama":
            result = run_yahoofleama(run_id)
        else:
            raise ValueError(f"Unsupported site: {args.site}")

        result_message = result.pop("message", None)
        if result_message:
            json_log("info", result_message, **result)
        else:
            json_log("info", "run finished", **result)

        status = "success" if result.get("status") != "error" else "failed"
        finish_run(run_id=run_id, status=status, error_summary=None if status == "success" else result_message)
        return 0 if status == "success" else 1
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        json_log("error", "run failed", run_id=run_id, site=args.site, error=msg)
        finish_run(run_id=run_id, status="failed", error_summary=msg)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
