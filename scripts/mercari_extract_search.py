#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

CSV_HEADERS = [
    "タイトル",
    "価格",
    "画像",
    "CustomLabel",
    "アイテムスペック用",
    "ブランド",
    "サイズ",
    "出品者",
]
IMAGE_URL_RE = re.compile(r'https?://(?:static\.mercdn\.net/item/detail/orig/photos|assets\.mercari-shops-static\.com/-/large/plain)/[^"\'\s?]+(?:\.(?:jpg|jpeg|png|webp)|@jpg)')
PRICE_RE = re.compile(r'[¥￥]\s*([0-9][0-9,]*)')


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,2400")
    options.add_argument("user-agent=Mozilla/5.0")
    service = Service(os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def wait_ready(driver: webdriver.Chrome) -> None:
    WebDriverWait(driver, 60).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(2)


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def find_line_value(lines: list[str], label: str) -> str:
    try:
        idx = lines.index(label)
    except ValueError:
        return ""
    return lines[idx + 1] if idx + 1 < len(lines) else ""


def find_relative_time(lines: list[str]) -> str:
    for line in lines:
        if re.search(r"(分前|時間前|日前|週間前|か月前|年前)$", line):
            return line
    return ""


def normalize_price(text: str) -> str:
    return re.sub(r"[^0-9]", "", text or "")


def first_price(lines: Iterable[str], page_source: str = "") -> str:
    for line in lines:
        m = PRICE_RE.search(line)
        if m:
            return normalize_price(m.group(1))
    source = (page_source or "").replace('\\/', '/')
    m = PRICE_RE.search(source)
    if m:
        return normalize_price(m.group(1))
    return ""


def collect_image_urls(driver: webdriver.Chrome) -> str:
    seen: list[str] = []
    candidates: list[str] = []

    source = driver.page_source.replace('\\/', '/')
    candidates.extend(match.split("?")[0] for match in IMAGE_URL_RE.findall(source))

    for img in driver.find_elements(By.CSS_SELECTOR, '[data-testid^="imageThumbnail-"] img'):
        src = (img.get_attribute("src") or "").strip()
        if src and ("static.mercdn.net/item/detail/orig/photos/" in src or "assets.mercari-shops-static.com/-/large/plain/" in src):
            candidates.append(src.split("?")[0])

    for img in driver.find_elements(By.TAG_NAME, "img"):
        for attr in ("src", "data-src", "srcset"):
            raw = (img.get_attribute(attr) or "").strip()
            if not raw:
                continue
            for part in raw.split(","):
                url = part.strip().split(" ")[0]
                if "static.mercdn.net/item/detail/orig/photos/" in url or "assets.mercari-shops-static.com/-/large/plain/" in url:
                    candidates.append(url.split("?")[0])

    for url in candidates:
        if url and url not in seen:
            seen.append(url)
    return "\n".join(seen)


def extract_item_record(driver: webdriver.Chrome, url: str) -> dict[str, str]:
    driver.get(url)
    wait_ready(driver)

    body = driver.find_element(By.TAG_NAME, "body").text
    lines = clean_lines(body)

    title = ""
    try:
        title = driver.find_element(By.TAG_NAME, "h1").text.strip()
    except Exception:
        if len(lines) > 5:
            title = lines[5]

    price = first_price(lines, driver.page_source)
    description = ""
    if "商品の説明" in lines:
        start = lines.index("商品の説明") + 1
        end = lines.index("商品の情報") if "商品の情報" in lines else len(lines)
        description = "\n".join(lines[start:end]).strip()

    relative_time = find_relative_time(lines)
    item_spec = description
    if relative_time:
        item_spec = f"{description}\n\n{relative_time}".strip()

    brand = find_line_value(lines, "ブランド")
    size = find_line_value(lines, "商品のサイズ")
    seller = find_line_value(lines, "出品者") or find_line_value(lines, "ショップ情報")

    return {
        "タイトル": title,
        "価格": price,
        "画像": collect_image_urls(driver),
        "CustomLabel": url,
        "アイテムスペック用": item_spec,
        "ブランド": brand,
        "サイズ": size,
        "出品者": seller,
    }


def extract_page_token(url: str) -> str | None:
    parsed = urlparse(url)
    return parse_qs(parsed.query).get("page_token", [None])[0]


def build_next_url(current_url: str, next_token: str) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    qs["page_token"] = [next_token]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs, doseq=True), parsed.fragment))


def collect_search_page_links(driver: webdriver.Chrome, current_url: str) -> tuple[list[str], str | None]:
    wait_ready(driver)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    anchors = driver.find_elements(By.TAG_NAME, "a")
    item_urls: list[str] = []
    next_token: str | None = None
    current_token = extract_page_token(current_url)

    for anchor in anchors:
        href = (anchor.get_attribute("href") or "").strip()
        if not href:
            continue
        if "/item/" in href or "/shops/product/" in href:
            if href not in item_urls:
                item_urls.append(href)
            continue
        token = extract_page_token(href)
        if token and token != current_token:
            next_token = token

    next_url = build_next_url(current_url, next_token) if next_token else None
    return item_urls, next_url


