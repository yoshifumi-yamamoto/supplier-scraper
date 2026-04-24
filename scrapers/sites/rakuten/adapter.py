from __future__ import annotations

import re
import os
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from scrapers.common.items import fetch_active_items_by_domain, update_item_stock_bulk
from scrapers.common.logging_utils import json_log
from scrapers.common.models import ScrapeStatus
from scrapers.common.run_store import finish_step, start_step
from scrapers.sites.rakuten.client import (
    RakutenApiError,
    auth_ready,
    fetch_item_by_code,
    fetch_page_hints,
    search_items,
)
from scrapers.sites.rakuten.normalizer import normalize_item


STATUS_MAP = {
    ScrapeStatus.IN_STOCK: "在庫あり",
    ScrapeStatus.OUT_OF_STOCK: "在庫なし",
    ScrapeStatus.UNKNOWN: "不明",
    ScrapeStatus.ERROR: "エラー",
}

RAKUTEN_DOMAINS = ["item.rakuten.co.jp", "www.rakuten.co.jp"]
RAKUTEN_CONFIRMED_PREFIX = "rakuten:"
RAKUTEN_PENDING_PREFIX = "rakuten-pending:"
MODEL_RE = re.compile(r"\b[a-z0-9]+(?:[-_][a-z0-9]+)+\b", re.IGNORECASE)
ALNUM_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
DISCOVERY_LIMIT = max(int(os.getenv("RAKUTEN_DISCOVERY_LIMIT", "30")), 0)


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _extract_models(*values: str | None) -> list[str]:
    models: list[str] = []
    for value in values:
        for match in MODEL_RE.findall((value or "").lower()):
            if len(match) < 5:
                continue
            if match not in models:
                models.append(match)
    return models


def _parse_saved_item_code(sku: str | None) -> tuple[str | None, str | None]:
    value = (sku or "").strip()
    if not value:
        return None, None
    if value.startswith(RAKUTEN_CONFIRMED_PREFIX):
        return "confirmed", value[len(RAKUTEN_CONFIRMED_PREFIX) :]
    if value.startswith(RAKUTEN_PENDING_PREFIX):
        return "pending", value[len(RAKUTEN_PENDING_PREFIX) :]
    return None, None


