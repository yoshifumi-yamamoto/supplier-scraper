#!/usr/bin/env python3
import argparse
import csv
import html
import json
import os
import re
import sys
import time
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

CSV_HEADERS = ["タイトル", "価格", "画像", "CustomLabel", "アイテムスペック用", "ブランド", "サイズ", "出品者"]
PRICE_RE = re.compile(r"'price'\s*:\s*([0-9]+)|販売価格[^0-9]*([0-9,]+)円")


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1600,2400')
    options.add_argument('user-agent=Mozilla/5.0')
    service = Service(os.getenv('CHROMEDRIVER_PATH', '/usr/local/bin/chromedriver'))
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def wait_ready(driver: webdriver.Chrome) -> None:
    WebDriverWait(driver, 60).until(lambda d: d.execute_script('return document.readyState') in ('interactive', 'complete'))
    time.sleep(2)


def write_progress(path: str | None, payload: dict) -> None:
    if not path:
        return
    try:
        with open(path, 'w', encoding='utf-8') as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clean_text(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalize_price(text: str) -> str:
    return re.sub(r'[^0-9]', '', text or '')


def extract_price(page_source: str, lines: list[str]) -> str:
    for line in lines:
        if 'タイムセール' in line:
            continue
        m = re.search(r'([0-9,]+)円', line)
        if m:
            return normalize_price(m.group(1))
    m = PRICE_RE.search(page_source)
    if m:
        return normalize_price(next(g for g in m.groups() if g))
    return ''


def _normalize_image_url(url: str) -> tuple[str, str]:
    raw = (url or '').strip()
    if raw.startswith('//'):
        raw = 'https:' + raw
    if raw.startswith('/'):
        raw = 'https://www.suruga-ya.jp' + raw
    raw = raw.replace('\/', '/')
    key = raw.split('?')[0]
    return raw, key


def collect_images(driver: webdriver.Chrome) -> str:
    selectors = [
        '.product_zoom .easyzoom a.show-lightbox.main-pro-lightbox',
        '.product_zoom .show-lightbox-main',
        '.product_zoom .zoom_product_thumnail .swiper-wrapper a[data-fancybox="gallery"]',
        '#itemImg_m .zoom-small-image a.show-lightbox',
        '#itemImg_m .slider2-thumbnail img.item-image',
        '#itemImg_m a[data-fancybox="gallery"]',
    ]
    urls: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, selector):
            candidates = []
            for attr in ('zoom-photo-url', 'data-standard', 'href', 'src'):
                value = (el.get_attribute(attr) or '').strip()
                if value:
                    candidates.append(value)
            for value in candidates:
                raw, key = _normalize_image_url(value)
                if not key:
                    continue
                if 'suruga-ya.jp' not in key:
                    continue
                if '/database/images/no_photo' in key:
                    continue
                if not any(part in key for part in ('/database/pics', '/pics_webp/', '/pics/')):
                    continue
                if key in seen:
                    continue
                seen.add(key)
                urls.append(raw)
    return '\n'.join(urls)


def next_search_url(driver: webdriver.Chrome) -> str | None:
    try:
        link = driver.find_element(By.CSS_SELECTOR, 'link[rel="next"]')
        href = (link.get_attribute('href') or '').strip()
        return href or None
    except Exception:
        return None


def collect_search_entries(driver: webdriver.Chrome, current_url: str) -> tuple[list[str], str | None]:
    driver.get(current_url)
    wait_ready(driver)
    links = []
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        if not href:
            continue
        full = urljoin(current_url, href)
        if '/product/detail/' in full or '/product/other/' in full:
            if full not in links:
                links.append(full.split('#')[0])
    return links, next_search_url(driver)


def resolve_surugaya_url(driver: webdriver.Chrome, url: str) -> str | None:
    if '/product/other/' not in url:
        return url
    driver.get(url)
    wait_ready(driver)
    choices = []
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        if not href:
            continue
        full = urljoin(url, href).replace('&amp;', '&')
        if '/product/detail/' in full and 'tenpo_cd=' in full and full not in choices:
            choices.append(full.split('#')[0])
    if choices:
        return choices[0]
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').strip()
        full = urljoin(url, href).replace('&amp;', '&')
        if '/product/detail/' in full:
            return full.split('#')[0]
    return None


def extract_record(driver: webdriver.Chrome, url: str) -> dict[str, str]:
    target_url = resolve_surugaya_url(driver, url)
    if not target_url:
        raise RuntimeError('detail_not_found')
    driver.get(target_url)
    wait_ready(driver)
    source = driver.page_source.replace('\\/', '/')
    lines = clean_text(driver.find_element(By.TAG_NAME, 'body').text)

    title = ''
    m = re.search(r"item_name': htmlDecode\('(.*?)'\)", source)
    if m:
        title = html.unescape(m.group(1))
    if not title:
        m = re.search(r'<title>駿河屋 -(?:<中古>|<新品>)?(.*?)（', source)
        if m:
            title = html.unescape(m.group(1)).strip()
    if not title and lines:
        title = lines[0]

    price = extract_price(source, lines)

    desc = ''
    m = re.search(r'<meta name="Description" content="(.*?)">', source)
    if m:
        desc = html.unescape(m.group(1)).strip()
    if not desc:
        for idx, line in enumerate(lines):
            if '商品解説' in line:
                desc = '\n'.join(lines[idx:idx+8]).strip()
                break

    brand = ''
    if title:
        brand = title.split(' ')[0]
    seller = '駿河屋'
    m = re.search(r"'affiliation': htmlDecode\('(.*?)'\)", source)
    if m:
        seller = html.unescape(m.group(1)).strip() or seller

    return {
        'タイトル': title,
        '価格': price,
        '画像': collect_images(driver),
        'CustomLabel': target_url,
        'アイテムスペック用': desc,
        'ブランド': brand,
        'サイズ': '',
        '出品者': seller,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Extract Surugaya search results into CSV.')
    p.add_argument('--search-url', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--max-items', type=int, default=400)
    p.add_argument('--headless', action='store_true')
    p.add_argument('--progress', default='')
    p.add_argument('--restart-pages', type=int, default=10)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    progress_path = args.progress or None
    driver = build_driver(args.headless)
    current_url = args.search_url
    page = 0
    seen = set()
    records = []
    skip_count = 0
    write_progress(progress_path, {'status': 'running', 'page': 0, 'extracted_count': 0, 'skip_count': 0, 'message': 'starting'})
    try:
        while current_url and (args.max_pages <= 0 or page < args.max_pages):
            if args.max_items and len(records) >= args.max_items:
                break
            if page > 0 and args.restart_pages > 0 and page % args.restart_pages == 0:
                driver.quit()
                driver = build_driver(args.headless)
            page += 1
            urls, next_url = collect_search_entries(driver, current_url)
            print(f'[page] {page} links={len(urls)} next={"yes" if next_url else "no"}', file=sys.stderr)
            for url in urls:
                if args.max_items and len(records) >= args.max_items:
                    break
                if url in seen:
                    continue
                seen.add(url)
                try:
                    records.append(extract_record(driver, url))
                except Exception as exc:
                    skip_count += 1
                    print(f'[skip] {url} reason={exc}', file=sys.stderr)
                write_progress(progress_path, {'status': 'running', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'message': current_url})
            current_url = next_url
        with open(args.output, 'w', encoding='utf-8', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(records)
        write_progress(progress_path, {'status': 'completed', 'page': page, 'extracted_count': len(records), 'skip_count': skip_count, 'output': args.output})
        print(f'wrote {len(records)} rows to {args.output}', file=sys.stderr)
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