def write_progress(path: str | None, payload: dict) -> None:
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_csv_writer(path: str):
    fp = open(path, "w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(fp, fieldnames=CSV_HEADERS)
    writer.writeheader()
    fp.flush()
    return fp, writer


def append_record(fp, writer, record: dict[str, str]) -> None:
    writer.writerow(record)
    fp.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Mercari search results into CSV.")
    parser.add_argument("--search-url", required=True, help="Mercari search result URL")
    parser.add_argument("--output", required=True, help="CSV output path")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum search pages to crawl (0 = unlimited)")
    parser.add_argument("--max-items", type=int, default=400, help="Maximum number of items to extract")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--progress", default="", help="Progress JSON path")
    parser.add_argument("--restart-pages", type=int, default=10, help="Restart browser every N pages to avoid renderer timeout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    progress_path = args.progress or None

    driver = build_driver(headless=args.headless)
    csv_fp, csv_writer = open_csv_writer(args.output)
    seen_urls: set[str] = set()
    records: list[dict[str, str]] = []
    skip_count = 0
    current_url = args.search_url
    page = 0

    write_progress(progress_path, {
        "status": "running",
        "page": 0,
        "extracted_count": 0,
        "skip_count": 0,
        "seen_count": 0,
        "max_items": args.max_items,
        "max_pages": args.max_pages,
        "next_url": args.search_url,
        "message": "starting",
    })

    try:
        while current_url and (args.max_pages <= 0 or page < args.max_pages):
            if args.max_items and len(records) >= args.max_items:
                break

            if page > 0 and args.restart_pages > 0 and page % args.restart_pages == 0:
                driver.quit()
                driver = build_driver(headless=args.headless)

            page += 1
            driver.get(current_url)
            item_urls, next_url = collect_search_page_links(driver, current_url)
            page_ok = 0
            page_skip = 0
            print(f"[page] {page} links={len(item_urls)} next={'yes' if next_url else 'no'} extracted={len(records)} skipped={skip_count}", file=sys.stderr)
            write_progress(progress_path, {
                "status": "running",
                "page": page,
                "extracted_count": len(records),
                "skip_count": skip_count,
                "seen_count": len(seen_urls),
                "max_items": args.max_items,
                "max_pages": args.max_pages,
                "next_url": current_url,
                "message": f"page {page} loaded",
            })
            if not item_urls:
                break

            for item_url in item_urls:
                if args.max_items and len(records) >= args.max_items:
                    current_url = None
                    break
                if item_url in seen_urls:
                    continue
                seen_urls.add(item_url)
                try:
                    record = extract_item_record(driver, item_url)
                    records.append(record)
                    append_record(csv_fp, csv_writer, record)
                    page_ok += 1
                    print(f"[ok] {item_url}", file=sys.stderr)
                except Exception as exc:  # noqa: BLE001
                    skip_count += 1
                    page_skip += 1
                    print(f"[skip] {item_url}: {exc}", file=sys.stderr)
                write_progress(progress_path, {
                    "status": "running",
                    "page": page,
                    "extracted_count": len(records),
                    "skip_count": skip_count,
                    "seen_count": len(seen_urls),
                    "page_ok": page_ok,
                    "page_skip": page_skip,
                    "max_items": args.max_items,
                    "max_pages": args.max_pages,
                    "next_url": current_url,
                    "message": f"page {page} processing",
                })

            print(f"[page-summary] page={page} ok={page_ok} skip={page_skip} total={len(records)}", file=sys.stderr)
            if args.max_items and len(records) >= args.max_items:
                break
            current_url = next_url

        write_progress(progress_path, {
            "status": "completed",
            "page": page,
            "extracted_count": len(records),
            "skip_count": skip_count,
            "seen_count": len(seen_urls),
            "max_items": args.max_items,
            "max_pages": args.max_pages,
            "next_url": None,
            "message": f"completed with {len(records)} rows",
        })
    except KeyboardInterrupt:
        write_progress(progress_path, {
            "status": "cancelled",
            "page": page,
            "extracted_count": len(records),
            "skip_count": skip_count,
            "seen_count": len(seen_urls),
            "max_items": args.max_items,
            "max_pages": args.max_pages,
            "next_url": current_url,
            "message": f"cancelled with {len(records)} rows",
        })
        print(f"cancelled after {len(records)} rows", file=sys.stderr)
        return 130
    except Exception as exc:
        write_progress(progress_path, {
            "status": "failed",
            "page": locals().get("page", 0),
            "extracted_count": len(records),
            "skip_count": skip_count,
            "seen_count": len(seen_urls),
            "max_items": args.max_items,
            "max_pages": args.max_pages,
            "next_url": locals().get("current_url", args.search_url),
            "message": str(exc),
        })
        raise
    finally:
        csv_fp.close()
        driver.quit()

    print(f"wrote {len(records)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
