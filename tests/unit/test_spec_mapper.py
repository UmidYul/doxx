from __future__ import annotations

from unittest.mock import MagicMock

from application.extractors.spec_mapper import map_raw_specs_to_typed_partial
from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_phone_raw_specs_to_typed():
    raw = {
        "оперативная память": "8 GB",
        "встроенная память": "256 GB",
        "ёмкость аккумулятора": "5000 mAh",
    }
    spec, warnings, _meta = map_raw_specs_to_typed_partial(
        raw, "phone", store_name="s", source_id="1", url="https://x"
    )
    d = spec.to_compact_dict()
    assert d.get("ram_gb") == 8
    assert d.get("storage_gb") == 256
    assert d.get("battery_mah") == 5000
    assert not warnings or "implausible" not in " ".join(warnings).lower()


def test_laptop_prefers_weight_kg_alias():
    raw = {"вес": "2.1 кг", "оперативная память": "16 GB"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "laptop", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("ram_gb") == 16
    assert d.get("weight_kg") == 2.1


def test_tv_display_and_smart_tv():
    raw = {
        "диагональ экрана": '55"',
        "разрешение экрана": "3840x2160",
        "smart tv": "Android TV",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "tv", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("display_size_inch") == 55.0
    assert d.get("display_resolution") == "3840x2160"
    assert d.get("smart_tv") is True


def test_implausible_battery_warning_not_in_typed():
    raw = {"ёмкость аккумулятора": "220 mAh"}
    spec, warnings, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.to_compact_dict().get("battery_mah") is None
    assert "implausible_value" in warnings


def test_ram_routes_to_storage_with_warning():
    raw = {"оперативная память": "512 GB"}
    spec, warnings, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("storage_gb") == 512
    assert d.get("ram_gb") is None
    assert "ram_storage_swap_suspected" in warnings


def test_conflicting_weight_units_clears_typed():
    raw = {"weight_g": "200 g", "weight_kg": "5 kg"}
    item = {
        "source": "s",
        "url": "https://x",
        "title": "Laptop",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "laptop",
        "raw_specs": raw,
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    d = item["_normalized"]["typed_specs"]
    assert "weight_kg" not in d and "weight_g" not in d
    assert "inconsistent_weight_units" in item["_normalized"]["normalization_warnings"]


def test_unknown_drops_non_common_typed_field():
    raw = {"hdmi_count": "3"}
    spec, warnings, _ = map_raw_specs_to_typed_partial(raw, "unknown", store_name="s", source_id=None, url="https://x")
    assert "hdmi_count" not in spec.to_compact_dict()
    assert "category_mismatch" in warnings


def test_tablet_maps_like_phone_ram_storage():
    raw = {"оперативная память": "12 GB", "встроенная память": "256 GB"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "tablet", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("ram_gb") == 12
    assert d.get("storage_gb") == 256
