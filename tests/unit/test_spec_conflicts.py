from __future__ import annotations

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_resolution import resolve_typed_field_candidates


def test_equivalent_values_merge_without_warning():
    v, w, _fcs, _sup = resolve_typed_field_candidates(
        "ram_gb",
        [("a", "8 GB", 8), ("b", "8", 8)],
        "phone",
    )
    assert v == 8
    assert WC.CONFLICTING_VALUES not in w


def test_conflicting_ram_values_suppress_typed_field():
    v, w, _fcs, sup = resolve_typed_field_candidates(
        "ram_gb",
        [("a", "8", 8), ("b", "16", 16)],
        "phone",
    )
    assert v is None
    assert WC.CONFLICTING_VALUES in w
    assert any(s.reason_code == WC.SUPPRESSED_BY_CONFLICT for s in sup)


def test_all_implausible_returns_none():
    v, w, _fcs, _sup = resolve_typed_field_candidates(
        "battery_mah",
        [("a", "50 mAh", 50), ("b", "40 mAh", 40)],
        "phone",
    )
    assert v is None
    assert WC.IMPLAUSIBLE_VALUE in w