def _parse_item_code_from_url(stocking_url: str) -> tuple[str, str] | None:
    if not stocking_url:
        return None
    parsed = urlparse(stocking_url)
    host = (parsed.netloc or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    shop_code, item_local_code = parts[0], parts[1]
    if not shop_code or not item_local_code:
        return None
    if host not in RAKUTEN_DOMAINS:
        return None
    return shop_code, item_local_code


def _normalize_image_key(url: str | None) -> str:
    if not url:
        return ""
    candidate = url.split("?")[0].rstrip("/")
    return candidate.rsplit("/", 1)[-1].lower()


def _candidate_image_match(row_image: str | None, candidate: dict[str, Any]) -> bool:
    row_key = _normalize_image_key(row_image)
    if not row_key:
        return False
    image_urls = []
    for key in ("mediumImageUrls", "smallImageUrls"):
        values = candidate.get(key) or []
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    image_urls.append(value.get("imageUrl") or value.get("url") or "")
                elif isinstance(value, str):
                    image_urls.append(value)
    image_urls.append(candidate.get("imageUrl") or candidate.get("mediumImageUrl") or "")
    return any(_normalize_image_key(url) == row_key for url in image_urls if url)


def _score_candidate(
    *,
    candidate: dict[str, Any],
    shop_code: str,
    models: list[str],
    row_title: str,
    row_image_url: str | None,
    local_code_hint: str | None = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    candidate_shop = (candidate.get("shopCode") or "").strip().lower()
    if candidate_shop != shop_code.lower():
        return 0.0, ["shop_mismatch"]

    score += 0.2
    reasons.append("shop_match")

    candidate_title = _normalize_text(candidate.get("itemName") or candidate.get("itemCaption"))
    candidate_item_code = _normalize_text(candidate.get("itemCode"))
    candidate_caption = _normalize_text(candidate.get("itemCaption"))
    candidate_url = _normalize_text(candidate.get("itemUrl"))

    local_code = _normalize_text(local_code_hint)
    if local_code and (
        local_code in candidate_title
        or local_code in candidate_caption
        or local_code in candidate_item_code
        or local_code in candidate_url
    ):
        score += 0.35
        reasons.append(f"local_code_match:{local_code}")

    model_exact = False
    for model in models:
        if model and (model in candidate_title or model in candidate_item_code):
            score += 0.45
            reasons.append(f"model_match:{model}")
            model_exact = True
            break

    title_ratio = SequenceMatcher(None, _normalize_text(row_title), candidate_title).ratio() if row_title and candidate_title else 0.0
    if title_ratio >= 0.75:
        score += 0.2
        reasons.append(f"title_sim:{title_ratio:.2f}")
    elif title_ratio >= 0.55:
        score += 0.1
        reasons.append(f"title_sim_weak:{title_ratio:.2f}")

    if _candidate_image_match(row_image_url, candidate):
        score += 0.15
        reasons.append("image_match")

    if model_exact and score >= 0.65:
        score += 0.05

    return min(score, 1.0), reasons


def _build_search_keywords(*, title: str, local_code_hint: str | None, page_models: list[str] | None = None) -> list[str]:
    keywords: list[str] = []
    models = _extract_models(local_code_hint, title, *(page_models or []))
    for model in models[:3]:
        normalized_model = model.replace("_", "-").strip("- ")
        if len(normalized_model) >= 5 and not normalized_model.isdigit():
            keywords.append(normalized_model)
    normalized_title = " ".join((title or "").split())
    if normalized_title:
        cleaned_title = re.sub(r"[^\w\s\-]", " ", normalized_title, flags=re.UNICODE)
        cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()
        title_tokens = [
            token
            for token in cleaned_title.split()
            if len(ALNUM_RE.findall(token)) > 0 and not token.isdigit()
        ]
        if title_tokens:
            keywords.append(" ".join(title_tokens[:8])[:120])
    unique_keywords: list[str] = []
    for keyword in keywords:
        value = keyword.strip()
        if not value:
            continue
        if len(value) < 3:
            continue
        if value.isdigit():
            continue
        if value not in unique_keywords:
            unique_keywords.append(value)
    return unique_keywords


def _discover_item(
    *,
    shop_code: str,
    local_code_hint: str | None,
    row_title: str,
    row_image_url: str | None,
    page_models: list[str] | None = None,
) -> tuple[dict[str, Any] | None, float, list[str], str | None]:
    best_candidate: dict[str, Any] | None = None
    best_score = 0.0
    best_reasons: list[str] = []
    best_keyword: str | None = None
    models = _extract_models(local_code_hint, row_title, *(page_models or []))
    for keyword in _build_search_keywords(title=row_title, local_code_hint=local_code_hint, page_models=page_models):
        candidates = search_items(keyword=keyword, shop_code=shop_code, hits=10)
        for candidate in candidates:
            score, reasons = _score_candidate(
                candidate=candidate,
                shop_code=shop_code,
                models=models,
                row_title=row_title,
                row_image_url=row_image_url,
                local_code_hint=local_code_hint,
            )
            if score > best_score:
                best_candidate = candidate
                best_score = score
                best_reasons = reasons
                best_keyword = keyword
        if best_score >= 0.85:
            break
    if best_keyword:
        best_reasons = [f"keyword:{best_keyword}", *best_reasons]
    return best_candidate, best_score, best_reasons, best_keyword


def _log_item_result(*, run_id: str, ebay_item_id: str, stocking_url: str, item_code: str | None, shop_code: str | None, status: ScrapeStatus, message: str) -> None:
    json_log(
        "info",
        "rakuten item api result",
        run_id=run_id,
        site="rakuten",
        ebay_item_id=ebay_item_id,
        stocking_url=stocking_url,
        shop_code=shop_code,
        item_code=item_code,
        scrape_status=STATUS_MAP[status],
        scrape_message=message,
        source="api",
    )


def run_pipeline(run_id: str) -> dict[str, Any]:
    fetch_step = start_step(run_id=run_id, step_name="fetch_items")
    try:
        if not auth_ready():
            raise RakutenApiError("rakuten auth not configured")
        items = fetch_active_items_by_domain(RAKUTEN_DOMAINS, page_size=50)
        if not items:
            finish_step(fetch_step, status="success", message="rakuten no target items")
            return {
                "run_id": run_id,
                "site": "rakuten",
                "status": "success",
                "message": "rakuten api pipeline completed: 0 items",
                "source": "api",
            }
        finish_step(fetch_step, status="success", message=f"fetched {len(items)} items")
    except Exception as exc:  # noqa: BLE001
        finish_step(fetch_step, status="failed", message=str(exc))
        return {
            "run_id": run_id,
            "site": "rakuten",
            "status": ScrapeStatus.ERROR.value,
            "message": f"fetch failed: {exc}",
            "source": "api",
        }

    processed = 0
    in_stock = 0
    out_of_stock = 0
    unknown = 0
    pending_updates: list[dict[str, Any]] = []
    discovery_attempts = 0
    discovery_skipped = 0
    for row in items:
        ebay_item_id = row.get("ebay_item_id")
        if not ebay_item_id:
            continue
        stocking_url = row.get("stocking_url") or ""
        parsed = _parse_item_code_from_url(stocking_url)
        shop_code = parsed[0] if parsed else None
        item_code = parsed[1] if parsed else None
        step_id = start_step(run_id=run_id, step_name=f"check:{ebay_item_id}")
        try:
            saved_state, saved_item_code = _parse_saved_item_code(row.get("sku"))
            if saved_state == "pending":
                status = ScrapeStatus.UNKNOWN
                message = f"rakuten candidate unresolved: {saved_item_code or 'pending'}"
                next_sku = row.get("sku")
                item_code = saved_item_code or item_code
            elif saved_state == "confirmed" and saved_item_code:
                item_code = saved_item_code
                raw = fetch_item_by_code(item_code, shop_code=shop_code)
                status, message = normalize_item(raw)
                next_sku = row.get("sku")
            else:
                row_title = row.get("title") or ""
                row_image_url = row.get("image_url")
                local_code_hint = item_code
                if not shop_code:
                    status = ScrapeStatus.UNKNOWN
                    message = "rakuten shopCode could not be resolved from stocking_url"
                    next_sku = row.get("sku")
                elif DISCOVERY_LIMIT and discovery_attempts >= DISCOVERY_LIMIT:
                    status = ScrapeStatus.UNKNOWN
                    message = "rakuten discovery deferred by run limit"
                    next_sku = row.get("sku")
                    discovery_skipped += 1
                else:
                    discovery_attempts += 1
                    page_hints = fetch_page_hints(stocking_url)
                    page_title = page_hints.get("page_title") or row_title
                    page_models = page_hints.get("page_models") or []
                    candidate, confidence, reasons, _ = _discover_item(
                        shop_code=shop_code,
                        local_code_hint=local_code_hint,
                        row_title=page_title,
                        row_image_url=row_image_url,
                        page_models=page_models,
                    )
                    if candidate and confidence >= 0.85 and candidate.get("itemCode"):
                        item_code = str(candidate["itemCode"])
                        status, normalized_message = normalize_item(candidate)
                        message = f"{normalized_message} | discovery_confirmed confidence={confidence:.2f} reasons={','.join(reasons[:4])}"
                        next_sku = f"{RAKUTEN_CONFIRMED_PREFIX}{item_code}"
                    elif candidate and confidence >= 0.55 and candidate.get("itemCode"):
                        item_code = str(candidate["itemCode"])
                        status = ScrapeStatus.UNKNOWN
                        message = f"rakuten candidate pending confidence={confidence:.2f} reasons={','.join(reasons[:4])}"
                        next_sku = f"{RAKUTEN_PENDING_PREFIX}{item_code}"
                    else:
                        status = ScrapeStatus.UNKNOWN
                        message = "rakuten itemCode discovery unresolved"
                        next_sku = row.get("sku")
            pending_updates.append(
                {
                    "ebay_item_id": ebay_item_id,
                    "scraped_stock_status": STATUS_MAP[status],
                    "is_scraped": status != ScrapeStatus.UNKNOWN,
                    "sku": next_sku,
                }
            )
            _log_item_result(
                run_id=run_id,
                ebay_item_id=str(ebay_item_id),
                stocking_url=stocking_url,
                shop_code=shop_code,
                item_code=item_code,
                status=status,
                message=message,
            )
            if status == ScrapeStatus.IN_STOCK:
                in_stock += 1
            elif status == ScrapeStatus.OUT_OF_STOCK:
                out_of_stock += 1
            else:
                unknown += 1
            finish_step(step_id, status="success", message=message)
            processed += 1
            if len(pending_updates) >= 20:
                update_item_stock_bulk(pending_updates)
                pending_updates = []
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            json_log(
                "warning",
                "rakuten item api failed",
                run_id=run_id,
                site="rakuten",
                ebay_item_id=ebay_item_id,
                stocking_url=stocking_url,
                shop_code=shop_code,
                item_code=item_code,
                error=err[:300],
                source="api",
            )
            pending_updates.append(
                {
                    "ebay_item_id": ebay_item_id,
                    "scraped_stock_status": "不明",
                    "is_scraped": False,
                    "sku": row.get("sku"),
                }
            )
            unknown += 1
            finish_step(step_id, status="success", message=f"rakuten api failed, marked unknown: {err[:300]}")
            processed += 1
            if len(pending_updates) >= 20:
                update_item_stock_bulk(pending_updates)
                pending_updates = []

    if pending_updates:
        update_item_stock_bulk(pending_updates)

    return {
        "run_id": run_id,
        "site": "rakuten",
        "status": "success",
        "message": f"rakuten api pipeline completed: checked={processed} in={in_stock} out={out_of_stock} unknown={unknown} discovery_attempts={discovery_attempts} discovery_skipped={discovery_skipped}",
        "source": "api",
    }
