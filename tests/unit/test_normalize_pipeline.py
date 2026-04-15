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


def test_normalize_pipeline_phone_title_not_downgraded_by_accessoryish_spec_labels():
    item = {
        "source": "s",
        "url": "https://x/p/smartfon-honor-200-pro",
        "title": "Smartfon HONOR 200 PRO 12/512 Cyan Blue",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "phone",
        "raw_specs": {
            "charger type": "USB Type-C",
            "wi-fi": "802.11ax",
            "bluetooth": "5.3",
            "ram_gb": "12 GB",
            "storage_gb": "512 GB",
        },
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    norm = item["_normalized"]
    assert norm["category_hint"] == "phone"
    assert norm["typed_specs"].get("has_wifi") is True
    assert norm["typed_specs"].get("has_bluetooth") is True
    assert norm["typed_specs"].get("ram_gb") == 12
    assert norm["typed_specs"].get("storage_gb") == 512


def test_normalize_pipeline_infers_known_brand_from_title_when_missing():
    item = {
        "source": "s",
        "url": "https://x/p/samsung-galaxy-a55",
        "title": "Samsung Galaxy A55 8/256",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    norm = item["_normalized"]
    assert norm["brand"] == "Samsung"
    assert norm["model_name"] == "A55 8/256"


def test_normalize_pipeline_does_not_invent_brand_from_generic_title():
    item = {
        "source": "s",
        "url": "https://x/p/device",
        "title": "Device X",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    assert item["_normalized"]["brand"] is None


def test_normalize_pipeline_does_not_infer_compatible_brand_for_accessory_title():
    item = {
        "source": "s",
        "url": "https://x/p/case-for-samsung-galaxy-s24",
        "title": "Case for Samsung Galaxy S24",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "raw_specs": {},
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    norm = item["_normalized"]
    assert norm["category_hint"] == "accessory"
    assert norm["brand"] is None
    assert norm["model_name"] is None


def test_normalize_pipeline_infers_brand_and_model_from_explicit_raw_specs():
    item = {
        "source": "s",
        "url": "https://x/p/rugged-armor",
        "title": "Rugged Armor Case",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "accessory",
        "raw_specs": {
            "Brand": "Spigen",
            "Model": "Rugged Armor",
            "Compatible with": "Samsung Galaxy S24",
        },
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    norm = item["_normalized"]
    assert norm["category_hint"] == "accessory"
    assert norm["brand"] == "Spigen"
    assert norm["model_name"] == "Rugged Armor"


def test_normalize_pipeline_does_not_take_compatibility_model_from_raw_specs_as_accessory_model():
    item = {
        "source": "s",
        "url": "https://x/p/clear-case",
        "title": "Clear Case",
        "source_id": "1",
        "price_str": "1",
        "in_stock": True,
        "category_hint": "accessory",
        "raw_specs": {
            "Brand": "Spigen",
            "Model": "Galaxy S24",
            "Compatible with": "Samsung Galaxy S24; Galaxy S24+",
        },
        "image_urls": [],
    }
    NormalizePipeline().process_item(item, MagicMock(store_name="s"))
    norm = item["_normalized"]
    assert norm["brand"] == "Spigen"
    assert norm["model_name"] != "Galaxy S24"
