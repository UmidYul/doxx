from __future__ import annotations

from application.extractors.spec_mapper import map_raw_specs_to_typed_partial


def test_mediapark_override_maps_operativ_volume_label():
    raw = {"объем оперативной памяти": "8 GB"}
    spec, _, meta = map_raw_specs_to_typed_partial(
        raw, "phone", store_name="mediapark", source_id=None, url="https://x"
    )
    assert spec.ram_gb == 8
    assert meta["mapped_fields_count"] >= 1


def test_uzum_memory_maps_to_storage():
    raw = {"memory": "256 GB"}
    spec, _, _ = map_raw_specs_to_typed_partial(
        raw, "phone", store_name="uzum", source_id=None, url="https://x"
    )
    assert spec.storage_gb == 256


def test_uzum_disables_hdmi_for_tv():
    raw = {"hdmi": "да"}
    spec, warnings, _ = map_raw_specs_to_typed_partial(
        raw, "tv", store_name="uzum", source_id=None, url="https://x"
    )
    assert spec.hdmi is None
    assert "field_disabled_by_store_override" in warnings


def test_uzum_does_not_break_common_for_other_store():
    raw = {"hdmi": "да"}
    spec, _, _ = map_raw_specs_to_typed_partial(
        raw, "tv", store_name="mediapark", source_id=None, url="https://x"
    )
    assert spec.hdmi is True
