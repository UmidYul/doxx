from __future__ import annotations

from unittest.mock import MagicMock

from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_normalized_payload_includes_quality_metadata():
    item = {
        "source": "s",
        "url": "https://x/p",
        "title": "P",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {"оперативная память": "8 GB"},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    n = item["_normalized"]
    assert "field_confidence" in n
    assert "suppressed_typed_fields" in n
    assert "normalization_quality" in n
    assert n["raw_specs"]["оперативная память"] == "8 GB"


def test_raw_specs_preserved_when_typed_display_suppressed_for_phone():
    item = {
        "source": "s",
        "url": "https://x/p",
        "title": "Phone",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "phone",
        "raw_specs": {'диагональ экрана': '55"'},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    n = item["_normalized"]
    assert n["raw_specs"].get('диагональ экрана')
    assert "display_size_inch" not in (n.get("typed_specs") or {})
