from __future__ import annotations

from unittest.mock import MagicMock

from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_hybrid_payload_has_raw_and_typed_specs():
    item = {
        "source": "mediapark",
        "url": "https://mediapark.uz/p/1",
        "title": "Смартфон Samsung Galaxy",
        "source_id": "99",
        "price_str": "1000 сум",
        "in_stock": True,
        "brand": "Samsung",
        "raw_specs": {
            "оперативная память": "8 GB",
            "встроенная память": "128 GB",
        },
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="mediapark"))
    n = item["_normalized"]
    assert n["raw_specs"]["оперативная память"] == "8 GB"
    assert n["typed_specs"].get("ram_gb") == 8
    assert n["typed_specs"].get("storage_gb") == 128
    assert isinstance(n["normalization_warnings"], list)
    assert "spec_coverage" in n
    assert n["spec_coverage"].get("mapping_ratio") is not None


def test_raw_specs_preserved_when_typed_mapping_empty():
    item = {
        "source": "s",
        "url": "https://x/y",
        "title": "Mystery",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {"weird_label_only": "123"},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    n = item["_normalized"]
    assert n["raw_specs"] == {"weird_label_only": "123"}
    assert n["typed_specs"] == {}
