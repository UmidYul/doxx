from __future__ import annotations

from domain.crm_apply_result import CrmApplyResult

from infrastructure.observability.payload_summary import summarize_apply_result, summarize_normalized_payload


def test_summarize_normalized_payload_no_raw_leak():
    huge_raw = {f"k{i}": "x" * 100 for i in range(50)}
    norm = {
        "price_value": 10,
        "brand": "B",
        "barcode": "123",
        "raw_specs": huge_raw,
        "typed_specs": {"a": 1, "b": 2},
        "normalization_warnings": ["w1", "w2"],
        "suppressed_typed_fields": [{}],
        "spec_coverage": {"enabled": True, "mapped_fields_count": 3, "unmapped_fields_count": 1},
        "category_hint": "phone",
        "source_id": "sid",
    }
    s = summarize_normalized_payload(norm)
    assert s["raw_specs_count"] == 50
    assert "raw_specs" not in s
    assert s["typed_specs_count"] == 2
    assert s["normalization_warning_count"] == 2
    assert s["has_price"] is True


def test_summarize_apply_result_compact():
    r = CrmApplyResult(
        event_id="e",
        entity_key="k",
        payload_hash="h",
        success=True,
        status="applied",
        crm_listing_id="L1",
        crm_product_id="P1",
    )
    s = summarize_apply_result(r)
    assert s["recognized"] is True
    assert s["has_listing_id"] is True
    assert "error_message" not in s or s.get("error_message") is None
