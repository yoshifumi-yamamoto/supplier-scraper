from scrapers.common.models import ScrapeStatus


def run_pipeline(run_id: str) -> dict:
    # TODO: 既存 yahoofleama ロジックを段階移植する
    return {
        "run_id": run_id,
        "site": "yahoofleama",
        "status": ScrapeStatus.UNKNOWN.value,
        "message": "adapter scaffold only",
    }
