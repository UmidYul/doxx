from __future__ import annotations

from application.extractors.unit_normalizer import normalize_bool, normalize_field_value


def test_normalize_bool_does_not_treat_wifi_standard_as_true() -> None:
    assert normalize_bool("802.11 a/b/g/n/ac") is None


def test_normalize_field_value_wifi_standard_maps_true() -> None:
    assert normalize_field_value("has_wifi", "802.11 a/b/g/n/ac") is True


def test_normalize_field_value_bluetooth_version_maps_true() -> None:
    assert normalize_field_value("has_bluetooth", "5.3") is True


def test_normalize_field_value_hdmi_unknown_stays_none() -> None:
    assert normalize_field_value("hdmi", "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u043e") is None


def test_normalize_field_value_hdmi_ports_maps_true() -> None:
    assert normalize_field_value("hdmi", "2 ports") is True
