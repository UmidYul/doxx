from __future__ import annotations

from unittest.mock import MagicMock

from domain.normalized_product import NormalizedProduct
from domain.raw_product import RawProduct
from infrastructure.pipelines.normalize_pipeline import NormalizePipeline


def test_normalize_pipeline_raw_product_shape():
    raw = RawProduct(
        source="mediapark",
        url="https://example.com/p",
        source_id="1",
        title="Phone",
        price_str="1 234 000 сум",
        in_stock=True,
        raw_specs={"ram_gb": "8"},
        image_urls=[],
        description="",
    )
    pipe = NormalizePipeline()
    item = raw.model_dump()
    out = pipe.process_item(item, MagicMock(store_name="mediapark"))
    assert out is item
    norm = item["_normalized"]
    NormalizedProduct.model_validate(norm)
    assert norm["title"] == "Phone"
    assert norm["title_clean"] == "Phone"
    assert norm["price_raw"] == "1 234 000 сум"
    assert norm["price_value"] == 1234000
    assert "price" not in norm
    assert norm["currency"] == "UZS"
    assert norm["in_stock"] is True
    assert norm["raw_specs"] == {"ram_gb": "8"}
    assert norm["external_ids"] == {"mediapark": "1"}
    assert "typed_specs" in norm
    assert norm["typed_specs"].get("ram_gb") == 8
    assert norm["normalization_warnings"] == []


def test_normalize_pipeline_optional_price_and_false_stock():
    raw = RawProduct(
        source="s",
        url="https://x",
        source_id="",
        title="T",
        price_str="",
        in_stock=False,
    )
    pipe = NormalizePipeline()
    item = raw.model_dump()
    pipe.process_item(item, MagicMock(store_name="s"))
    n = item["_normalized"]
    assert n["price_value"] is None
    assert n["in_stock"] is False


def test_normalize_pipeline_string_in_stock_normalized():
    item = {
        "source": "s",
        "url": "https://x",
        "title": "T",
        "source_id": "1",
        "price_str": "100 сум",
        "in_stock": "false",
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["in_stock"] is False


def test_normalize_pipeline_category_from_spider_category():
    item = {
        "source": "s",
        "url": "https://x/phones/",
        "title": "Device",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category": "планшеты",
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["category_hint"] == "tablet"


def test_normalize_pipeline_barcode_extracted():
    item = {
        "source": "s",
        "url": "https://x",
        "title": "T",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {"GTIN": "5901234123457"},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["barcode"] == "5901234123457"
