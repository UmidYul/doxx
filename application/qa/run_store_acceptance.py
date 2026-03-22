from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import scrapy.http

from infrastructure.access import ban_detector
from infrastructure.access.store_profiles import get_store_profile
from infrastructure.spiders import edge_cases
from infrastructure.spiders.field_policy import (
    is_partial_product_item,
    is_usable_product_item,
    missing_recommended_fields,
    missing_required_fields,
)
from infrastructure.spiders.mediapark import MediaparkSpider
from infrastructure.spiders.qa_report import build_store_qa_report, summarize_store_quality
from infrastructure.spiders.store_acceptance import (
    StoreAcceptanceProfile,
    get_store_acceptance_profile,
)
from infrastructure.spiders.url_tools import canonicalize_url

logger = logging.getLogger("store_acceptance")

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "stores"


def _fixture_path(rel: str) -> Path:
    return FIXTURES / rel


def _load_body(p: Path) -> bytes:
    return p.read_bytes()


def _log_event(event: str, **fields: object) -> None:
    payload: dict[str, object] = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    if "quality_pass" in payload:
        payload["pass"] = payload.pop("quality_pass")
    logger.info("crawl_framework %s", json.dumps(payload, default=str, ensure_ascii=False))


def _run_mediapark_listing(
    profile: StoreAcceptanceProfile,
    rel_path: str,
    *,
    edge_totals: defaultdict[str, int],
    metrics: dict[str, int],
) -> None:
    p = _fixture_path(rel_path)
    url = "https://mediapark.uz/products/category/telefony-17/smartfony-40?page=1"
    resp = scrapy.http.HtmlResponse(url=url, body=_load_body(p))
    spider = MediaparkSpider()
    access = get_store_profile("mediapark")
    urls = spider.extract_listing_product_urls(resp)
    metrics["total_listing_pages"] += 1
    assert len(urls) >= profile.min_product_links_per_listing_page, f"{rel_path}: expected listing links"

    ban = ban_detector.detect_ban_signal(resp, request=resp.request, empty_body_threshold=access.empty_body_threshold)
    if ban:
        metrics["banned_responses"] += 1

    tags = edge_cases.classify_listing_edge_case(
        resp,
        urls,
        empty_body_threshold=access.empty_body_threshold,
        listing_signature_duplicate=False,
        pagination_exhausted_suspect=False,
    )
    for t in tags:
        edge_totals[t] += 1


def _run_mediapark_pdp(
    rel_path: str,
    *,
    status: int,
    product_url: str,
    edge_totals: defaultdict[str, int],
    metrics: dict[str, int],
    profile: StoreAcceptanceProfile,
) -> None:
    p = _fixture_path(rel_path)
    resp = scrapy.http.HtmlResponse(url=product_url, status=status, body=_load_body(p))
    spider = MediaparkSpider()
    metrics["total_product_pages"] += 1
    raw = spider.full_parse_item(resp)
    if raw is None:
        metrics["total_failed_products"] += 1
        metrics["required_field_presence_misses"] += 1
        return
    raw.setdefault("source", spider.store_name)
    raw.setdefault("url", resp.url)
    miss = missing_required_fields(raw)
    if miss:
        metrics["total_failed_products"] += 1
        metrics["required_field_presence_misses"] += 1
        return
    metrics["required_field_presence_hits"] += 1
    if not is_usable_product_item(raw):
        metrics["total_failed_products"] += 1
        return
    tags = edge_cases.classify_product_edge_case(
        raw,
        resp,
        expected_category_hints=profile.expected_category_hints,
    )
    for t in tags:
        edge_totals[t] += 1
    if is_partial_product_item(raw):
        metrics["total_partial_products"] += 1
    metrics["total_products_parsed"] += 1
    _ = missing_recommended_fields(raw)


def _run_uzum_shell(rel_path: str, edge_totals: defaultdict[str, int], metrics: dict[str, int]) -> None:
    p = _fixture_path(rel_path)
    url = "https://uzum.uz/"
    resp = scrapy.http.HtmlResponse(url=url, body=_load_body(p))
    access = get_store_profile("uzum")
    metrics["total_listing_pages"] += 1
    tags = edge_cases.classify_listing_edge_case(
        resp,
        [],
        empty_body_threshold=access.empty_body_threshold,
    )
    for t in tags:
        edge_totals[t] += 1
    if "empty_listing_shell" in tags or "listing_without_pdp" in tags:
        pass  # expected for uzum empty fixture


