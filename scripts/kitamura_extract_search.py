#!/usr/bin/env python3
import argparse
import csv
import html
import json
import os
import re
import sys
import time
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
PRICE_RE = re.compile(r'([0-9][0-9,]*)円')
IMAGE_RE = re.compile(r'https?://[^"\'\s>]+(?:jpg|jpeg|png|webp)')


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


def write_progress(path: str | None, payload: dict) -> None:
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_csv_writer(path: str):
    fp = open(path, 'w', encoding='utf-8-sig', newline='')
    writer = csv.DictWriter(fp, fieldnames=CSV_HEADERS)
    writer.writeheader()
    fp.flush()
    return fp, writer


def append_record(fp, writer, record: dict[str, str]) -> None:
    writer.writerow(record)
    fp.flush()


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalize_price(text: str) -> str:
    return re.sub(r"[^0-9]", "", text or "")


def first_price(lines: list[str], source: str) -> str:
    for line in lines:
        m = PRICE_RE.search(line)
        if m:
            return normalize_price(m.group(1))
    m = PRICE_RE.search(source)
    if m:
        return normalize_price(m.group(1))
    return ""


def collect_image_urls(driver: webdriver.Chrome) -> str:
    seen: list[str] = []
    candidates: list[str] = []
    allowed_hosts = ('shopimg.kitamura.jp', 'nc-img.kitamura.jp')
    selectors = [
        '.product-image-main-img',
        '.product-image-thumbnail-list img.product-image-thumbnail-img',
        'img.product-image-thumbnail-img',
    ]
    for selector in selectors:
        for img in driver.find_elements(By.CSS_SELECTOR, selector):
            raw = (img.get_attribute('src') or img.get_attribute('data-src') or '').strip()
            if not raw:
                continue
            if raw.startswith('//'):
                raw = f'https:{raw}'
            if not any(host in raw for host in allowed_hosts):
                continue
            candidates.append(raw)
    if not candidates:
        source = driver.page_source.replace('\/', '/')
        for url in IMAGE_RE.findall(source):
            if any(host in url for host in allowed_hosts):
                candidates.append(url)
    for url in candidates:
        if not url:
            continue
        clean = url.split('?')[0]
        if clean not in seen:
            seen.append(clean)
    return "\n".join(seen)


def build_next_url(current_url: str, page_num: int) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    qs['page'] = [str(page_num)]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs, doseq=True), parsed.fragment))


def collect_listing_entries(driver: webdriver.Chrome) -> tuple[list[dict[str, str]], str | None]:
    wait_ready(driver)
    body = driver.find_element(By.TAG_NAME, 'body').text
    m = re.search(r'(\d+)件中(\d+)-(\d+)の結果', body)
    next_url = None
    if m:
        total = int(m.group(1))
        end = int(m.group(3))
        if end < total:
            parsed = urlparse(driver.current_url)
            page = int(parse_qs(parsed.query).get('page', ['1'])[0])
            next_url = build_next_url(driver.current_url, page + 1)

    anchors = driver.find_elements(By.TAG_NAME, 'a')
    pd_map: dict[str, dict[str, str]] = {}
    used_map: dict[str, dict[str, str]] = {}

    for anchor in anchors:
        href = (anchor.get_attribute('href') or '').strip()
        text = (anchor.text or '').strip().replace('\n', ' ')
        if not href.startswith('https://shop.kitamura.jp/ec/'):
            continue
        if '/ec/pd/' in href:
            code = href.rstrip('/').split('/ec/pd/')[-1].split('#')[0]
            if code and code not in pd_map:
                pd_map[code] = {'url': href.split('#')[0], 'kind': 'pd', 'text': text}
        elif '/ec/list?' in href and 'keyword3=' in href and 'type=u' in href:
            qs = parse_qs(urlparse(href).query)
            code = (qs.get('keyword3') or [''])[0]
            if code and code not in used_map:
                used_map[code] = {'url': href.split('#')[0], 'kind': 'used_list', 'text': text}

    entries: list[dict[str, str]] = []
    for code, row in pd_map.items():
        entry = {'product_code': code, **row}
        if code in used_map:
            entry['used_list_url'] = used_map[code]['url']
        entries.append(entry)
    for code, row in used_map.items():
        if code not in pd_map:
            entries.append({'product_code': code, **row})
    return entries, next_url


def _used_detail_from_list(driver: webdriver.Chrome, list_url: str) -> tuple[str, str] | None:
    driver.get(list_url)
    wait_ready(driver)
    links: list[str] = []
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        if '/ec/used/' in href and href not in links:
            links.append(href.split('#')[0])
    if links:
        return links[0], 'used'
    return None


def resolve_target_url(driver: webdriver.Chrome, entry: dict[str, str]) -> tuple[str, str] | None:
    entry_url = entry['url']
    if 'type=u' in entry_url:
        return _used_detail_from_list(driver, entry_url)
    driver.get(entry_url)
    wait_ready(driver)
    source = driver.page_source.replace('\/', '/')
    sold_out = ('SoldOut' in source) or ('availability": "https://schema.org/SoldOut' in source)
    if sold_out:
        return None
    return entry_url, 'pd'


