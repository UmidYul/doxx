from __future__ import annotations

from unittest.mock import MagicMock

from domain.normalized_product import NormalizedProduct
from domain.raw_product import RawProduct, as_scrapy_item_dict
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


def test_normalize_pipeline_raw_product_preserves_string_stock_signal():
    item = as_scrapy_item_dict(
        {
            "source": "s",
            "url": "https://x",
            "source_id": "1",
            "title": "T",
            "price_str": "100 \u0441\u0443\u043c",
            "in_stock": "\u043d\u0435\u0442",
            "raw_specs": {},
            "image_urls": [],
        }
    )
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


def test_normalize_pipeline_accessory_title_overrides_phone_hint():
    item = {
        "source": "s",
        "url": "https://x/p/iphone-15-case",
        "title": "Case for Samsung Galaxy S24",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "phone",
        "brand": "Samsung",
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["category_hint"] == "accessory"
    assert item["_normalized"]["model_name"] is None


def test_normalize_pipeline_accessory_policy_rejects_phone_like_typed_specs():
    item = {
        "source": "s",
        "url": "https://x/p/iphone-15-case",
        "title": "Case for iPhone 15 Pro Max",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "accessory",
        "raw_specs": {
            "\u041e\u0417\u0423": "8 GB",
            "\u041f\u0430\u043c\u044f\u0442\u044c": "256 GB",
            "\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440": "Snapdragon 8 Gen 3",
        },
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    typed = item["_normalized"]["typed_specs"]
    assert "ram_gb" not in typed
    assert "storage_gb" not in typed
    assert "processor" not in typed
