from __future__ import annotations

from infrastructure.spiders.field_policy import (
    is_partial_product_item,
    is_usable_product_item,
    missing_required_fields,
    missing_recommended_fields,
)


def test_partial_usable_with_identity_and_title_no_source_id_in_payload():
    item = {
        "title": "Phone",
        "url": "https://shop.uz/p/1",
        "source": "shop",
        "price_str": "",
    }
    assert is_usable_product_item(item)
    assert is_partial_product_item(item)
    assert "price" in missing_recommended_fields(item)


def test_not_usable_without_title_even_with_url():
    item = {"title": "", "url": "https://shop.uz/p/1", "source": "shop"}
    assert not is_usable_product_item(item)
    assert "title" in missing_required_fields(item)


def test_not_usable_without_identity_or_url():
    item = {"title": "X", "url": "", "source": "shop", "source_id": ""}
    assert not is_usable_product_item(item)
    assert "identity" in missing_required_fields(item) or "url" in missing_required_fields(item)


def test_price_value_satisfies_recommended():
    item = {
        "title": "X",
        "url": "https://x",
        "source": "s",
        "price_value": 100,
        "image_urls": ["u"],
        "raw_specs": {"a": "b"},
        "category_hint": "phone",
        "brand": "b",
    }
    assert is_usable_product_item(item)
    assert not is_partial_product_item(item)
