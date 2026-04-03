from __future__ import annotations

import pytest

from domain.raw_product import RawProduct, as_scrapy_item_dict


def test_raw_product_excludes_raw_html():
    assert "raw_html" not in RawProduct.model_fields


def test_raw_product_dump_has_no_raw_html(sample_raw_product: RawProduct):
    assert "raw_html" not in sample_raw_product.model_dump()


def test_as_scrapy_item_dict_matches_raw_product_shape():
    d = as_scrapy_item_dict(
        {
            "source": "mediapark",
            "url": "https://mediapark.uz/p/1",
            "source_id": "99",
            "title": "Phone",
            "name": "ignored when title set",
            "price_str": "10",
            "in_stock": True,
            "raw_specs": {"a": "b"},
            "image_urls": ["https://i/x.jpg"],
            "description": "d",
            "category_hint": "phone",
            "external_ids": {"sku": "sku-1"},
        }
    )
    RawProduct.model_validate(d)
    assert d["source_id"] == "99"
    assert d["category_hint"] == "phone"
    assert d["external_ids"] == {"sku": "sku-1", "mediapark": "99"}
    assert "_category_hint" not in d["raw_specs"]


def test_as_scrapy_item_dict_requires_source_and_url():
    with pytest.raises(ValueError, match="source"):
        as_scrapy_item_dict({"title": "x"})
