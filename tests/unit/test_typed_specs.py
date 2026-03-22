from __future__ import annotations

from domain.typed_specs import TypedPartialSpecs


def test_to_compact_dict_omits_none():
    s = TypedPartialSpecs(ram_gb=8, storage_gb=None, color="Black")
    d = s.to_compact_dict()
    assert d == {"ram_gb": 8, "color": "Black"}
    assert "storage_gb" not in d
    assert "display_size_inch" not in d


def test_model_validate_partial_dict():
    s = TypedPartialSpecs.model_validate({"battery_mah": 5000, "os": "Android"})
    assert s.battery_mah == 5000
    assert s.os == "Android"
    assert s.ram_gb is None
