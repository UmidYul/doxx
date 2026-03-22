from __future__ import annotations

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_resolution import resolve_typed_field_candidates


def test_single_implausible_suppresses():
    v, w, _fc, sup = resolve_typed_field_candidates(
        "battery_mah",
        [("a", "200 mAh", 200)],
        "phone",
    )
    assert v is None
    assert WC.IMPLAUSIBLE_VALUE in w
    assert any(s.reason_code == WC.SUPPRESSED_BY_PLAUSIBILITY for s in sup)


def test_two_equal_candidates_merge_confident():
    v, w, _fc, sup = resolve_typed_field_candidates(
        "ram_gb",
        [("a", "8 GB", 8), ("b", "8 ГБ", 8)],
        "phone",
    )
    assert v == 8
    assert not sup


def test_compatible_numeric_cluster_picks_value():
    v, w, _fc, _sup = resolve_typed_field_candidates(
        "ram_gb",
        [("a", "8 GB", 8), ("b", "8 ГБ", 8)],
        "phone",
    )
    assert v == 8
    assert isinstance(w, list)
