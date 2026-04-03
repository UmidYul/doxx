from __future__ import annotations

from datetime import UTC, datetime

from config.settings import settings
from domain.publication_event import PublicationMetadata, ScraperProductEvent, ScrapedProductPayload
from domain.scraped_product import ScrapedProductSnapshot


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_scraper_product_event(
    snapshot: ScrapedProductSnapshot,
    *,
    event_id: str,
    event_type: str,
    exchange_name: str,
    routing_key: str,
    created_at: datetime | None = None,
) -> ScraperProductEvent:
    created = created_at or utcnow()
    product = ScrapedProductPayload(
        store_name=snapshot.store_name,
        source_url=snapshot.source_url,
        source_id=snapshot.source_id,
        title=snapshot.title,
        brand=snapshot.brand,
        price_raw=snapshot.price_raw,
        in_stock=snapshot.in_stock,
        raw_specs=dict(snapshot.raw_specs),
        image_urls=list(snapshot.image_urls),
        description=snapshot.description,
        category_hint=snapshot.category_hint,
        external_ids=dict(snapshot.external_ids),
        scraped_at=snapshot.scraped_at,
        payload_hash=snapshot.payload_hash,
        raw_payload_snapshot=dict(snapshot.raw_payload),
        scrape_run_id=snapshot.scrape_run_id,
        identity_key=snapshot.identity_key,
    )
    publication = PublicationMetadata(
        publication_version=int(settings.MESSAGE_SCHEMA_VERSION),
        exchange_name=exchange_name,
        queue_name=settings.RABBITMQ_QUEUE,
        routing_key=routing_key,
        outbox_created_at=created,
    )
    return ScraperProductEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version=int(settings.MESSAGE_SCHEMA_VERSION),
        store_name=snapshot.store_name,
        source_id=snapshot.source_id,
        source_url=snapshot.source_url,
        scrape_run_id=snapshot.scrape_run_id,
        scraped_at=snapshot.scraped_at,
        payload_hash=snapshot.payload_hash,
        structured_payload=product,
        publication=publication,
    )
