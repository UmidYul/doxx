from __future__ import annotations

from application.governance.code_placement import decide_code_placement, get_responsibility_areas


def test_placement_pdp_to_spider() -> None:
    d = decide_code_placement("PDP price extraction", "parse product detail HTML for one store")
    assert d.recommended_layer == "infrastructure"
    assert "spiders" in d.recommended_module


def test_placement_lifecycle() -> None:
    d = decide_code_placement("lifecycle selection", "choose product_found vs update for replay")
    assert d.recommended_layer == "application"
    assert "lifecycle" in d.recommended_module


def test_responsibility_areas_non_empty() -> None:
    areas = get_responsibility_areas()
    assert len(areas) >= 5
    assert any(a.name == "pydantic_contracts" for a in areas)
