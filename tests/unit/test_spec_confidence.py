from __future__ import annotations

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_confidence import (
    detect_missing_unit,
    merge_field_confidences,
    score_typed_field_confidence,
    should_suppress_field,
)
from domain.normalization_quality import FieldConfidence


def test_direct_key_exact_alias_high_confidence():
    fc = score_typed_field_confidence(
        "ram_gb",
        8,
        "ram_gb",
        "8 GB",
        "phone",
        direct_key=True,
    )
    assert fc.confidence >= 0.79
    assert "ram_gb" in fc.source_labels


def test_ambiguous_alias_lowers_confidence():
    base = score_typed_field_confidence(
        "storage_gb",
        128,
        "mem",
        "128 GB",
        "phone",
        direct_key=False,
        rule_priority=5,
        ambiguous_alias=False,
    )
    amb = score_typed_field_confidence(
        "storage_gb",
        128,
        "mem",
        "128 GB",
        "phone",
        direct_key=False,
        rule_priority=5,
        ambiguous_alias=True,
    )
    assert amb.confidence < base.confidence
    assert WC.AMBIGUOUS_ALIAS in amb.warning_codes


def test_missing_unit_lowers_confidence():
    with_unit = score_typed_field_confidence(
        "ram_gb",
        8,
        "ram",
        "8 GB",
        "phone",
        missing_unit=False,
    )
    bare = score_typed_field_confidence(
        "ram_gb",
        8,
        "ram",
        "8",
        "phone",
        missing_unit=None,
    )
    assert detect_missing_unit("ram_gb", "8") is True
    assert bare.confidence < with_unit.confidence
    assert WC.MISSING_UNIT in bare.warning_codes


def test_deprecated_alias_warning_and_lower_score():
    fc = score_typed_field_confidence(
        "ram_gb",
        8,
        "old_label",
        "8 GB",
        "phone",
        deprecated_alias=True,
    )
    assert WC.DEPRECATED_ALIAS in fc.warning_codes


def test_merge_consistent_sources_raises_confidence():
    a = score_typed_field_confidence("ram_gb", 8, "a", "8 GB", "phone", direct_key=True)
    b = score_typed_field_confidence("ram_gb", 8, "b", "8", "phone", direct_key=True)
    m = merge_field_confidences("ram_gb", [a, b], "phone")
    assert m.confidence >= max(a.confidence, b.confidence)
    assert m.resolution_reason == "merged_equivalent_sources"


def test_should_suppress_respects_threshold(monkeypatch):
    low = FieldConfidence(
        field_name="x",
        confidence=0.1,
        source_labels=["l"],
        source_values=["v"],
    )
    import application.extractors.spec_confidence as sc

    monkeypatch.setattr(sc.settings, "ENABLE_TYPED_SPEC_CONFIDENCE", True)
    monkeypatch.setattr(sc.settings, "ENABLE_TYPED_SPEC_SUPPRESSION", True)
    monkeypatch.setattr(sc.settings, "TYPED_SPEC_MIN_CONFIDENCE_DEFAULT", 0.65)
    assert should_suppress_field(low, None) is True

    monkeypatch.setattr(sc.settings, "ENABLE_TYPED_SPEC_SUPPRESSION", False)
    assert should_suppress_field(low, None) is False
