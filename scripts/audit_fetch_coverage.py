import json
import os
import sys
import time
from collections import defaultdict
from typing import Any, Optional

import requests


SITE_DOMAINS = {
    "mercari": ["mercari.com", "jp.mercari.com"],
    "secondstreet": ["2ndstreet.jp", "www.2ndstreet.jp"],
    "surugaya": ["suruga-ya.jp", "www.suruga-ya.jp"],
    "yodobashi": ["yodobashi.com", "www.yodobashi.com"],
    "rakuma": ["fril.jp", "item.fril.jp"],
    "yafuoku": ["auctions.yahoo.co.jp", "page.auctions.yahoo.co.jp"],
    "yahoofleama": ["paypayfleamarket.yahoo.co.jp"],
    "kitamura": ["shop.kitamura.jp"],
    "hardoff": ["netmall.hardoff.co.jp"],
}

PAGE_SIZE = int(os.getenv("AUDIT_PAGE_SIZE", "100"))
MAX_RETRIES = int(os.getenv("AUDIT_MAX_RETRIES", "5"))
BACKOFF = float(os.getenv("AUDIT_BACKOFF_BASE", "1.5"))
PROGRESS_EVERY_PAGES = int(os.getenv("AUDIT_PROGRESS_EVERY_PAGES", "25"))


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _headers() -> dict[str, str]:
    key = _env("SUPABASE_SERVICE_ROLE_KEY") if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else _env("SUPABASE_KEY")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def _site_from_row(row: dict[str, Any]) -> Optional[str]:
    domain = (row.get("stocking_domain") or "").strip().lower()
    stocking_url = (row.get("stocking_url") or "").strip().lower()
    for site, domains in SITE_DOMAINS.items():
        if domain in domains:
            return site
    for site, domains in SITE_DOMAINS.items():
        if any(domain_part in stocking_url for domain_part in domains):
            return site
    return None


def _fetch_active_items() -> list[dict[str, Any]]:
    url = f"{_env('SUPABASE_URL').rstrip('/')}/rest/v1/items"
    all_rows: list[dict[str, Any]] = []
    last_item_id = None
    page_size = PAGE_SIZE
    page = 0
    while True:
        params = {
            "select": "ebay_item_id,stocking_url,stocking_domain,listing_status",
            "listing_status": "eq.Active",
            "order": "ebay_item_id.asc",
            "limit": str(page_size),
        }
        if last_item_id:
            params["ebay_item_id"] = f"gt.{last_item_id}"

        data = None
        for attempt in range(MAX_RETRIES):
            try:
                res = requests.get(url, headers=_headers(), params=params, timeout=60)
                if res.status_code >= 500:
                    if "57014" in res.text and page_size > 20:
                        page_size = max(20, page_size // 2)
                        params["limit"] = str(page_size)
                        print(
                            f"[audit] page_size reduced to {page_size} after 57014 at page={page + 1}",
                            file=sys.stderr,
                            flush=True,
                        )
                    preview = res.text[:300].replace("\n", " ")
                    raise requests.HTTPError(f"Supabase {res.status_code}: {preview}", response=res)
                res.raise_for_status()
                data = res.json()
                break
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                print(
                    f"[audit] retry page={page + 1} attempt={attempt + 1} page_size={page_size} error={exc}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(BACKOFF * (2 ** attempt))

        if not data:
            break
        all_rows.extend(data)
        last_item_id = data[-1]["ebay_item_id"]
        page += 1
        if page % PROGRESS_EVERY_PAGES == 0:
            print(
                f"[audit] pages={page} rows={len(all_rows)} last_item_id={last_item_id} page_size={page_size}",
                file=sys.stderr,
                flush=True,
            )
        if len(data) < page_size:
            break
    return all_rows


def main() -> int:
    rows = _fetch_active_items()
    report: dict[str, Any] = {
        "active_rows": len(rows),
        "sites": {},
        "unknown": {"count": 0, "examples": []},
    }
    site_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "total": 0,
        "fetchable": 0,
        "unfetchable": 0,
        "unfetchable_examples": [],
    })

    for row in rows:
        site = _site_from_row(row)
        domain = (row.get("stocking_domain") or "").strip().lower()
        if not site:
            report["unknown"]["count"] += 1
            if len(report["unknown"]["examples"]) < 20:
                report["unknown"]["examples"].append({
                    "ebay_item_id": row.get("ebay_item_id"),
                    "stocking_domain": domain,
                    "stocking_url": row.get("stocking_url"),
                })
            continue

        stats = site_stats[site]
        stats["total"] += 1
        if domain in SITE_DOMAINS[site]:
            stats["fetchable"] += 1
        else:
            stats["unfetchable"] += 1
            if len(stats["unfetchable_examples"]) < 20:
                stats["unfetchable_examples"].append({
                    "ebay_item_id": row.get("ebay_item_id"),
                    "stocking_domain": domain,
                    "stocking_url": row.get("stocking_url"),
                })

    for site in sorted(SITE_DOMAINS):
        report["sites"][site] = site_stats[site]

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
