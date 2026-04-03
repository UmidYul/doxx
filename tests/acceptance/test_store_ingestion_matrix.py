from __future__ import annotations

from pathlib import Path

import pytest
import scrapy
import scrapy.http

from application.ingestion.persistence_service import ScraperPersistenceService
from infrastructure.spiders.alifshop import AlifshopSpider
from infrastructure.spiders.mediapark import MediaparkSpider
from infrastructure.spiders.texnomart import TexnomartSpider
from infrastructure.spiders.uzum import UzumSpider
from infrastructure.persistence.sqlite_store import SQLiteScraperStore
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import SQLiteOutboxReader
from services.publisher.publication_worker import PublicationWorker

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "stores"


class _StubRabbitPublisher:
    def __init__(self) -> None:
        self.published = []

    async def connect(self) -> None:
        return None

    async def publish(self, event) -> None:
        self.published.append(event)

    async def close(self) -> None:
        return None


_STORE_CASES = {
    "mediapark": {
        "spider_cls": MediaparkSpider,
        "listing_fixture": "mediapark/listing_good.html",
        "listing_url": "https://mediapark.uz/products/category/telefony-17/smartfony-40?page=1",
        "pdp_fixture": "mediapark/pdp_phone_reference.html",
        "pdp_url": "https://mediapark.uz/products/view/apple-iphone-15-pro-999001",
        "expected_source_id": "999001",
        "expected_category_hint": "phone",
    },
    "texnomart": {
        "spider_cls": TexnomartSpider,
        "listing_fixture": "texnomart/listing_good.html",
        "listing_url": "https://texnomart.uz/ru/katalog/smartfony/",
        "pdp_fixture": "texnomart/pdp_full.html",
        "pdp_url": "https://texnomart.uz/ru/product/detail/555666",
        "expected_source_id": "sku:555666",
        "expected_category_hint": "tv",
    },
    "uzum": {
        "spider_cls": UzumSpider,
        "listing_fixture": "uzum/listing_good.html",
        "listing_url": "https://uzum.uz/ru/category/smartfony-12690",
        "pdp_fixture": "uzum/pdp_full.html",
        "pdp_url": "https://uzum.uz/ru/product/demo-phone-111111?skuId=123456",
        "expected_source_id": "sku:123456",
        "expected_category_hint": "phone",
    },
    "alifshop": {
        "spider_cls": AlifshopSpider,
        "listing_fixture": "alifshop/listing_good.html",
        "listing_url": "https://alifshop.uz/ru/categories/smartfoni-apple",
        "pdp_fixture": "alifshop/pdp_full.html",
        "pdp_url": "https://alifshop.uz/ru/moderated-offer/demo-phone-blue-1772002920",
        "expected_source_id": "1772002920",
        "expected_category_hint": "phone",
    },
}


def _read(rel_path: str) -> bytes:
    return (FIXTURES / rel_path).read_bytes()


def _response(rel_path: str, *, url: str, status: int = 200) -> scrapy.http.HtmlResponse:
    request = scrapy.Request(url=url)
    return scrapy.http.HtmlResponse(url=url, request=request, status=status, body=_read(rel_path), encoding="utf-8")


def _publisher_config(tmp_path: Path, store: str) -> PublisherServiceConfig:
    return PublisherServiceConfig(
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        exchange_name="moscraper.events",
        exchange_type="topic",
        queue_name="scraper.products.v1",
        routing_key="listing.scraped.v1",
        publish_mandatory=True,
        batch_size=10,
        lease_seconds=60,
        max_retries=8,
        retry_base_seconds=15,
        poll_interval_seconds=0.1,
        publisher_service_name=f"publisher-{store}",
        scraper_db_path=str(tmp_path / f"{store}.db"),
    )


@pytest.mark.parametrize("store", ["mediapark", "texnomart", "uzum", "alifshop"])
def test_store_listing_and_pdp_cover_core_fields(store: str) -> None:
    case = _STORE_CASES[store]
    spider = case["spider_cls"]()

    listing = _response(case["listing_fixture"], url=case["listing_url"])
    product_urls = spider.extract_listing_product_urls(listing)
    assert len(product_urls) >= 1

    pdp = _response(case["pdp_fixture"], url=case["pdp_url"])
    raw = spider.full_parse_item(pdp)

    assert raw is not None
    assert raw["source"] == store
    assert raw["source_id"] == case["expected_source_id"]
    assert raw["url"] == case["pdp_url"]
    assert raw["category_hint"] == case["expected_category_hint"]
    assert raw["raw_specs"]
    assert raw["image_urls"]


@pytest.mark.asyncio
@pytest.mark.parametrize("store", ["mediapark", "texnomart", "uzum", "alifshop"])
async def test_store_item_persists_to_outbox_and_publishes(store: str, tmp_path: Path) -> None:
    case = _STORE_CASES[store]
    spider = case["spider_cls"]()
    pdp = _response(case["pdp_fixture"], url=case["pdp_url"])
    raw = spider.full_parse_item(pdp)
    assert raw is not None

    config = _publisher_config(tmp_path, store)
    db_path = Path(config.scraper_db_path)
    persistence_store = SQLiteScraperStore(db_path)
    persistence = ScraperPersistenceService(store=persistence_store)
    run_id = f"{store}:acceptance-run"
    persistence.start_run(
        scrape_run_id=run_id,
        store_name=store,
        spider_name=store,
        category_urls=list(spider.start_category_urls()),
    )
    persisted = persistence.persist_item(
        raw,
        scrape_run_id=run_id,
        event_type="scraper.product.scraped.v1",
        exchange_name=config.exchange_name,
        routing_key=config.routing_key,
    )

    product_row = persistence_store.get_snapshot_row(
        scrape_run_id=run_id,
        identity_key=f"{store}:{case['expected_source_id']}",
    )
    assert product_row is not None
    assert product_row["source_id"] == case["expected_source_id"]
    assert product_row["publication_state"] == "pending"

    outbox_row = persistence_store.get_outbox_row(persisted.event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "pending"
    assert persistence_store.get_raw_product_images(persisted.raw_product_id)
    assert persistence_store.get_raw_product_specs(persisted.raw_product_id)

    publisher = _StubRabbitPublisher()
    worker = PublicationWorker(
        config=config,
        outbox_reader=SQLiteOutboxReader(store=persistence_store, config=config),
        rabbit_publisher=publisher,
    )
    result = await worker.run_once()

    assert result.claimed == 1
    assert result.published == 1
    assert len(publisher.published) == 1
    assert publisher.published[0].store_name == store
    assert publisher.published[0].structured_payload.source_id == case["expected_source_id"]

    published_outbox = persistence_store.get_outbox_row(persisted.event_id)
    assert published_outbox is not None
    assert published_outbox["status"] == "published"
