import argparse
import os
import uuid

from scrapers.common.execution_guard import (
    LockBusyError,
    acquire_run_lock,
    cleanup_site_processes,
    release_run_lock,
)
from scrapers.common.logging_utils import json_log
from scrapers.common.notifier import build_failure_message, notify_chatwork
from scrapers.common.run_store import create_run, finish_run
from scrapers.sites.secondstreet.adapter import run_pipeline as run_secondstreet
from scrapers.sites.yahoofleama.adapter import run_pipeline as run_yahoofleama


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified supplier scraper runner")
    parser.add_argument(
        "--site",
        required=True,
        choices=["yahoofleama", "secondstreet"],
        help="target site",
    )
    args = parser.parse_args()

    lock = None
    run_id = os.getenv("RUN_ID") or str(uuid.uuid4())
    try:
        lock = acquire_run_lock(args.site)
    except LockBusyError as exc:
        msg = str(exc)
        json_log("warning", "skip run: lock busy", site=args.site, error=msg)
        notify_chatwork(build_failure_message(site=args.site, run_id=run_id, error=f"lock busy: {msg}"))
        return 2

    json_log("info", "run started", run_id=run_id, site=args.site)
    try:
        create_run(run_id=run_id, site=args.site, trigger_type="manual")
    except Exception as exc:  # noqa: BLE001
        json_log("warning", "create_run failed, continue run", run_id=run_id, site=args.site, error=str(exc))

    try:
        cleanup_site_processes(args.site)
        if args.site == "yahoofleama":
            result = run_yahoofleama(run_id)
        elif args.site == "secondstreet":
            result = run_secondstreet(run_id)
        else:
            raise ValueError(f"Unsupported site: {args.site}")

        result_message = result.pop("message", None)
        if result_message:
            json_log("info", result_message, **result)
        else:
            json_log("info", "run finished", **result)

        status = "success" if result.get("status") != "error" else "failed"
        try:
            finish_run(run_id=run_id, status=status, error_summary=None if status == "success" else result_message)
        except Exception as exc:  # noqa: BLE001
            json_log("warning", "finish_run failed", run_id=run_id, site=args.site, error=str(exc))
        if status != "success":
            notify_chatwork(
                build_failure_message(
                    site=args.site,
                    run_id=run_id,
                    error=result_message or "pipeline returned error status",
                )
            )
        cleanup_site_processes(args.site)
        return 0 if status == "success" else 1
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        json_log("error", "run failed", run_id=run_id, site=args.site, error=msg)
        notify_chatwork(build_failure_message(site=args.site, run_id=run_id, error=msg))
        try:
            finish_run(run_id=run_id, status="failed", error_summary=msg)
        except Exception as finish_exc:  # noqa: BLE001
            json_log("warning", "finish_run failed", run_id=run_id, site=args.site, error=str(finish_exc))
        cleanup_site_processes(args.site)
        return 1
    finally:
        release_run_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
