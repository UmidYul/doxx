from __future__ import annotations

import os

import orjson
import pytest

pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from psycopg import connect

from domain.scrape_fingerprints import build_product_identity_key
from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.persistence.postgres_store import PostgresScraperStore, apply_postgres_schema

TEST_DSN = os.environ.get("MOSCRAPER_TEST_POSTGRES_DSN", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DSN,
    reason="Set MOSCRAPER_TEST_POSTGRES_DSN to run Postgres-backed persistence tests.",
)


def _snapshot(
    run_id: str,
    *,
    price_str: str = "1000000",
    image_urls: list[str] | None = None,
    raw_specs: dict | None = None,
) -> ScrapedProductSnapshot:
    return ScrapedProductSnapshot.from_scrapy_item(
        {
            "source": "mediapark",
            "url": "https://mediapark.uz/products/view/demo-phone-123",
            "source_id": "123",
            "title": "Demo Phone",
            "price_str": price_str,
            "in_stock": True,
            "brand": "DemoBrand",
            "raw_specs": raw_specs
            or {
                "Color": "Black",
                "Display": {
                    "Size": "6.7 inch",
                    "Resolution": "2400x1080",
                },
            },
            "image_urls": image_urls or ["https://mediapark.uz/img/demo.jpg"],
            "description": "Demo description",
            "category_hint": "phone",
            "external_ids": {"sku": "sku-123"},
        },
        scrape_run_id=run_id,
    )


@pytest.fixture()
def store() -> PostgresScraperStore:
    apply_postgres_schema(TEST_DSN)
    with connect(TEST_DSN, autocommit=True) as connection:
        connection.execute(
            """
            truncate table
                scraper.publication_attempts,
                scraper.publication_outbox,
                scraper.raw_product_specs,
                scraper.raw_product_images,
                scraper.raw_products,
                scraper.scrape_runs
            restart identity cascade
            """
        )
    store = PostgresScraperStore(TEST_DSN)
    try:
        yield store
    finally:
        store.close()


def _register_run(store: PostgresScraperStore, *, run_id: str = "mediapark:test-run") -> str:
    store.register_scrape_run(
        scrape_run_id=run_id,
        store_name="mediapark",
        spider_name="mediapark",
        category_urls=["https://mediapark.uz/products/category/phones"],
    )
    return run_id


def test_persist_snapshot_writes_raw_product_images_specs_and_outbox(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)

    persisted = store.persist_snapshot(
        _snapshot(run_id),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    run_row = store.get_scrape_run_row(run_id)
    assert run_row is not None
    assert run_row["run_id"] == run_id
    assert run_row["store_name"] == "mediapark"

    product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key="mediapark:123")
    assert product_row is not None
    assert product_row["store_name"] == "mediapark"
    assert product_row["source_id"] == "123"
    assert product_row["publication_state"] == "pending"
    structured_payload = orjson.loads(str(product_row["structured_payload_json"]))
    assert structured_payload["raw_specs"]["Color"] == "Black"
    assert structured_payload["image_urls"] == ["https://mediapark.uz/img/demo.jpg"]

    images = store.get_raw_product_images(persisted.raw_product_id)
    assert [row["image_url"] for row in images] == ["https://mediapark.uz/img/demo.jpg"]
    assert [row["position"] for row in images] == [0]

    specs = store.get_raw_product_specs(persisted.raw_product_id)
    spec_pairs = {(row["source_section"], row["spec_name"], row["spec_value"]) for row in specs}
    assert (None, "Color", "Black") in spec_pairs
    assert ("Display", "Size", "6.7 inch") in spec_pairs
    assert ("Display", "Resolution", "2400x1080") in spec_pairs

    outbox_row = store.get_outbox_row(persisted.event_id)
    assert outbox_row is not None
    assert outbox_row["raw_product_id"] == persisted.raw_product_id
    assert outbox_row["status"] == "pending"
    payload = orjson.loads(str(outbox_row["payload_json"]))
    assert payload["event_id"] == persisted.event_id
    assert payload["structured_payload"]["payload_hash"] == persisted.payload_hash


