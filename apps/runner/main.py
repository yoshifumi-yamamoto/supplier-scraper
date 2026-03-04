import argparse
import uuid

from scrapers.common.logging_utils import json_log
from scrapers.sites.yahoofleama.adapter import run_pipeline as run_yahoofleama


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified supplier scraper runner")
    parser.add_argument("--site", required=True, choices=["yahoofleama"], help="target site")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    json_log("info", "run started", run_id=run_id, site=args.site)

    if args.site == "yahoofleama":
        result = run_yahoofleama(run_id)
    else:
        raise ValueError(f"Unsupported site: {args.site}")

    result_message = result.pop("message", None)
    if result_message:
        json_log("info", result_message, **result)
    else:
        json_log("info", "run finished", **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
