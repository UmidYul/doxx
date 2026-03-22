from __future__ import annotations

import pytest

from application.normalization.light_normalizer import (
    build_external_ids,
    derive_category_hint,
    extract_barcode,
    extract_model_name,
    normalize_image_urls,
    normalize_price_value,
    normalize_stock_value,
    normalize_title_whitespace,
    sanitize_raw_specs,
)


def test_normalize_title_whitespace():
    assert normalize_title_whitespace("  a   b  ") == "a b"
    assert normalize_title_whitespace(None) == ""


def test_normalize_price_value_spaces_and_currency():
    assert normalize_price_value("12 999 000 сум") == 12999000


def test_normalize_price_value_po_zaprosu():
    assert normalize_price_value("по запросу") is None


def test_normalize_price_value_zero():
    assert normalize_price_value("0") is None


def test_normalize_stock_false_string():
    assert normalize_stock_value("false") is False


def test_normalize_stock_zero_string():
    assert normalize_stock_value("0") is False


def test_normalize_stock_net():
    assert normalize_stock_value("нет") is False


def test_normalize_stock_true_string():
    assert normalize_stock_value("true") is True


def test_normalize_stock_one_string():
    assert normalize_stock_value("1") is True


def test_normalize_stock_empty_string():
    assert normalize_stock_value("") is None


def test_normalize_stock_none():
    assert normalize_stock_value(None) is None


def test_normalize_stock_bool():
    assert normalize_stock_value(False) is False
    assert normalize_stock_value(True) is True


def test_extract_barcode_from_specs():
    assert extract_barcode({"EAN": "5901234123457"}) == "5901234123457"
    assert extract_barcode({"штрихкод": "  12345670  "}) == "12345670"


def test_extract_barcode_rejects_garbage_length():
    assert extract_barcode({"barcode": "12345"}) is None
    assert extract_barcode({"barcode": "12345678901234567890"}) is None


def test_build_external_ids():
    assert build_external_ids("mediapark", "sku-1") == {"mediapark": "sku-1"}
    assert build_external_ids("mediapark", None) == {}
    assert build_external_ids("mediapark", "   ") == {}


def test_tablet_not_classified_as_phone():
    assert derive_category_hint(
        "https://shop.uz/tablets/ipad",
        "Apple iPad Air",
        {},
        spider_hint=None,
    ) == "tablet"


def test_extract_model_name_strips_brand_and_noise():
    m = extract_model_name("Samsung Galaxy S24 Ultra 256GB", brand="Samsung", category_hint="phone")
    assert m is not None
    assert "S24" in m or "Ultra" in m
    assert "Samsung" not in m


def test_normalize_image_urls_dedup_and_order():
    assert normalize_image_urls([" https://a/x.jpg ", "https://b/y.jpg", "https://a/x.jpg"]) == [
        "https://a/x.jpg",
        "https://b/y.jpg",
    ]


def test_normalize_image_urls_max_ten():
    urls = [f"https://x/{i}.jpg" for i in range(15)]
    assert len(normalize_image_urls(urls)) == 10


def test_sanitize_raw_specs_trims_and_drops_empty():
    assert sanitize_raw_specs({"  a  ": "  b  ", "": "x", "k": ""}) == {"a": "b"}


def test_sanitize_raw_specs_non_dict():
    assert sanitize_raw_specs("nope") == {}


def test_sanitize_raw_specs_truncates_long_value():
    long_val = "x" * 600
    out = sanitize_raw_specs({"k": long_val})
    assert len(out["k"]) == 500
