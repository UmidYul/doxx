from __future__ import annotations

from application.extractors.unit_normalizer import (
    normalize_battery,
    normalize_battery_wh,
    normalize_camera_mp,
    normalize_display,
    normalize_int_field,
    normalize_power_w,
    normalize_refresh_rate,
    normalize_resolution,
    normalize_storage,
    normalize_volume_l,
    normalize_warranty_months,
    normalize_weight_g,
    normalize_weight_kg,
)


def test_normalize_power_w_rejects_range() -> None:
    assert normalize_power_w("20-30 W") is None


def test_normalize_power_w_rejects_multiple_watt_values() -> None:
    assert normalize_power_w("USB PD 20W + 15W") is None


def test_normalize_power_w_keeps_single_explicit_power() -> None:
    assert normalize_power_w("220-240V, 50Hz, 2000W") == 2000


def test_normalize_volume_l_rejects_range() -> None:
    assert normalize_volume_l("12-15 l") is None
    assert normalize_volume_l("\u043e\u0431\u044a\u0435\u043c 12/15 \u043b") is None


def test_normalize_volume_l_converts_ml_to_litres() -> None:
    assert normalize_volume_l("500 ml") == 0.5


def test_normalize_volume_l_keeps_plain_litre_value() -> None:
    assert normalize_volume_l("1.5 \u043b") == 1.5


def test_normalize_storage_rejects_composite_values() -> None:
    assert normalize_storage("256/512 GB") is None
    assert normalize_storage("8 GB + 256 GB") is None


def test_normalize_storage_keeps_single_explicit_value() -> None:
    assert normalize_storage("PCIe 4.0 NVMe 512 GB") == 512
    assert normalize_storage("ROM 128") == 128


def test_normalize_battery_rejects_composite_values() -> None:
    assert normalize_battery("5000/6000 mAh") is None
    assert normalize_battery("5000 + 1200 mAh") is None


def test_normalize_battery_keeps_single_explicit_value() -> None:
    assert normalize_battery("Li-Po 5000 mAh") == 5000
    assert normalize_battery("Battery 5000") == 5000


def test_normalize_battery_wh_rejects_composite_values() -> None:
    assert normalize_battery_wh("56/70 Wh") is None
    assert normalize_battery_wh("56 Wh + 70 Wh") is None


def test_normalize_battery_wh_keeps_single_explicit_value() -> None:
    assert normalize_battery_wh("56 Wh") == 56.0
    assert normalize_battery_wh("56.5 Wh") == 56.5


def test_normalize_weight_g_rejects_composite_values() -> None:
    assert normalize_weight_g("190/210 g") is None
    assert normalize_weight_g("0.19 kg / 190 g") is None


def test_normalize_weight_g_keeps_single_explicit_value() -> None:
    assert normalize_weight_g("0.19 kg") == 190
    assert normalize_weight_g("190 g") == 190


def test_normalize_weight_kg_rejects_composite_values() -> None:
    assert normalize_weight_kg("1.9/2.1 kg") is None
    assert normalize_weight_kg("1.9 + 0.2 kg") is None


def test_normalize_weight_kg_keeps_single_explicit_value() -> None:
    assert normalize_weight_kg("1900 g") == 1.9
    assert normalize_weight_kg("1.9 kg") == 1.9


def test_normalize_display_rejects_composite_sizes_and_dimensions() -> None:
    assert normalize_display("6.1/6.7 inch") is None
    assert normalize_display("2400x1080") is None


def test_normalize_display_keeps_single_size_signal() -> None:
    assert normalize_display("15.6") == 15.6
    assert normalize_display("164 cm") == 64.6
    assert normalize_display('6.7" / 17 cm') == 6.7


def test_normalize_camera_mp_rejects_composite_values() -> None:
    assert normalize_camera_mp("50+12 MP") is None
    assert normalize_camera_mp("main 50 / front 16 MP") is None


def test_normalize_camera_mp_keeps_single_explicit_value() -> None:
    assert normalize_camera_mp("108 MP, f/1.8") == 108
    assert normalize_camera_mp("Camera 64") == 64


def test_normalize_warranty_months_rejects_ambiguous_ranges() -> None:
    assert normalize_warranty_months("12/24 months") is None
    assert normalize_warranty_months("up to 24 months") is None


def test_normalize_warranty_months_keeps_single_explicit_value() -> None:
    assert normalize_warranty_months("2 years") == 24
    assert normalize_warranty_months("24") == 24


def test_normalize_resolution_canonicalizes_multiplication_variants() -> None:
    assert normalize_resolution("2400 x 1080") == "2400x1080"
    assert normalize_resolution("1920*1080") == "1920x1080"
    assert normalize_resolution("3840×2160") == "3840x2160"


def test_normalize_refresh_rate_rejects_ambiguous_values() -> None:
    assert normalize_refresh_rate("60-120 Hz") is None
    assert normalize_refresh_rate("48/60/120 Hz") is None
    assert normalize_refresh_rate("up to 120 Hz") is None


def test_normalize_refresh_rate_keeps_single_explicit_value() -> None:
    assert normalize_refresh_rate("VRR 120 Hz") == 120
    assert normalize_refresh_rate("120") == 120


def test_normalize_int_field_rejects_ranges_and_versions() -> None:
    assert normalize_int_field("2-3") is None
    assert normalize_int_field("HDMI 2.1") is None
    assert normalize_int_field("v2.0") is None


def test_normalize_int_field_accepts_count_patterns() -> None:
    assert normalize_int_field("2") == 2
    assert normalize_int_field("USB-C x2") == 2
    assert normalize_int_field("3 ports") == 3
