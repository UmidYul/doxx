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


def test_phone_string_fields_are_cleaned_and_canonicalized():
    raw = {
        "\u043f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440": "\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440: A17 Pro",
        "\u043e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430": "\u041e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430: Android 14",
        "\u0442\u0438\u043f \u044d\u043a\u0440\u0430\u043d\u0430": "\u0422\u0438\u043f \u044d\u043a\u0440\u0430\u043d\u0430: AMOLED",
        "\u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u044d\u043a\u0440\u0430\u043d\u0430": "1920*1080",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("processor") == "Apple A17 Pro"
    assert d.get("os") == "Android 14"
    assert d.get("display_type") == "AMOLED"
    assert d.get("display_resolution") == "1920x1080"


def test_laptop_gpu_unknown_string_not_forced_into_typed():
    raw = {"\u0432\u0438\u0434\u0435\u043e\u043a\u0430\u0440\u0442\u0430": "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "laptop", store_name="s", source_id=None, url="https://x")
    assert spec.gpu is None


def test_appliance_energy_class_string_is_canonicalized():
    raw = {"\u044d\u043d\u0435\u0440\u0433\u043e\u043a\u043b\u0430\u0441\u0441": "a++"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "appliance", store_name="s", source_id=None, url="https://x")
    assert spec.energy_class == "A++"


def test_phone_live_store_aliases_map_to_existing_typed_fields():
    raw = {
        "\u0432\u0435\u0440\u0441\u0438\u044f \u043e\u0441 \u043d\u0430 \u043d\u0430\u0447\u0430\u043b\u043e \u043f\u0440\u043e\u0434\u0430\u0436": "Android 14",
        "\u0440\u0430\u0437\u043c\u0435\u0440 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f": "2400 x 1080",
        "\u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442 Bluetooth": "5.3",
        "\u0442\u0438\u043f \u043c\u0430\u0442\u0440\u0438\u0446\u044b \u044d\u043a\u0440\u0430\u043d\u0430": "AMOLED",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="mediapark", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("os") == "Android 14"
    assert d.get("display_resolution") == "2400x1080"
    assert d.get("has_bluetooth") is True
    assert d.get("display_type") == "AMOLED"


def test_phone_live_store_escaped_label_artifact_still_maps():
    raw = {"\u0415\u043c\u043a\u043e\u0441\u0442\u044c \u0430\u043a\u043a\u0443\u043c\u0443\u043b\u044f\u0442\u043e\u0440\u0430\\t": "5000 mAh"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="mediapark", source_id=None, url="https://x")
    assert spec.battery_mah == 5000


def test_tv_live_store_aliases_map_to_existing_typed_fields():
    raw = {
        "\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 Smart TV": "\u0414\u0430",
        "\u0442\u0438\u043f \u0434\u0438\u0441\u043f\u043b\u0435\u044f": "QLED",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "tv", store_name="texnomart", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("smart_tv") is True
    assert d.get("display_type") == "QLED"


def test_phone_connectivity_versions_map_to_boolean_fields():
    raw = {
        "\u0432\u0435\u0440\u0441\u0438\u044f bluetooth": "5.3",
        "\u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442 wi-fi": "802.11 a/b/g/n/ac",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("has_bluetooth") is True
    assert d.get("has_wifi") is True


def test_phone_connectivity_bundle_maps_to_wifi_and_bluetooth():
    raw = {
        "\u0431\u0435\u0441\u043f\u0440\u043e\u0432\u043e\u0434\u043d\u044b\u0435 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u044b": "Wi-Fi, Bluetooth 5.3"
    }
    spec, _, meta = map_raw_specs_to_typed_partial(
        raw, "phone", store_name="s", source_id=None, url="https://x"
    )
    d = spec.to_compact_dict()
    assert d.get("has_bluetooth") is True
    assert d.get("has_wifi") is True
    assert meta.get("mapped_fields_count") == 1


def test_phone_nfc_does_not_map_to_bluetooth():
    raw = {"nfc": "\u0434\u0430"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.has_bluetooth is None


def test_tv_hdmi_unknown_not_forced_true():
    raw = {"hdmi": "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "tv", store_name="s", source_id=None, url="https://x")
    assert spec.hdmi is None


def test_appliance_numeric_ranges_not_forced_into_typed_specs():
    raw = {
        "\u043c\u043e\u0449\u043d\u043e\u0441\u0442\u044c": "20-30 W",
        "\u043e\u0431\u044a\u0435\u043c": "12-15 l",
    }
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "appliance", store_name="s", source_id=None, url="https://x")
    d = spec.to_compact_dict()
    assert d.get("power_w") is None
    assert d.get("volume_l") is None


def test_appliance_volume_ml_maps_to_litres():
    raw = {"\u043e\u0431\u044a\u0435\u043c": "500 ml"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "appliance", store_name="s", source_id=None, url="https://x")
    assert spec.volume_l == 0.5


def test_phone_storage_composite_not_forced_into_typed_specs():
    raw = {"\u0432\u0441\u0442\u0440\u043e\u0435\u043d\u043d\u0430\u044f \u043f\u0430\u043c\u044f\u0442\u044c": "8 GB + 256 GB"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.storage_gb is None


def test_phone_battery_composite_not_forced_into_typed_specs():
    raw = {"\u0435\u043c\u043a\u043e\u0441\u0442\u044c \u0430\u043a\u043a\u0443\u043c\u0443\u043b\u044f\u0442\u043e\u0440\u0430": "5000/6000 mAh"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.battery_mah is None


def test_phone_weight_composite_not_forced_into_typed_specs():
    raw = {"weight_g": "190/210 g"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.weight_g is None


def test_phone_display_dimension_not_forced_into_size():
    raw = {"\u044d\u043a\u0440\u0430\u043d": "2400x1080"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.display_size_inch is None


def test_phone_refresh_rate_range_not_forced_into_typed_specs():
    raw = {"\u0447\u0430\u0441\u0442\u043e\u0442\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u044d\u043a\u0440\u0430\u043d\u0430": "60-120 Hz"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.refresh_rate_hz is None


def test_phone_camera_bundle_not_forced_into_main_camera():
    raw = {"\u043a\u0430\u043c\u0435\u0440\u0430": "50+12 MP"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "phone", store_name="s", source_id=None, url="https://x")
    assert spec.main_camera_mp is None


def test_common_warranty_range_not_forced_into_months():
    raw = {"\u0433\u0430\u0440\u0430\u043d\u0442\u0438\u044f": "12/24 months"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "appliance", store_name="s", source_id=None, url="https://x")
    assert spec.warranty_months is None


def test_laptop_battery_wh_composite_not_forced_into_typed_specs():
    raw = {"\u0431\u0430\u0442\u0430\u0440\u0435\u044f wh": "56/70 Wh"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "laptop", store_name="s", source_id=None, url="https://x")
    assert spec.battery_wh is None


def test_laptop_weight_composite_not_forced_into_typed_specs():
    raw = {"weight_kg": "1.9/2.1 kg"}
    spec, _, _ = map_raw_specs_to_typed_partial(raw, "laptop", store_name="s", source_id=None, url="https://x")
    assert spec.weight_kg is None


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
