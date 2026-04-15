from __future__ import annotations

from application.extractors.unit_normalizer import normalize_field_value, normalize_processor


def test_normalize_processor_strips_label_and_applies_alias() -> None:
    assert normalize_processor("\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440: A17 Pro") == "Apple A17 Pro"
    assert normalize_processor("CPU Apple A17 Pro") == "Apple A17 Pro"


def test_normalize_processor_drops_unknown_placeholder() -> None:
    assert normalize_processor("\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e") is None


def test_normalize_gpu_strips_label_and_unknowns() -> None:
    assert normalize_field_value("gpu", "GPU: Adreno 750") == "Adreno 750"
    assert normalize_field_value("gpu", "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e") is None


def test_normalize_os_strips_label_and_canonicalizes_common_values() -> None:
    assert normalize_field_value("os", "\u041e\u043f\u0435\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430: Android 14") == "Android 14"
    assert normalize_field_value("os", "OS: Windows 11 Home") == "Windows 11 Home"
    assert normalize_field_value("os", "\u0431\u0435\u0437 \u043e\u0441") == "No OS"


def test_normalize_display_strings_strip_labels_and_canonicalize() -> None:
    assert normalize_field_value("display_type", "\u0422\u0438\u043f \u044d\u043a\u0440\u0430\u043d\u0430: AMOLED") == "AMOLED"
    assert normalize_field_value("display_tech", "Display tech: Mini LED") == "Mini LED"


def test_normalize_string_fields_use_dedicated_resolution_and_energy_logic() -> None:
    assert normalize_field_value("display_resolution", "1920*1080") == "1920x1080"
    assert normalize_field_value("energy_class", "a++") == "A++"
