from scrapers.common.legacy_pipeline import run_legacy_pipeline


def run_pipeline(run_id: str) -> dict:
    return run_legacy_pipeline(
        run_id=run_id,
        site="yafuoku",
        scripts=[
            "fetch_urls.py",
            "split_urls.py",
            "scrape_status.py",
            "summarize_results.py",
            "upload_to_supabase.py",
            "delete_temp_data.py",
        ],
    )
