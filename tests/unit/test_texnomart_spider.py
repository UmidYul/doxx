from __future__ import annotations

import scrapy

from infrastructure.spiders import edge_cases
from infrastructure.spiders.texnomart import TexnomartSpider
from infrastructure.performance.resource_tracker import (
    build_runtime_state,
    increment_inflight_request,
    reset_resource_tracker_for_tests,
)


def test_texnomart_sitemap_iterator_keeps_only_product_urls() -> None:
    spider = TexnomartSpider()
    xml = """
    <urlset>
      <url><loc>https://texnomart.uz/katalog/smartfony/</loc></url>
      <url><loc>https://texnomart.uz/product/detail/355737/</loc></url>
      <url><loc>https://texnomart.uz/ru/product/detail/355737/</loc></url>
      <url><loc>https://texnomart.uz/product/detail/357998/</loc></url>
      <url><loc>https://example.com/product/detail/1/</loc></url>
    </urlset>
    """

    urls = list(spider._iter_product_urls_from_sitemap(xml))

    assert urls == [
        "https://texnomart.uz/product/detail/355737/",
        "https://texnomart.uz/product/detail/357998/",
    ]


def test_texnomart_sitemap_callback_releases_listing_governance(monkeypatch) -> None:
    reset_resource_tracker_for_tests()
    spider = TexnomartSpider()
    increment_inflight_request("texnomart", "listing")

    monkeypatch.setattr(spider, "schedule_safe_request", lambda *args, **kwargs: None)
    response = scrapy.http.HtmlResponse(
        url=spider.product_sitemap_url,
        request=scrapy.Request(
            spider.product_sitemap_url,
            meta={"_resource_gov": {"purpose": "listing", "mode": "plain"}},
        ),
        body=b"<urlset></urlset>",
    )

    list(spider.parse_product_sitemap(response))

    state = build_runtime_state("texnomart")
    assert state.inflight_requests == 0
    assert state.inflight_listing_requests == 0


def test_texnomart_parse_product_sitemap_seeds_in_memory_queue(monkeypatch) -> None:
    spider = TexnomartSpider()
    scheduled: list[str] = []

    def _fake_schedule(url: str, **kwargs):
        scheduled.append(url)
        if len(scheduled) > 2:
            return None
        return scrapy.Request(url, callback=kwargs["callback"], meta=kwargs.get("meta") or {})

    monkeypatch.setattr(spider, "schedule_safe_request", _fake_schedule)
    response = scrapy.http.HtmlResponse(
        url=spider.product_sitemap_url,
        request=scrapy.Request(spider.product_sitemap_url),
        body=b"""
        <urlset>
          <url><loc>https://texnomart.uz/product/detail/1001/</loc></url>
          <url><loc>https://texnomart.uz/product/detail/1002/</loc></url>
          <url><loc>https://texnomart.uz/product/detail/1003/</loc></url>
        </urlset>
        """,
    )

    outputs = list(spider.parse_product_sitemap(response))

    assert len(outputs) == 2
    queue, seen = spider._pending_sitemap_product_queue()
    assert list(queue) == [
        (
            "https://texnomart.uz/product/detail/1003/",
            {
                "category_url": spider.product_sitemap_url,
                "from_listing": spider.product_sitemap_url,
                "discovery_mode": "sitemap",
            },
        )
    ]
    assert seen == {"https://texnomart.uz/product/detail/1003/"}


def test_texnomart_parse_product_drains_pending_queue(monkeypatch) -> None:
    spider = TexnomartSpider()
    spider._texnomart_sitemap_seeded = True
    queue, seen = spider._pending_sitemap_product_queue()
    queue.append(
        (
            "https://texnomart.uz/product/detail/2001/",
            {
                "category_url": spider.product_sitemap_url,
                "from_listing": spider.product_sitemap_url,
                "discovery_mode": "sitemap",
            },
        )
    )
    seen.add("https://texnomart.uz/product/detail/2001/")

    def _fake_schedule(url: str, **kwargs):
        return scrapy.Request(url, callback=kwargs["callback"], meta=kwargs.get("meta") or {})

    monkeypatch.setattr(spider, "schedule_safe_request", _fake_schedule)
    response = scrapy.http.HtmlResponse(
        url="https://texnomart.uz/product/detail/355737/",
        request=scrapy.Request("https://texnomart.uz/product/detail/355737/"),
        body=b"""
        <html><head><title>Phone</title></head><body>
        <script type="application/ld+json">
        {"@type":"Product","name":"Demo Phone","sku":"355737","offers":{"price":"4999000","availability":"https://schema.org/InStock"}}
        </script>
        </body></html>
        """,
        encoding="utf-8",
    )

    outputs = list(spider.parse_product(response))
    requests = [item for item in outputs if isinstance(item, scrapy.Request)]

    assert len(requests) == 1
    assert requests[0].url == "https://texnomart.uz/product/detail/2001/"
    assert not queue
    assert not seen


def test_texnomart_faq_ld_price_fallback_avoids_partial_price_loss() -> None:
    spider = TexnomartSpider()
    response = scrapy.http.HtmlResponse(
        url="https://texnomart.uz/ru/product/detail/357182/",
        request=scrapy.Request("https://texnomart.uz/ru/product/detail/357182/"),
        body="""
        <html>
          <head>
            <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Demo Vacuum",
                "sku": "357182",
                "description": "Demo Vacuum so&#x27;mdan boshlab",
                "offers": {"@type": "Offer", "availability": "https://schema.org/InStock"},
                "image": ["https://cdn.example.com/demo.jpg"],
                "additionalProperty": [
                  {"name": "Power", "value": "1800 W"}
                ]
              }
            </script>
            <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                  {
                    "@type": "Question",
                    "name": "Price",
                    "acceptedAnswer": {
                      "@type": "Answer",
                      "text": "Стоимость Demo Vacuum составляет 6999000 сум. Актуально сейчас."
                    }
                  }
                ]
              }
            </script>
          </head>
          <body><h1>Demo Vacuum</h1></body>
        </html>
        """.encode("utf-8"),
        encoding="utf-8",
    )

    raw = spider.full_parse_item(response)

    assert raw is not None
    assert raw["price_str"].startswith("6999000")

    tags = edge_cases.classify_product_edge_case(raw, response)
    assert edge_cases.EDGE_MISSING_PRICE not in tags
    assert edge_cases.EDGE_PARTIAL_PRODUCT not in tags
