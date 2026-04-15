from __future__ import annotations

import pytest

from infrastructure.spiders.product_classifier import classify_category


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
def test_classify_category_returns_accessory_for_conflicting_accessory_titles(url: str, title: str):
    assert classify_category(url, title) == "accessory"


def test_classify_category_uses_ld_category_as_soft_signal():
    assert classify_category("https://shop.uz/p/demo-phone", "Model X", ld_category="Смартфоны") == "phone"


def test_classify_category_brand_fallback_still_works_for_model_only_title():
    assert classify_category("https://shop.uz/p/samsung-galaxy-a55", "Samsung Galaxy A55") == "phone"
