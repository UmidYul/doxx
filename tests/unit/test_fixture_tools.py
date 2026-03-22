from __future__ import annotations

from pathlib import Path

from tests.helpers import fixture_tools


def test_list_available_store_fixtures() -> None:
    xs = fixture_tools.list_available_store_fixtures()
    assert any("fixtures/regression/normalization" in x for x in xs)
    mp = fixture_tools.list_available_store_fixtures("mediapark")
    assert mp


def test_load_fixture_json_and_summary() -> None:
    root = Path(__file__).resolve().parents[1]
    rel = "fixtures/regression/normalization/laptop.json"
    data = fixture_tools.load_fixture_json(str(root / rel))
    assert "raw_item" in data
    summ = fixture_tools.build_fixture_summary(str(root / rel))
    assert summ.get("store_hint") == "mediapark"
    assert "size_bytes" in summ
