from __future__ import annotations

import pytest

from application.normalization.light_normalizer import (
    build_external_ids,
    derive_category_hint,
    extract_barcode,
    extract_brand_from_raw_specs,
    extract_compatibility_targets,
    extract_model_name,
    extract_model_name_from_raw_specs,
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


def test_normalize_price_value_rejects_installment_text():
    assert normalize_price_value("\u043e\u0442 100 000 \u0441\u0443\u043c/\u043c\u0435\u0441") is None


def test_normalize_price_value_rejects_range_text():
    assert normalize_price_value("100 000 - 120 000 \u0441\u0443\u043c") is None


def test_normalize_price_value_rejects_old_and_new_price_text():
    assert normalize_price_value("\u0431\u044b\u043b\u043e 200 000, \u0441\u0442\u0430\u043b\u043e 150 000 \u0441\u0443\u043c") is None


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


@pytest.mark.parametrize(
    ("url", "title"),
    [
        ("https://shop.uz/p/chehol-dlya-iphone-15", "Чехол для iPhone 15 Pro Max"),
        ("https://shop.uz/p/iphone-15-case", "Case for Samsung Galaxy S24"),
        ("https://shop.uz/p/charger-iphone-15", "Зарядка для iPhone 15"),
        ("https://shop.uz/p/steklo-iphone-15", "Защитное стекло для iPhone 15"),
        ("https://shop.uz/p/plenka-samsung-galaxy-s24", "Пленка для Samsung Galaxy S24"),
        ("https://shop.uz/p/apple-watch-series-9", "Apple Watch Series 9"),
    ],
)
def test_accessory_signals_override_phone_spider_hint(url: str, title: str):
    assert derive_category_hint(url, title, {}, spider_hint=None) == "accessory"
    assert derive_category_hint(url, title, {}, spider_hint="phone") == "accessory"


def test_accessory_raw_specs_override_phone_spider_hint():
    assert (
        derive_category_hint(
            "https://shop.uz/p/demo-item",
            "Apple Series 9",
            {"Тип устройства": "smart watch"},
            spider_hint="phone",
        )
        == "accessory"
    )


def test_phone_title_beats_accessoryish_raw_spec_labels():
    assert (
        derive_category_hint(
            "https://shop.uz/p/smartfon-honor-200-pro",
            "Smartfon HONOR 200 PRO 12/512 Cyan Blue",
            {
                "charger type": "USB Type-C",
                "wireless interfaces": "Wi-Fi, Bluetooth 5.3",
            },
            spider_hint=None,
        )
        == "phone"
    )


def test_accessoryish_raw_spec_labels_do_not_override_phone_spider_hint():
    assert (
        derive_category_hint(
            "https://shop.uz/p/model-x",
            "Model X",
            {
                "charger type": "USB Type-C",
                "wireless interfaces": "Wi-Fi, Bluetooth 5.3",
            },
            spider_hint="phone",
        )
        == "phone"
    )


def test_extract_model_name_strips_brand_and_noise():
    m = extract_model_name("Samsung Galaxy S24 Ultra 256GB", brand="Samsung", category_hint="phone")
    assert m is not None
    assert "S24" in m or "Ultra" in m
    assert "Samsung" not in m


def test_extract_model_name_returns_none_for_accessory_compatibility_title():
    assert extract_model_name("Чехол для iPhone 15 Pro Max", brand="Apple", category_hint="accessory") is None


def test_extract_model_name_keeps_watch_model_for_accessory():
    assert extract_model_name("Apple Watch Series 9", brand="Apple", category_hint="accessory") == "Watch Series 9"


def test_extract_model_name_keeps_headphone_model_for_accessory():
    assert extract_model_name("Sony WH-1000XM5", brand="Sony", category_hint="accessory") == "WH-1000XM5"


def test_extract_brand_from_raw_specs():
    assert extract_brand_from_raw_specs({"Brand": "Spigen"}) == "Spigen"


def test_extract_brand_from_raw_specs_supports_manufacturer_label():
    assert extract_brand_from_raw_specs({"Manufacturer": "Sony"}) == "Sony"


def test_extract_model_name_from_raw_specs_for_accessory():
    assert (
        extract_model_name_from_raw_specs(
            {"Model": "Sony WH-1000XM5"},
            brand="Sony",
            category_hint="accessory",
        )
        == "WH-1000XM5"
    )


def test_extract_model_name_from_raw_specs_ignores_compatibility_target_for_accessory():
    assert (
        extract_model_name_from_raw_specs(
            {"Model": "Galaxy S24"},
            brand="Spigen",
            category_hint="accessory",
            compatibility_targets=["Samsung Galaxy S24", "Galaxy S24"],
        )
        is None
    )


def test_extract_compatibility_targets_for_accessory_title():
    assert extract_compatibility_targets("Case for Samsung Galaxy S24", category_hint="accessory") == [
        "Samsung Galaxy S24"
    ]


def test_extract_compatibility_targets_splits_multi_model_tail():
    assert extract_compatibility_targets(
        "Spigen Rugged Armor for iPhone 15, 15 Pro, 15 Pro Max",
        category_hint="accessory",
    ) == ["iPhone 15", "15 Pro", "15 Pro Max"]


def test_extract_compatibility_targets_keeps_plus_model_suffix():
    assert extract_compatibility_targets(
        "Case for Samsung Galaxy S24+",
        category_hint="accessory",
    ) == ["Samsung Galaxy S24+"]


def test_extract_compatibility_targets_from_raw_specs_for_generic_accessory_title():
    assert extract_compatibility_targets(
        "Spigen Rugged Armor",
        category_hint="accessory",
        raw_specs={"Compatible with": "Samsung Galaxy S24, Galaxy S24+"},
    ) == ["Samsung Galaxy S24", "Galaxy S24+"]


def test_extract_compatibility_targets_combines_title_and_raw_specs_without_duplicates():
    assert extract_compatibility_targets(
        "Case for Samsung Galaxy S24",
        category_hint="accessory",
        raw_specs={"Compatible with": "Samsung Galaxy S24; Galaxy S24+"},
    ) == ["Samsung Galaxy S24", "Galaxy S24+"]


def test_extract_compatibility_targets_empty_for_non_compatibility_accessory():
    assert extract_compatibility_targets("Apple Watch Series 9", category_hint="accessory") == []


def test_extract_compatibility_targets_empty_for_non_accessory_title():
    assert extract_compatibility_targets("Samsung Galaxy S24", category_hint="phone") == []


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


def test_normalize_stock_v_nalichii():
    assert normalize_stock_value("в наличии") is True


def test_normalize_stock_net_v_nalichii():
    assert normalize_stock_value("нет в наличии") is False


def test_normalize_stock_ambiguous_phrase_is_unknown():
    assert normalize_stock_value("уточняйте наличие") is None
