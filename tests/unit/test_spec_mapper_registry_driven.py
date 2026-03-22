from __future__ import annotations

from application.extractors.spec_mapper import map_raw_specs_to_typed_partial, resolve_raw_label


def test_resolve_raw_label_common():
    c, tf = resolve_raw_label("Оперативная память", "phone", None)
    assert tf == "ram_gb"
    assert c is not None


def test_deprecated_alias_emits_warning():
    raw = {"оперативка": "8 GB"}
    spec, warnings, meta = map_raw_specs_to_typed_partial(
        raw, "phone", store_name="teststore", source_id=None, url="https://x"
    )
    assert spec.ram_gb == 8
    assert "deprecated_alias" in warnings
    assert meta["deprecated_alias_hits"]


def test_category_rule_beats_common_for_tablet_ram_priority():
    """Tablet-specific duplicate label uses higher-priority category rule when applicable."""
    raw = {"оперативная память": "12 GB"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "tablet", store_name="s", source_id=None, url="https://x")
    assert spec.ram_gb == 12