def find_line_value(lines: list[str], label: str) -> str:
    try:
        idx = lines.index(label)
    except ValueError:
        return ''
    return lines[idx + 1] if idx + 1 < len(lines) else ''


def extract_record(driver: webdriver.Chrome, entry: dict[str, str]) -> dict[str, str]:
    resolved = resolve_target_url(driver, entry)
    if not resolved:
        raise RuntimeError('sold out')
    target_url, resolved_kind = resolved
    driver.get(target_url)
    wait_ready(driver)
    source = driver.page_source.replace('\\/', '/')
    lines = clean_lines(driver.find_element(By.TAG_NAME, 'body').text)

    title = ''
    try:
        title = driver.find_element(By.TAG_NAME, 'h1').text.strip()
    except Exception:
        title = lines[0] if lines else ''

    price = first_price(lines, source)
    description = ''
    if '商品説明' in lines:
        start = lines.index('商品説明') + 1
        end = lines.index('動画・記事') if '動画・記事' in lines else len(lines)
        description = '\n'.join(lines[start:end]).strip()
    if not description:
        m = re.search(r'\"description\"\s*:\s*\"(.*?)\"', source)
        if m:
            raw_desc = html.unescape(m.group(1))
            raw_desc = raw_desc.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
            description = re.sub(r'<[^>]+>', '', raw_desc).strip()

    spec_parts = []
    if description:
        spec_parts.append(description)
    for label in ('備考', '付属品'):
        val = find_line_value(lines, label)
        if val:
            spec_parts.append(f'{label}: {val}')
    description = '\n\n'.join(part for part in spec_parts if part).strip()

    brand = find_line_value(lines, 'メーカー') or (title.split(' ')[0] if title else '')
    seller = find_line_value(lines, '取扱店舗') or 'カメラのキタムラ'

    return {
        'タイトル': title,
        '価格': price,
        '画像': collect_image_urls(driver),
        'CustomLabel': target_url,
        'アイテムスペック用': description,
        'ブランド': brand,
        'サイズ': '',
        '出品者': seller,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Extract Kitamura listing results into CSV.')
    parser.add_argument('--search-url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-pages', type=int, default=0)
    parser.add_argument('--max-items', type=int, default=400)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--progress', default='')
    parser.add_argument('--restart-pages', type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    progress_path = args.progress or None
    driver = build_driver(headless=args.headless)
    csv_fp, csv_writer = open_csv_writer(args.output)
    seen_codes: set[str] = set()
    records: list[dict[str, str]] = []
    skip_count = 0
    current_url = args.search_url
    page = 0

    write_progress(progress_path, {'status': 'running', 'page': 0, 'extracted_count': 0, 'skip_count': 0, 'seen_count': 0, 'max_items': args.max_items, 'max_pages': args.max_pages, 'next_url': current_url, 'message': 'starting'})
    try:
        while current_url and (args.max_pages <= 0 or page < args.max_pages):
            if args.max_items and len(records) >= args.max_items:
                break
            if page > 0 and args.restart_pages > 0 and page % args.restart_pages == 0:
                driver.quit()
                driver = build_driver(headless=args.headless)
            page += 1
            driver.get(current_url)
            entries, next_url = collect_listing_entries(driver)
            page_ok = 0
            page_skip = 0
            print(f"[page] {page} entries={len(entries)} next={'yes' if next_url else 'no'} extracted={len(records)} skipped={skip_count}", file=sys.stderr)
            if not entries:
                break
            for entry in entries:
                if args.max_items and len(records) >= args.max_items:
                    current_url = None
                    break
                code = entry.get('product_code') or entry['url']
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                try:
                    record = extract_record(driver, entry)
                    records.append(record)
                    append_record(csv_fp, csv_writer, record)
                    page_ok += 1
                    print(f"[ok] {entry['url']}", file=sys.stderr)
                except Exception as exc:
                    skip_count += 1
                    page_skip += 1
                    print(f"[skip] {entry['url']}: {exc}", file=sys.stderr)
                write_progress(progress_path, {'status': 'running', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'seen_count': len(seen_codes), 'page_ok': page_ok, 'page_skip': page_skip, 'max_items': args.max_items, 'max_pages': args.max_pages, 'next_url': current_url, 'message': f'page {page} processing'})
            print(f"[page-summary] page={page} ok={page_ok} skip={page_skip} total={len(records)}", file=sys.stderr)
            current_url = next_url

        write_progress(progress_path, {'status': 'completed', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'seen_count': len(seen_codes), 'max_items': args.max_items, 'max_pages': args.max_pages, 'next_url': None, 'message': f'completed with {len(records)} rows'})
    except KeyboardInterrupt:
        write_progress(progress_path, {'status': 'cancelled', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'seen_count': len(seen_codes), 'max_items': args.max_items, 'max_pages': args.max_pages, 'next_url': current_url, 'message': f'cancelled with {len(records)} rows'})
        print(f'cancelled after {len(records)} rows', file=sys.stderr)
        return 130
    except Exception as exc:
        write_progress(progress_path, {'status': 'failed', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'seen_count': len(seen_codes), 'max_items': args.max_items, 'max_pages': args.max_pages, 'next_url': current_url, 'message': str(exc)})
        raise
    finally:
        csv_fp.close()
        driver.quit()

    print(f'wrote {len(records)} rows to {args.output}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
