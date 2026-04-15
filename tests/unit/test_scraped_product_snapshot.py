from __future__ import annotations

from domain.scraped_product import ScrapedProductSnapshot


def test_from_scrapy_item_filters_frontend_noise_and_caps_image_urls() -> None:
    image_urls = [f"https://cdn.example.com/{index}.jpg" for index in range(105)]
    image_urls.extend(["javascript:alert(1)", "not-a-url"])

    snapshot = ScrapedProductSnapshot.from_scrapy_item(
        {
            "source": "mediapark",
            "url": "https://mediapark.uz/products/view/demo-phone-123",
            "source_id": "123",
            "title": "Demo Phone",
            "price_str": "1000000",
            "in_stock": True,
            "raw_specs": {
                "Memory": "256 GB",
                "Hydration": 'self.__next_f.push([1,"bad"])',
                "Nested": {
                    "Color": "Black",
                    "Noise": "window.__NEXT_DATA__ = {}",
                },
                "List": ["OLED", 'self.__next_f.push([1,"bad"])'],
            },
            "image_urls": image_urls,
        },
        scrape_run_id="mediapark:test-run",
    )

    assert snapshot.raw_specs == {
        "Memory": "256 GB",
        "Nested": {"Color": "Black"},
        "List": ["OLED"],
    }
    assert len(snapshot.image_urls) == 100
    assert snapshot.image_urls[0] == "https://cdn.example.com/0.jpg"
    assert snapshot.image_urls[-1] == "https://cdn.example.com/99.jpg"


def test_from_scrapy_item_normalizes_known_stock_strings() -> None:
    unavailable = ScrapedProductSnapshot.from_scrapy_item(
        {
            "source": "mediapark",
            "url": "https://mediapark.uz/products/view/demo-phone-123",
            "source_id": "123",
            "title": "Demo Phone",
            "price_str": "1000000",
            "in_stock": "\u043d\u0435\u0442",
        },
        scrape_run_id="mediapark:test-run",
    )
    available = ScrapedProductSnapshot.from_scrapy_item(
        {
            "source": "mediapark",
            "url": "https://mediapark.uz/products/view/demo-phone-123",
            "source_id": "123",
            "title": "Demo Phone",
            "price_str": "1000000",
            "in_stock": "\u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
        },
        scrape_run_id="mediapark:test-run",
    )

    assert unavailable.in_stock is False
    assert available.in_stock is True
