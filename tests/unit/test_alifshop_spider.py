from __future__ import annotations

from infrastructure.spiders.alifshop import AlifshopSpider


def test_start_category_urls_include_home_and_laptops() -> None:
    spider = AlifshopSpider()
    urls = spider.start_category_urls()
    assert "https://alifshop.uz/ru" in urls
    assert "https://alifshop.uz/ru/categories/noutbuki-i-kompjyuteri" in urls
    assert "https://alifshop.uz/ru/categories/tv-i-proektori" in urls


def test_allowed_category_path_accepts_tech_and_blocks_noise() -> None:
    assert AlifshopSpider._is_allowed_category_path("/ru/categories/vse-noutbuki")
    assert AlifshopSpider._is_allowed_category_path("/ru/categories/televizori-i-proektori")
    assert not AlifshopSpider._is_allowed_category_path("/ru/categories/knigi")
    assert not AlifshopSpider._is_allowed_category_path("/ru/categories/chehli-dlya-smartfonov")
