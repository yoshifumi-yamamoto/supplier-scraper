#!/usr/bin/env python3
import argparse
import csv
import os
import re
import time
from urllib.parse import parse_qs, unquote_plus, urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CSV_HEADERS = [
    "タイトル",
    "価格",
    "送料",
    "画像",
    "CustomLabel",
    "アイテムスペック用",
    "ブランド",
    "サイズ",
    "出品者",
]

DETAIL_URL_PATTERNS = (
    "auctions.yahoo.co.jp/jp/auction/",
    "paypayfleamarket.yahoo.co.jp/item/",
)

SECTION_STOP_WORDS = (
    "支払い方法",
    "商品情報",
    "その他の情報",
    "商品説明",
    "商品の状態",
    "個数",
    "配送方法",
    "配送方法一覧",
    "発送元の地域",
    "発送までの日数",
)


def setup_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,2200")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )
    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def normalize_whitespace(value):
    if value is None:
        return ""
    return re.sub(r"[ \t\u3000]+", " ", str(value)).strip()


def normalize_multiline(value):
    if value is None:
        return ""
    lines = [normalize_whitespace(line) for line in str(value).splitlines()]
    return "\n".join(line for line in lines if line)


def first_text(driver, xpaths):
    for xpath in xpaths:
        try:
            element = driver.find_element(By.XPATH, xpath)
            text = normalize_multiline(element.text)
            if text:
                return text
        except Exception:
            continue
    return ""


def first_attr(driver, xpaths, attr):
    for xpath in xpaths:
        try:
            element = driver.find_element(By.XPATH, xpath)
            value = normalize_whitespace(element.get_attribute(attr))
            if value:
                return value
        except Exception:
            continue
    return ""


def extract_section_text(page_text, label):
    if not page_text:
        return ""

    lines = [normalize_whitespace(line) for line in page_text.splitlines()]
    lines = [line for line in lines if line]

    for index, line in enumerate(lines):
        if line != label:
            continue

        collected = []
        for candidate in lines[index + 1 : index + 8]:
            if candidate in SECTION_STOP_WORDS:
                break
            if candidate == label:
                break
            collected.append(candidate)

        result = "\n".join(collected).strip()
        if result:
            return result
    return ""


def extract_label_value(driver, labels):
    for label in labels:
        xpaths = [
            f"//*[normalize-space(text())='{label}']/following-sibling::*[1]",
            f"//*[normalize-space(text())='{label}']/parent::*/*[last()]",
            f"//*[contains(normalize-space(text()), '{label}')]/following::*[1]",
        ]
        for xpath in xpaths:
            try:
                text = normalize_multiline(driver.find_element(By.XPATH, xpath).text)
                if text and text != label:
                    return text
            except Exception:
                continue
    return ""


def extract_price(driver, page_text, marketplace):
    meta_price = first_attr(
        driver,
        [
            "//meta[@property='product:price:amount']",
            "//meta[@name='twitter:data1']",
        ],
        "content",
    )
    if meta_price:
        digits = re.sub(r"[^\d]", "", meta_price)
        if digits:
            return f"¥{int(digits):,}"

    label_value = extract_label_value(driver, ["現在", "即決", "価格", "販売価格"])
    if label_value:
        match = re.search(r"[¥￥]?\s?[\d,]+(?:円)?", label_value)
        if match:
            raw = re.sub(r"[^\d]", "", match.group(0))
            if raw:
                return f"¥{int(raw):,}"

    if marketplace == "Yahoo!フリマ":
        match = re.search(r"[¥￥]\s?[\d,]+", page_text)
        if match:
            raw = re.sub(r"[^\d]", "", match.group(0))
            if raw:
                return f"¥{int(raw):,}"

    return ""


def extract_shipping(driver, page_text, marketplace):
    if marketplace != "ヤフオク":
        return ""

    shipping = extract_label_value(driver, ["送料"])
    if shipping and shipping != "送料":
        shipping_lines = [line for line in shipping.splitlines() if line not in SECTION_STOP_WORDS]
        shipping = "\n".join(shipping_lines[:2]).strip()
        if shipping:
            return shipping

    shipping = extract_section_text(page_text, "送料")
    if shipping:
        shipping_lines = [line for line in shipping.splitlines() if line not in SECTION_STOP_WORDS]
        shipping = "\n".join(shipping_lines[:2]).strip()
        if shipping:
            return shipping

    match = re.search(r"(送料無料|送料[^\n]{0,30}[\d,]+円|送料情報の取得に失敗しました)", page_text)
    if match:
        return normalize_whitespace(match.group(1))

    return ""


