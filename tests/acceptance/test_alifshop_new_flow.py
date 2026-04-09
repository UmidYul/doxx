from __future__ import annotations

import scrapy
import scrapy.http

from infrastructure.spiders.alifshop import AlifshopSpider


def test_alifshop_start_requests_include_product_bearing_category_seeds(monkeypatch):
    spider = AlifshopSpider()

    def _fake_schedule(url, *, callback, meta=None, purpose="listing", priority=0):
        return scrapy.Request(url=url, callback=callback, meta=meta or {}, priority=priority)

    monkeypatch.setattr(spider, "schedule_safe_request", _fake_schedule)

    requests = list(spider.start_requests())
    urls = [req.url for req in requests]

    assert requests
    assert urls[0] == "https://alifshop.uz/ru/categories/smartfoni-apple"
    assert "https://alifshop.uz/ru/categories/smartfoni-vivo" in urls
    assert "https://alifshop.uz/ru/categories/smart-chasi" in urls
    assert "https://alifshop.uz/ru/categories/umnie-koljca" in urls
    assert "https://alifshop.uz/ru/categories/ekshen-kameri" in urls
    assert "https://alifshop.uz/ru/categories/ochki-virtualjnoy-realjnosti" in urls


def test_alifshop_category_filter_keeps_only_product_bearing_tech_branches():
    spider = AlifshopSpider()
    response = scrapy.http.HtmlResponse(
        url="https://alifshop.uz/ru/categories",
        body=b"""
        <html><body>
          <a href="/ru/categories/smart-chasi">smart watches</a>
          <a href="/ru/categories/fitnes-brasleti">fitness bands</a>
          <a href="/ru/categories/umnie-koljca">smart rings</a>
          <a href="/ru/categories/umnie-ochki">smart glasses</a>
          <a href="/ru/categories/ekshen-kameri">action cams</a>
          <a href="/ru/categories/ochki-virtualjnoy-realjnosti">vr</a>
          <a href="/ru/categories/noutbuki-i-kompjyuteri">pc hub</a>
          <a href="/ru/categories/tv-i-proektori">tv hub</a>
          <a href="/ru/categories/chehli-dlya-smartfonov">cases</a>
          <a href="/ru/categories/kabeli">cables</a>
          <a href="/ru/categories/produkti-pitaniya">food</a>
        </body></html>
        """,
        encoding="utf-8",
    )

    categories = spider.extract_listing_category_urls(response)

    assert categories == [
        "/ru/categories/ekshen-kameri",
        "/ru/categories/fitnes-brasleti",
        "/ru/categories/ochki-virtualjnoy-realjnosti",
        "/ru/categories/smart-chasi",
        "/ru/categories/umnie-koljca",
        "/ru/categories/umnie-ochki",
    ]


def test_alifshop_phone_listing_discovers_only_allowed_related_tech_categories():
    spider = AlifshopSpider()
    response = scrapy.http.HtmlResponse(
        url="https://alifshop.uz/ru/categories/smartfoni-apple",
        body=b"""
        <html><body>
          <a href="/ru/categories/smartfoni-vivo">phones</a>
          <a href="/ru/categories/smart-chasi">smart watches</a>
          <a href="/ru/categories/fitnes-brasleti">fitness bands</a>
          <a href="/ru/categories/umnie-ochki">smart glasses</a>
          <a href="/ru/categories/umnie-koljca">smart rings</a>
          <a href="/ru/categories/ekshen-kameri">action cams</a>
          <a href="/ru/categories/noutbuki-i-kompjyuteri">pc hub</a>
          <a href="/ru/categories/kabeli">cables</a>
          <a href="/ru/categories/aksessuari-dlya-telefonov">accessories</a>
        </body></html>
        """,
        encoding="utf-8",
    )

    categories = spider.extract_listing_category_urls(response)

    assert categories == [
        "/ru/categories/ekshen-kameri",
        "/ru/categories/fitnes-brasleti",
        "/ru/categories/smart-chasi",
        "/ru/categories/smartfoni-vivo",
        "/ru/categories/umnie-koljca",
        "/ru/categories/umnie-ochki",
    ]
