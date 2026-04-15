from __future__ import annotations

import html
import re
from typing import Any

import scrapy.http

from infrastructure.access import ban_detector
from infrastructure.spiders.field_policy import (
    has_price_signal,
    is_partial_product_item,
    is_usable_product_item,
    missing_recommended_fields,
)
from infrastructure.spiders.url_tools import canonicalize_url

# Taxonomy labels (stable string IDs for logs, QA reports, and profiles).
EDGE_MISSING_PRICE = "missing_price"
EDGE_MISSING_TITLE = "missing_title"
EDGE_MISSING_SOURCE_ID = "missing_source_id"
EDGE_LISTING_WITHOUT_PDP = "listing_without_pdp"
EDGE_DELETED_PRODUCT_404 = "deleted_product_404"
EDGE_PRODUCT_SOFT_404 = "product_soft_404"
EDGE_OUT_OF_STOCK_WITH_PRICE = "out_of_stock_with_price"
EDGE_OLD_PRICE_ONLY = "old_price_only"
EDGE_DUPLICATE_PDP_URLS = "duplicate_pdp_urls"
EDGE_DUPLICATE_SOURCE_ID = "duplicate_source_id"
EDGE_VARIANT_PRODUCT = "variant_product"
EDGE_CONFLICTING_BRAND = "conflicting_brand"
EDGE_EMPTY_LISTING_SHELL = "empty_listing_shell"
EDGE_JS_SHELL_LISTING = "js_shell_listing"
EDGE_MOBILE_REDIRECT = "mobile_redirect"
EDGE_INFINITE_PAGINATION = "infinite_pagination"
EDGE_LISTING_REPEAT = "listing_repeat"
EDGE_IMAGE_ONLY_PRODUCT = "image_only_product"
EDGE_SPECS_MISSING = "specs_missing"
EDGE_PARTIAL_PRODUCT = "partial_product"
EDGE_ACCESSORY_MISCLASSIFIED = "accessory_misclassified"
EDGE_CATEGORY_MISCLASSIFIED = "category_misclassified"
EDGE_CANONICAL_MISMATCH = "canonical_mismatch"

_SOFT_404_PAT = re.compile(
    r"\b404\s+not\s+found\b|"
    r"\u0442\u043e\u0432\u0430\u0440\s+\u043d\u0435\s+\u043d\u0430\u0439\u0434\u0435\u043d|"
    r"\u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430\s+\u043d\u0435\s+\u043d\u0430\u0439\u0434\u0435\u043d\u0430|"
    r"page\s+not\s+found|product\s+unavailable",
    re.I,
)
_VARIANT_PAT = re.compile(
    r"\b(variant|\u0432\u0430\u0440\u0438\u0430\u043d\u0442|\u0446\u0432\u0435\u0442|memory|gb\/|\/\d+gb)\b",
    re.I,
)


def _visible_page_text(response: scrapy.http.Response, *, limit: int = 12_000) -> str:
    """Return normalized visible HTML text without script/style noise."""
    raw = response.text or ""
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<noscript\b[^>]*>.*?</noscript>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()[:limit]


def classify_listing_edge_case(
    response: scrapy.http.Response,
    extracted_urls: list[str],
    *,
    empty_body_threshold: int = 400,
    listing_signature_duplicate: bool = False,
    pagination_exhausted_suspect: bool = False,
) -> list[str]:
    tags: list[str] = []
    if not extracted_urls:
        tags.append(EDGE_LISTING_WITHOUT_PDP)

    canon = [canonicalize_url(u) for u in extracted_urls]
    if len(canon) > len(set(canon)):
        tags.append(EDGE_DUPLICATE_PDP_URLS)

    ban = ban_detector.detect_ban_signal(response, empty_body_threshold=empty_body_threshold)
    if ban == "empty_shell":
        tags.append(EDGE_EMPTY_LISTING_SHELL)
    if ban == "js_shell":
        tags.append(EDGE_JS_SHELL_LISTING)
    if ban == "mobile_redirect":
        tags.append(EDGE_MOBILE_REDIRECT)

    if listing_signature_duplicate:
        tags.append(EDGE_LISTING_REPEAT)
    if pagination_exhausted_suspect:
        tags.append(EDGE_INFINITE_PAGINATION)

    return list(dict.fromkeys(tags))


def classify_product_edge_case(
    item: dict[str, Any],
    response: scrapy.http.Response,
    *,
    expected_category_hints: frozenset[str] | None = None,
) -> list[str]:
    tags: list[str] = []
    visible_text = _visible_page_text(response)

    if response.status == 404:
        tags.append(EDGE_DELETED_PRODUCT_404)
    elif response.status == 200 and _SOFT_404_PAT.search(visible_text):
        tags.append(EDGE_PRODUCT_SOFT_404)

    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        tags.append(EDGE_MISSING_TITLE)

    sid = str(item.get("source_id") or item.get("external_id") or "").strip()
    if not sid:
        tags.append(EDGE_MISSING_SOURCE_ID)

    if not has_price_signal(item):
        tags.append(EDGE_MISSING_PRICE)

    specs = item.get("raw_specs") or {}
    if isinstance(specs, dict) and len(specs) == 0:
        tags.append(EDGE_SPECS_MISSING)

    imgs = item.get("image_urls") or []
    if title and isinstance(imgs, list) and imgs and not has_price_signal(item):
        tags.append(EDGE_IMAGE_ONLY_PRODUCT)

    in_stock = item.get("in_stock", True)
    if in_stock is False and has_price_signal(item):
        tags.append(EDGE_OUT_OF_STOCK_WITH_PRICE)

    ps = str(item.get("price_str") or item.get("price_raw") or "")
    if "\u0431\u044b\u043b\u043e" in ps.lower() or "was" in ps.lower():
        if re.search(r"\d", ps):
            tags.append(EDGE_OLD_PRICE_ONLY)

    url = str(item.get("url") or response.url or "")
    if _VARIANT_PAT.search(url) or _VARIANT_PAT.search(title):
        tags.append(EDGE_VARIANT_PRODUCT)

    if is_usable_product_item(item) and is_partial_product_item(item):
        tags.append(EDGE_PARTIAL_PRODUCT)

    rec_missing = missing_recommended_fields(item)
    if "brand" in rec_missing:
        ch = str(item.get("category_hint") or item.get("category") or "").lower()
        if "accessory" in ch or "\u0430\u043a\u0441\u0435\u0441\u0441\u0443\u0430\u0440" in title.lower():
            tags.append(EDGE_ACCESSORY_MISCLASSIFIED)

    if expected_category_hints is not None:
        hint = item.get("category_hint") or item.get("category")
        if hint is not None and str(hint).strip():
            if str(hint).strip().lower() not in {h.lower() for h in expected_category_hints}:
                tags.append(EDGE_CATEGORY_MISCLASSIFIED)

    req_canon = canonicalize_url(str(item.get("url") or ""))
    resp_canon = canonicalize_url(response.url)
    if req_canon and resp_canon and req_canon != resp_canon:
        tags.append(EDGE_CANONICAL_MISMATCH)

    return list(dict.fromkeys(tags))
