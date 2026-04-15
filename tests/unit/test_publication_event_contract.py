from __future__ import annotations

from datetime import UTC, datetime

import pytest

from domain.publication_event import PublicationMetadata, ScrapedProductPayload, ScraperProductEvent


def _event() -> ScraperProductEvent:
    now = datetime(2026, 4, 12, 8, 0, 0, tzinfo=UTC)
    payload_hash = "sha256:test-hash"
    return ScraperProductEvent(
        event_id="11111111-2222-3333-4444-555555555555",
        event_type="scraper.product.scraped.v1",
        schema_version=1,
        scrape_run_id="uzum:run-20260412-0001",
        store_name="uzum",
        source_id="sku:9434915",
        source_url="https://uzum.uz/ru/product/example?skuId=9434915",
        scraped_at=now,
        payload_hash=payload_hash,
        structured_payload=ScrapedProductPayload(
            store_name="uzum",
            source_url="https://uzum.uz/ru/product/example?skuId=9434915",
            source_id="sku:9434915",
            title="Redmi Note 14",
            brand="Redmi",
            price_raw="1969000 сум",
            in_stock=True,
            raw_specs={"Цвет": "Фиолетовый"},
            image_urls=["https://images.uzum.uz/example-1.jpg"],
            description="Описание товара",
            category_hint="phone",
            external_ids={"uzum": "sku:9434915"},
            scraped_at=now,
            payload_hash=payload_hash,
            raw_payload_snapshot={"source": "uzum"},
            scrape_run_id="uzum:run-20260412-0001",
            identity_key="uzum:sku:9434915",
        ),
        publication=PublicationMetadata(
            publication_version=1,
            exchange_name="moscraper.events",
            queue_name="scraper.products.v1",
            routing_key="listing.scraped.v1",
            outbox_status="published",
            attempt_number=1,
            publisher_service="publisher-service",
            outbox_created_at=now,
            published_at=datetime(2026, 4, 12, 8, 0, 1, 123000, tzinfo=UTC),
        ),
    )


def test_publish_contract_accepts_final_event() -> None:
    _event().assert_rabbit_publish_contract()


def test_publish_contract_rejects_cross_field_drift() -> None:
    event = _event()
    drifted = event.model_copy(
        update={
            "structured_payload": event.structured_payload.model_copy(
                update={"payload_hash": "sha256:other"}
            )
        }
    )

    with pytest.raises(ValueError, match="structured_payload.payload_hash"):
        drifted.assert_rabbit_publish_contract()


def test_publish_contract_requires_final_publication_fields() -> None:
    event = _event()
    broken = event.model_copy(
        update={
            "publication": event.publication.model_copy(
                update={
                    "outbox_status": "pending",
                    "publisher_service": None,
                    "published_at": None,
                }
            )
        }
    )

    with pytest.raises(ValueError, match="publication.outbox_status"):
        broken.assert_rabbit_publish_contract()