def extract_images(driver):
    urls = []
    seen = set()

    def add_url(url):
        clean = normalize_whitespace(url)
        if not clean or clean in seen:
            return
        if not clean.startswith("http"):
            return
        if "clear.gif" in clean or "/api/v1/clear.gif" in clean:
            return
        if clean.lower().endswith(".svg"):
            return
        seen.add(clean)
        urls.append(clean)

    add_url(first_attr(driver, ["//meta[@property='og:image']"], "content"))

    try:
        image_elements = driver.find_elements(
            By.XPATH,
            "//img[contains(@src, 'yimg') or contains(@src, 'paypayfleamarket') or contains(@src, 'auctions') or contains(@src, 'img')]",
        )
        for element in image_elements:
            add_url(element.get_attribute("src"))
            add_url(element.get_attribute("data-src"))
    except Exception:
        pass

    return "\n".join(urls[:20])


def extract_seller(driver, page_text):
    seller = first_text(
        driver,
        [
            "//a[contains(@href, '/seller/')]/span",
            "//a[contains(@href, '/seller/')]",
            "//a[contains(@href, '/users/')]/span",
            "//a[contains(@href, '/users/')]",
            "//h2/a",
        ],
    )
    if seller:
        return seller.replace(" さん", "").strip()

    match = re.search(r"##\s*(.+?)\s*さん", page_text)
    if match:
        return normalize_whitespace(match.group(1))

    return ""


def extract_detail_text(driver):
    return normalize_multiline(
        first_text(
            driver,
            [
                "//*[normalize-space(text())='商品説明']/following::*[1]",
                "//*[normalize-space(text())='商品の説明']/following::*[1]",
                "//section[contains(., '商品説明')]",
                "//section[contains(., '商品の説明')]",
                "//meta[@name='description']",
            ],
        )
    )


def scrape_listing(driver, url):
    driver.get(url)
    WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(1.0)

    parsed = urlparse(url)
    marketplace = "Yahoo!フリマ" if "paypayfleamarket.yahoo.co.jp" in parsed.netloc else "ヤフオク"
    page_text = driver.find_element(By.TAG_NAME, "body").text

    title = first_text(driver, ["//h1", "//meta[@property='og:title']"])
    if not title:
        title = first_attr(driver, ["//meta[@property='og:title']"], "content")

    description = extract_detail_text(driver)
    brand = extract_label_value(driver, ["ブランド"])
    size = extract_label_value(driver, ["サイズ"])

    return {
        "タイトル": title,
        "価格": extract_price(driver, page_text, marketplace),
        "送料": extract_shipping(driver, page_text, marketplace),
        "画像": extract_images(driver),
        "CustomLabel": url,
        "アイテムスペック用": description,
        "ブランド": brand,
        "サイズ": size,
        "出品者": extract_seller(driver, page_text),
    }


def collect_detail_urls(driver, search_url, max_items):
    driver.get(search_url)
    WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(2.0)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located(
                (
                    By.XPATH,
                    "//a[contains(@href, '/jp/auction/') or contains(@href, 'paypayfleamarket.yahoo.co.jp/item/')]",
                )
            )
        )
    except TimeoutException:
        pass

    anchors = driver.find_elements(
        By.XPATH,
        "//a[contains(@href, '/jp/auction/') or contains(@href, 'paypayfleamarket.yahoo.co.jp/item/')]",
    )

    urls = []
    seen = set()
    for anchor in anchors:
        href = normalize_whitespace(anchor.get_attribute("href"))
        if not href or not any(pattern in href for pattern in DETAIL_URL_PATTERNS):
            continue
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
        if max_items and len(urls) >= max_items:
            break

    return urls


def default_output_path(search_url):
    parsed = urlparse(search_url)
    query = parse_qs(parsed.query)
    keyword = query.get("p", ["yahoo_extract"])[0]
    keyword = unquote_plus(keyword)
    safe_keyword = re.sub(r'[\\/:*?"<>|]+', "_", keyword).strip() or "yahoo_extract"
    return os.path.join("samples", f"{safe_keyword}-Yahoo抽出.csv")


def open_csv_writer(path: str):
    fp = open(path, "w", encoding="utf-8", newline="")
    writer = csv.DictWriter(fp, fieldnames=CSV_HEADERS)
    writer.writeheader()
    fp.flush()
    return fp, writer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Yahoo!オークション検索一覧URL")
    parser.add_argument("--output", help="出力CSVパス")
    parser.add_argument("--max-items", type=int, default=50, help="抽出最大件数")
    args = parser.parse_args()

    output_path = args.output or default_output_path(args.url)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    driver = setup_driver()
    csv_fp, csv_writer = open_csv_writer(output_path)
    try:
        detail_urls = collect_detail_urls(driver, args.url, args.max_items)
        if not detail_urls:
            raise RuntimeError("一覧から商品URLを取得できませんでした")

        for index, detail_url in enumerate(detail_urls, start=1):
            print(f"[{index}/{len(detail_urls)}] {detail_url}")
            csv_writer.writerow(scrape_listing(driver, detail_url))
            csv_fp.flush()
        print(f"saved: {output_path}")
    except KeyboardInterrupt:
        print(f"cancelled: {output_path}")
        return
    finally:
        csv_fp.close()
        driver.quit()


if __name__ == "__main__":
    main()
