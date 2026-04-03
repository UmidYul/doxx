from __future__ import annotations

from pathlib import Path

import scrapy.http

from application.ingestion.persistence_service import ScraperPersistenceService
from infrastructure.spiders.mediapark import MediaparkSpider
from infrastructure.persistence.sqlite_store import SQLiteScraperStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "stores" / "mediapark"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _response(name: str, *, url: str, status: int = 200) -> scrapy.http.HtmlResponse:
    request = scrapy.Request(url=url)
    return scrapy.http.HtmlResponse(url=url, request=request, status=status, body=_read(name), encoding="utf-8")


def test_mediapark_listing_discovers_pdp_urls_nested_categories_and_next_page():
    spider = MediaparkSpider()
    response = _response(
        "listing_good.html",
        url="https://mediapark.uz/products/category/telefony-17/smartfony-40?page=1",
    )

    product_urls = spider.extract_listing_product_urls(response)
    category_urls = spider.extract_listing_category_urls(response)
    next_page_url = spider.extract_next_page_url(response)

    assert len(product_urls) >= 3
    assert all("/products/view/" in url for url in product_urls)
    assert "/products/category/smartfony-po-brendu-660/smartfony-samsung-210" in category_urls
    assert "/products/category/smartfony-po-brendu-660/smartfony-apple-iphone-211" in category_urls
    assert next_page_url == "https://mediapark.uz/products/category/telefony-17/smartfony-40?page=2"


def test_mediapark_pdp_parser_returns_stable_fields_and_source_id():
    spider = MediaparkSpider()
    response = _response(
        "pdp_phone_reference.html",
        url="https://mediapark.uz/products/view/apple-iphone-15-pro-999001",
    )

    raw = spider.full_parse_item(response)

    assert raw is not None
    assert raw["source"] == "mediapark"
    assert raw["source_id"] == "999001"
    assert raw["url"] == response.url
    assert raw["title"] == "Apple iPhone 15 Pro"
    assert raw["brand"] == "Apple"
    assert raw["price_str"] == "14999000"
    assert raw["in_stock"] is True
    assert raw["category_hint"] == "phone"
    assert raw["description"] == "Reference MediaPark phone fixture"
    assert raw["image_urls"]
    assert "Память" in raw["raw_specs"]
    assert raw["raw_specs"]["Память"] == "256 GB"


def test_mediapark_valid_pdp_is_not_dropped_by_soft_404_text_inside_scripts():
    spider = MediaparkSpider()
    body = """
    <html>
      <head>
        <meta property="og:title" content="Demo Phone | MediaPark" />
        <meta property="product:price:amount" content="10999000" />
        <meta property="og:image" content="https://mediapark.uz/images/demo-phone.jpg" />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Demo Phone",
            "description": "Demo MediaPark PDP",
            "image": ["https://mediapark.uz/images/demo-phone.jpg"],
            "brand": {"@type": "Brand", "name": "DemoBrand"},
            "offers": {
              "@type": "Offer",
              "price": "10999000",
              "availability": "https://schema.org/InStock"
            },
            "additionalProperty": [
              {"name": "Memory", "value": "256 GB"}
            ]
          }
        </script>
        <script>
          window.__noise = "Страница не найдена";
        </script>
      </head>
      <body>
        <h1>Demo Phone</h1>
        <p>Valid PDP body content</p>
      </body>
    </html>
    """.encode("utf-8")
    response = scrapy.http.HtmlResponse(
        url="https://mediapark.uz/products/view/demo-phone-123456",
        body=body,
        encoding="utf-8",
    )

    raw = spider.full_parse_item(response)

    assert raw is not None
    assert raw["source_id"] == "123456"
    assert raw["title"] == "Demo Phone"
    assert raw["price_str"] == "10999000"
    assert raw["image_urls"]
    assert raw["raw_specs"]["Memory"] == "256 GB"


def test_mediapark_specs_and_images_cover_reference_sample_items():
    spider = MediaparkSpider()
    responses = [
        _response(
            "pdp_full.html",
            url="https://mediapark.uz/products/view/samsung-tv-777",
        ),
        _response(
            "pdp_phone_reference.html",
            url="https://mediapark.uz/products/view/apple-iphone-15-pro-999001",
        ),
    ]

    parsed = []
    for response in responses:
        parsed.extend(list(spider.parse_product(response)))

    assert len(parsed) == 2
    assert sum(1 for item in parsed if item.get("raw_specs")) >= 2
    assert sum(1 for item in parsed if item.get("image_urls")) >= 2

    metrics = spider.crawl_registry.snapshot_metrics()
    assert metrics["products_with_specs_total"] >= 2
    assert metrics["products_with_images_total"] >= 2
    assert metrics["spec_coverage_ratio"] == 1.0
    assert metrics["image_coverage_ratio"] == 1.0


def test_mediapark_parsed_item_persists_to_scraper_db_and_outbox(tmp_path: Path):
    spider = MediaparkSpider()
    response = _response(
        "pdp_phone_reference.html",
        url="https://mediapark.uz/products/view/apple-iphone-15-pro-999001",
    )
    raw = spider.full_parse_item(response)
    assert raw is not None

    store = SQLiteScraperStore(tmp_path / "scraper.db")
    service = ScraperPersistenceService(store=store)
    run_id = "mediapark:acceptance-run"
    service.start_run(
        scrape_run_id=run_id,
        store_name="mediapark",
        spider_name="mediapark",
        category_urls=list(spider.start_category_urls()),
    )

    persisted = service.persist_item(
        raw,
        scrape_run_id=run_id,
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key="mediapark:999001")
    assert product_row is not None
    assert product_row["store_name"] == "mediapark"
    assert product_row["source_id"] == "999001"
    assert product_row["category_hint"] == "phone"
    assert product_row["publication_state"] == "pending"

    images = store.get_raw_product_images(persisted.raw_product_id)
    specs = store.get_raw_product_specs(persisted.raw_product_id)
    outbox_row = store.get_outbox_row(persisted.event_id)

    assert len(images) >= 1
    assert len(specs) >= 1
    assert outbox_row is not None
    assert outbox_row["status"] == "pending"
    assert outbox_row["raw_product_id"] == persisted.raw_product_id
