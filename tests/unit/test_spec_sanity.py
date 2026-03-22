from __future__ import annotations

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_sanity import apply_cross_field_sanity_checks
from domain.typed_specs import TypedPartialSpecs


def test_phone_large_display_suppressed():
    ts = TypedPartialSpecs(display_size_inch=55.0)
    out, w, sup = apply_cross_field_sanity_checks(ts, "phone")
    assert out.display_size_inch is None
    assert WC.CATEGORY_MISMATCH in w or WC.CROSS_FIELD_CONFLICT in w
    assert any(s.field_name == "display_size_inch" for s in sup)


def test_tv_large_display_allowed():
    ts = TypedPartialSpecs(display_size_inch=55.0)
    out, w, sup = apply_cross_field_sanity_checks(ts, "tv")
    assert out.display_size_inch == 55.0
    assert not sup


def test_ram_gt_storage_suppresses_ram():
    ts = TypedPartialSpecs(ram_gb=16, storage_gb=8)
    out, w, _sup = apply_cross_field_sanity_checks(ts, "phone")
    assert out.ram_gb is None
    assert out.storage_gb == 8
    assert WC.RAM_STORAGE_SWAP_SUSPECTED in w


def test_weight_g_kg_conflict_suppresses_both():
    ts = TypedPartialSpecs(weight_g=200, weight_kg=5.0)
    out, w, sup = apply_cross_field_sanity_checks(ts, "laptop")
    assert out.weight_g is None and out.weight_kg is None
    assert WC.INCONSISTENT_WEIGHT_UNITS in w
    assert len(sup) >= 1


def test_hdmi_false_with_positive_count():
    ts = TypedPartialSpecs(hdmi=False, hdmi_count=2)
    out, w, sup = apply_cross_field_sanity_checks(ts, "tv")
    assert out.hdmi_count is None
    assert WC.INCONSISTENT_HDMI_STATE in w
    assert any(s.field_name == "hdmi_count" for s in sup)


def test_smart_tv_on_phone_suppressed():
    ts = TypedPartialSpecs(smart_tv=True)
    out, w, _sup = apply_cross_field_sanity_checks(ts, "phone")
    assert out.smart_tv is None
    assert WC.CROSS_FIELD_CONFLICT in w
