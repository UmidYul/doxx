from __future__ import annotations

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_quality import build_normalization_quality_summary
from domain.typed_specs import TypedPartialSpecs


def test_normalization_quality_summary_counts():
    ts = TypedPartialSpecs(ram_gb=8, storage_gb=128)
    fc = {
        "ram_gb": {"confidence": 0.9, "source_labels": ["a"], "source_values": ["8 GB"]},
        "storage_gb": {"confidence": 0.9, "source_labels": ["b"], "source_values": ["128 GB"]},
    }
    suppressed = [
        {"field_name": "battery_mah", "reason_code": WC.SUPPRESSED_BY_CONFLICT, "raw_values": ["1", "2"]},
        {"field_name": "x", "reason_code": WC.SUPPRESSED_BY_CONFIDENCE, "raw_values": ["z"]},
    ]
    q = build_normalization_quality_summary(
        category_hint="phone",
        field_confidence=fc,
        suppressed_typed_fields=suppressed,
        conflicting_fields=["battery_mah"],
        normalization_warnings=[WC.CONFLICTING_VALUES, WC.RAM_STORAGE_SWAP_SUSPECTED],
        mapping_ratio=0.5,
        typed_specs=ts,
    )
    d = q.to_compact_dict()
    assert d["suppressed_fields_count"] == 2
    assert d["warning_count"] == 2
    assert d["conflict_count"] >= 1
    assert d["confident_fields_count"] >= 1
