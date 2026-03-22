from __future__ import annotations

import pytest

from application.extractors.spec_coverage import (
    build_spec_coverage_report,
    calculate_mapping_ratio,
    summarize_unmapped_labels,
)
from domain.typed_specs import TypedPartialSpecs


def test_calculate_mapping_ratio():
    raw = {"a": "1", "b": "2", "c": "3"}
    assert calculate_mapping_ratio(raw, 2) == pytest.approx(2 / 3)
    assert calculate_mapping_ratio({}, 0) == 1.0


def test_summarize_unmapped_labels():
    assert summarize_unmapped_labels(["x", "x", "y"]) == {"x": 2, "y": 1}


def test_build_spec_coverage_report():
    raw = {"k1": "v", "k2": "v"}
    ts = TypedPartialSpecs(ram_gb=8)
    meta = {
        "mapped_fields_count": 1,
        "unmapped_fields_count": 1,
        "unmapped_labels": ["k2"],
        "deprecated_alias_hits": [],
        "conflicting_fields": ["ram_gb"],
    }
    rep = build_spec_coverage_report(raw, ts, meta)
    assert rep["total_raw_fields"] == 2
    assert rep["mapped_fields_count"] == 1
    assert rep["conflict_count"] == 1
    assert "ram_gb" in rep["typed_fields_filled"]