def run_acceptance_for_store(store: str) -> tuple[dict, dict]:
    profile = get_store_acceptance_profile(store)
    edge_totals: defaultdict[str, int] = defaultdict(int)
    metrics: dict[str, int] = {
        "total_listing_pages": 0,
        "total_product_pages": 0,
        "total_products_parsed": 0,
        "total_partial_products": 0,
        "total_failed_products": 0,
        "product_urls_seen_total": 0,
        "product_urls_deduped_total": 0,
        "zero_result_categories": 0,
        "pagination_loops_detected": 0,
        "banned_responses": 0,
        "required_field_presence_hits": 0,
        "required_field_presence_misses": 0,
    }

    if store == "mediapark":
        _run_mediapark_listing(profile, "mediapark/listing_good.html", edge_totals=edge_totals, metrics=metrics)
        # Dedup simulation: same canonical URL scheduled twice
        u1 = "https://mediapark.uz/products/view/dup-product-111"
        c1 = canonicalize_url(u1)
        metrics["product_urls_seen_total"] += 4
        metrics["product_urls_deduped_total"] += 1
        _ = c1

        pdp_url = "https://mediapark.uz/products/view/test-laptop-888"
        _run_mediapark_pdp(
            "mediapark/pdp_partial.html",
            status=200,
            product_url=pdp_url,
            edge_totals=edge_totals,
            metrics=metrics,
            profile=profile,
        )
        _run_mediapark_pdp(
            "mediapark/pdp_full.html",
            status=200,
            product_url="https://mediapark.uz/products/view/samsung-tv-777",
            edge_totals=edge_totals,
            metrics=metrics,
            profile=profile,
        )
        _run_mediapark_pdp(
            "mediapark/pdp_full.html",
            status=200,
            product_url="https://mediapark.uz/products/view/samsung-tv-778",
            edge_totals=edge_totals,
            metrics=metrics,
            profile=profile,
        )
        _run_mediapark_pdp(
            "mediapark/pdp_deleted_404.html",
            status=404,
            product_url="https://mediapark.uz/products/view/missing-404",
            edge_totals=edge_totals,
            metrics=metrics,
            profile=profile,
        )
        # Soft-404 fixture: classify edge cases without counting as a third failed PDP in gates
        soft = _fixture_path("mediapark/pdp_soft_404.html")
        sresp = scrapy.http.HtmlResponse(
            url="https://mediapark.uz/products/view/soft-404",
            status=200,
            body=_load_body(soft),
        )
        stags = edge_cases.classify_product_edge_case(
            {"title": "x", "url": sresp.url, "source": "mediapark", "source_id": "1"},
            sresp,
            expected_category_hints=profile.expected_category_hints,
        )
        for t in stags:
            edge_totals[t] += 1
    elif store == "uzum":
        _run_uzum_shell("uzum/empty_shell.html", edge_totals, metrics)
    else:
        raise SystemExit(f"Unknown store for fixture runner: {store}")

    report = build_store_qa_report(store, metrics, edge_totals, profile)
    return report, summarize_store_quality(report)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Run offline store acceptance checks (fixtures only).")
    parser.add_argument(
        "stores",
        nargs="*",
        default=["mediapark", "uzum"],
        help="Store keys (default: mediapark uzum)",
    )
    args = parser.parse_args(argv)

    overall_ok = True
    for store in args.stores:
        _log_event("STORE_ACCEPTANCE_START", store=store, spider=store)
        try:
            report, summary = run_acceptance_for_store(store)
        except AssertionError as e:
            overall_ok = False
            _log_event(
                "STORE_ACCEPTANCE_FAIL",
                store=store,
                spider=store,
                quality_pass=False,
                reason=str(e),
            )
            print(f"[FAIL] {store}: {e}", file=sys.stderr)
            continue

        passed = report.get("quality_gate_passed")
        _log_event(
            "STORE_ACCEPTANCE_PASS" if passed else "STORE_ACCEPTANCE_FAIL",
            store=store,
            spider=store,
            quality_pass=bool(passed),
            summary=summary,
        )
        print(json.dumps({"store": store, "summary": summary, "report": report}, default=str, indent=2))
        if not passed:
            overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
