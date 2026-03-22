from __future__ import annotations

from collections import defaultdict
from typing import Any

from infrastructure.spiders.store_acceptance import StoreAcceptanceProfile, StoreQualityGate


def build_store_qa_report(
    store_name: str,
    metrics: dict[str, Any],
    edge_case_counts: dict[str, int],
    acceptance_profile: StoreAcceptanceProfile,
) -> dict[str, Any]:
    """Assemble a JSON-serializable QA report from crawl metrics + edge-case histogram."""
    gates = acceptance_profile.quality_gates
    total_products = int(metrics.get("total_products_parsed", 0))
    total_partial = int(metrics.get("total_partial_products", 0))
    total_failed = int(metrics.get("total_failed_products", 0))
    total_attempts = total_products + total_failed
    parse_success = (total_products / total_attempts) if total_attempts else 1.0

    req_hits = int(metrics.get("required_field_presence_hits", 0))
    req_miss = int(metrics.get("required_field_presence_misses", 0))
    req_total = req_hits + req_miss
    field_presence = (req_hits / req_total) if req_total else 1.0

    seen = int(metrics.get("product_urls_seen_total", 0))
    deduped = int(metrics.get("product_urls_deduped_total", 0))
    duplicate_ratio = (deduped / seen) if seen else 0.0

    partial_ratio = (total_partial / total_products) if total_products else 0.0

    listing_pages = int(metrics.get("total_listing_pages", 0))
    banned = int(metrics.get("banned_responses", 0))
    banned_rate = (banned / listing_pages) if listing_pages else 0.0

    pagination_loops = int(metrics.get("pagination_loops_detected", 0))
    zero_cats = int(metrics.get("zero_result_categories", 0))

    gate_eval = _evaluate_gates(
        gates=gates,
        field_presence=field_presence,
        parse_success=parse_success,
        duplicate_ratio=duplicate_ratio,
        partial_ratio=partial_ratio,
        banned_rate=banned_rate,
        pagination_loops=pagination_loops,
        zero_cats=zero_cats,
    )

    return {
        "store": store_name,
        "acceptance_profile": acceptance_profile.store_name,
        "total_listing_pages": listing_pages,
        "total_product_pages": int(metrics.get("total_product_pages", 0)),
        "total_products_parsed": total_products,
        "total_partial_products": total_partial,
        "total_failed_products": total_failed,
        "duplicate_product_ratio": duplicate_ratio,
        "zero_result_categories": zero_cats,
        "pagination_loops_detected": pagination_loops,
        "banned_responses": banned,
        "edge_case_counts": dict(edge_case_counts),
        "required_field_presence": {
            "hits": req_hits,
            "misses": req_miss,
            "ratio": field_presence,
        },
        "derived": {
            "parse_success_ratio": parse_success,
            "partial_item_ratio": partial_ratio,
            "banned_response_rate": banned_rate,
        },
        "quality_gate_passed": gate_eval["passed"],
        "quality_gate_details": gate_eval["details"],
    }


def summarize_store_quality(report: dict[str, Any]) -> dict[str, Any]:
    """Short summary for CLI / CI."""
    return {
        "store": report.get("store"),
        "quality_gate_passed": report.get("quality_gate_passed"),
        "parse_success_ratio": (report.get("derived") or {}).get("parse_success_ratio"),
        "field_presence_ratio": (report.get("required_field_presence") or {}).get("ratio"),
        "duplicate_product_ratio": report.get("duplicate_product_ratio"),
        "partial_item_ratio": (report.get("derived") or {}).get("partial_item_ratio"),
        "pagination_loops": report.get("pagination_loops_detected"),
        "banned_responses": report.get("banned_responses"),
    }


def should_fail_store_quality(report: dict[str, Any]) -> bool:
    return not bool(report.get("quality_gate_passed"))


def _evaluate_gates(
    *,
    gates: StoreQualityGate,
    field_presence: float,
    parse_success: float,
    duplicate_ratio: float,
    partial_ratio: float,
    banned_rate: float,
    pagination_loops: int,
    zero_cats: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, threshold: Any) -> None:
        checks.append(
            {
                "quality_gate": name,
                "value": value,
                "threshold": threshold,
                "pass": passed,
            }
        )

    add(
        "field_presence_threshold",
        field_presence >= gates.field_presence_threshold,
        field_presence,
        gates.field_presence_threshold,
    )
    add(
        "parse_success_threshold",
        parse_success >= gates.parse_success_threshold,
        parse_success,
        gates.parse_success_threshold,
    )
    add(
        "duplicate_ratio_threshold",
        duplicate_ratio <= gates.duplicate_ratio_threshold,
        duplicate_ratio,
        gates.duplicate_ratio_threshold,
    )
    add(
        "partial_item_ratio_threshold",
        partial_ratio <= gates.partial_item_ratio_threshold,
        partial_ratio,
        gates.partial_item_ratio_threshold,
    )
    add(
        "banned_response_threshold",
        banned_rate <= gates.banned_response_threshold,
        banned_rate,
        gates.banned_response_threshold,
    )
    add(
        "pagination_loop_threshold",
        pagination_loops <= gates.pagination_loop_threshold,
        pagination_loops,
        gates.pagination_loop_threshold,
    )
    add(
        "zero_result_category_threshold",
        zero_cats <= gates.zero_result_category_threshold,
        zero_cats,
        gates.zero_result_category_threshold,
    )

    passed = all(c["pass"] for c in checks)
    return {"passed": passed, "details": checks}


def empty_edge_case_counts() -> defaultdict[str, int]:
    return defaultdict(int)


def crawl_snapshot_to_qa_metrics(snap: dict[str, Any]) -> dict[str, Any]:
    """Map :meth:`CrawlRuntimeRegistry.snapshot_metrics` keys to QA report input."""
    return {
        "total_listing_pages": int(snap.get("listing_pages_seen_total", 0)),
        "total_product_pages": int(snap.get("product_pages_seen_total", 0)),
        "total_products_parsed": int(snap.get("product_items_yielded_total", 0)),
        "total_partial_products": int(snap.get("product_parse_partial_total", 0)),
        "total_failed_products": int(snap.get("product_parse_failed_total", 0)),
        "product_urls_seen_total": int(snap.get("product_urls_seen_total", 0)),
        "product_urls_deduped_total": int(snap.get("product_urls_deduped_total", 0)),
        "zero_result_categories": int(snap.get("zero_result_categories_count", 0)),
        "pagination_loops_detected": int(snap.get("pagination_loops_detected", 0)),
        "banned_responses": int(snap.get("banned_responses_total", 0)),
        "required_field_presence_hits": int(snap.get("required_field_presence_hits", 0)),
        "required_field_presence_misses": int(snap.get("required_field_presence_misses", 0)),
    }