def test_duplicate_same_source_id_updates_existing_row_and_replaces_children(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)

    first = store.persist_snapshot(
        _snapshot(
            run_id,
            price_str="1000000",
            image_urls=["https://mediapark.uz/img/old.jpg"],
            raw_specs={"Color": "Black", "Memory": "128 GB"},
        ),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )
    second = store.persist_snapshot(
        _snapshot(
            run_id,
            price_str="1200000",
            image_urls=["https://mediapark.uz/img/new-1.jpg", "https://mediapark.uz/img/new-2.jpg"],
            raw_specs={"Color": "Blue", "Memory": "256 GB"},
        ),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    assert second.raw_product_id == first.raw_product_id
    assert second.event_id == first.event_id

    product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key="mediapark:123")
    assert product_row is not None
    assert product_row["price_raw"] == "1200000"
    assert product_row["payload_hash"] == second.payload_hash

    images = store.get_raw_product_images(second.raw_product_id)
    assert [row["image_url"] for row in images] == [
        "https://mediapark.uz/img/new-1.jpg",
        "https://mediapark.uz/img/new-2.jpg",
    ]

    outbox_row = store.get_outbox_row(second.event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "pending"
    payload = orjson.loads(str(outbox_row["payload_json"]))
    assert payload["structured_payload"]["price_raw"] == "1200000"


def test_missing_source_id_uses_canonical_url_identity_and_stable_event_id(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)

    first = store.persist_snapshot(
        ScrapedProductSnapshot.from_scrapy_item(
            {
                "source": "mediapark",
                "url": "https://Mediapark.uz/products/view/demo-phone/?utm=ad",
                "title": "Demo Phone",
                "price_str": "1000000",
                "in_stock": True,
                "raw_specs": {"Color": "Black"},
                "image_urls": ["https://mediapark.uz/img/demo.jpg"],
            },
            scrape_run_id=run_id,
        ),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )
    second = store.persist_snapshot(
        ScrapedProductSnapshot.from_scrapy_item(
            {
                "source": "mediapark",
                "url": "https://mediapark.uz/products/view/demo-phone/",
                "title": "Demo Phone",
                "price_str": "1000000",
                "in_stock": True,
                "raw_specs": {"Color": "Blue"},
                "image_urls": ["https://mediapark.uz/img/demo.jpg"],
            },
            scrape_run_id=run_id,
        ),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    assert first.raw_product_id == second.raw_product_id
    assert first.event_id == second.event_id

    expected_identity = build_product_identity_key(
        "mediapark",
        None,
        "https://mediapark.uz/products/view/demo-phone/",
    )
    product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key=expected_identity)
    assert product_row is not None
    assert product_row["source_id"] is None
    assert product_row["source_url"] == "https://mediapark.uz/products/view/demo-phone/"


def test_claim_outbox_batch_leases_rows_and_respects_expired_leases(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)
    persisted = store.persist_snapshot(
        _snapshot(run_id),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    claimed = store.claim_outbox_batch(batch_size=10, publisher_id="publisher", lease_seconds=30)
    assert len(claimed) == 1
    assert claimed[0].event_id == persisted.event_id
    assert store.has_claimable_outbox_rows() is False

    with connect(TEST_DSN, autocommit=True) as connection:
        connection.execute(
            """
            update scraper.publication_outbox
               set lease_expires_at = now() - interval '1 second'
             where event_id = %s
            """,
            (persisted.event_id,),
        )

    assert store.has_claimable_outbox_rows() is True
    reclaimed = store.claim_outbox_batch(batch_size=10, publisher_id="publisher-2", lease_seconds=30)
    assert len(reclaimed) == 1
    assert reclaimed[0].event_id == persisted.event_id

    outbox_row = store.get_outbox_row(persisted.event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "leased"


def test_mark_outbox_failed_sets_retryable_status_and_attempt_history(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)
    persisted = store.persist_snapshot(
        _snapshot(run_id),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    claimed = store.claim_outbox_batch(batch_size=10, publisher_id="publisher", lease_seconds=30)
    assert len(claimed) == 1

    store.mark_outbox_failed(
        event_id=persisted.event_id,
        publisher_id="publisher",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
        error_message="temporary network issue",
        retryable=True,
    )

    outbox_row = store.get_outbox_row(persisted.event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "retryable"
    assert outbox_row["retry_count"] == 1

    attempts = store.get_publication_attempts(int(outbox_row["id"]))
    assert len(attempts) == 1
    assert attempts[0]["success"] is False
    assert attempts[0]["error_message"] == "temporary network issue"


def test_mark_outbox_published_and_requeue_function(store: PostgresScraperStore) -> None:
    run_id = _register_run(store)
    persisted = store.persist_snapshot(
        _snapshot(run_id),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    claimed = store.claim_outbox_batch(batch_size=10, publisher_id="publisher", lease_seconds=30)
    delivery_event = claimed[0].payload.model_copy(
        update={
            "publication": claimed[0].payload.publication.model_copy(
                update={
                    "exchange_name": "moscraper.events",
                    "queue_name": "scraper.products.v1",
                    "routing_key": "listing.scraped.v1",
                    "outbox_status": "published",
                    "attempt_number": 1,
                    "publisher_service": "publisher",
                    "published_at": "2026-04-03T12:00:16Z",
                }
            )
        }
    )
    store.mark_outbox_published(
        event_id=persisted.event_id,
        publisher_id="publisher",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
        published_event=delivery_event,
    )

    outbox_row = store.get_outbox_row(persisted.event_id)
    assert outbox_row is not None
    assert outbox_row["status"] == "published"

    with connect(TEST_DSN, autocommit=True) as connection:
        row = connection.execute(
            "select scraper.requeue_outbox(%s, %s, %s, %s, %s)",
            (persisted.event_id, None, None, ["published"], 1),
        ).fetchone()

    assert row is not None
    assert int(row[0]) == 1
    replayed = store.get_outbox_row(persisted.event_id)
    assert replayed is not None
    assert replayed["status"] == "pending"
