from __future__ import annotations

from infrastructure.spiders.qa_report import build_store_qa_report, should_fail_store_quality
from infrastructure.spiders.store_acceptance import StoreAcceptanceProfile, StoreQualityGate


def test_quality_gate_fails_when_thresholds_broken():
    profile = StoreAcceptanceProfile(
        store_name="t",
        quality_gates=StoreQualityGate(
            field_presence_threshold=0.99,
            parse_success_threshold=0.99,
            duplicate_ratio_threshold=0.01,
            partial_item_ratio_threshold=0.01,
            banned_response_threshold=0.0,
            pagination_loop_threshold=0,
            zero_result_category_threshold=0,
        ),
    )
    metrics = {
        "total_listing_pages": 1,
        "total_product_pages": 2,
        "total_products_parsed": 1,
        "total_partial_products": 1,
        "total_failed_products": 1,
        "product_urls_seen_total": 10,
        "product_urls_deduped_total": 9,
        "zero_result_categories": 5,
        "pagination_loops_detected": 3,
        "banned_responses": 1,
        "required_field_presence_hits": 1,
        "required_field_presence_misses": 5,
    }
    report = build_store_qa_report("t", metrics, {"missing_price": 2}, profile)
    assert should_fail_store_quality(report)
    assert report["quality_gate_passed"] is False


def test_quality_gate_passes_on_clean_metrics():
    profile = StoreAcceptanceProfile(store_name="ok")
    metrics = {
        "total_listing_pages": 10,
        "total_product_pages": 10,
        "total_products_parsed": 10,
        "total_partial_products": 1,
        "total_failed_products": 0,
        "product_urls_seen_total": 20,
        "product_urls_deduped_total": 2,
        "zero_result_categories": 0,
        "pagination_loops_detected": 0,
        "banned_responses": 0,
        "required_field_presence_hits": 10,
        "required_field_presence_misses": 0,
    }
    report = build_store_qa_report("ok", metrics, {}, profile)
    assert report["quality_gate_passed"] is True
    assert not should_fail_store_quality(report)
