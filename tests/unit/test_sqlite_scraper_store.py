from __future__ import annotations

from pathlib import Path

import orjson

from domain.scraped_product import ScrapedProductSnapshot
from infrastructure.persistence.sqlite_store import SQLiteScraperStore


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


def _store(tmp_path: Path) -> tuple[SQLiteScraperStore, str]:
    db_path = tmp_path / "scraper.db"
    store = SQLiteScraperStore(db_path)
    run_id = "mediapark:test-run"
    store.register_scrape_run(
        scrape_run_id=run_id,
        store_name="mediapark",
        spider_name="mediapark",
        category_urls=["https://mediapark.uz/products/category/phones"],
    )
    return store, run_id


def test_persist_snapshot_writes_raw_product_images_specs_and_outbox(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)

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
    assert product_row["raw_payload_json"]
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
    assert outbox_row["retry_count"] == 0
    payload = orjson.loads(str(outbox_row["payload_json"]))
    assert payload["event_id"] == persisted.event_id
    assert payload["structured_payload"]["payload_hash"] == persisted.payload_hash


def test_duplicate_same_source_id_updates_existing_row_and_replaces_children(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)

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
            image_urls=[
                "https://mediapark.uz/img/new-1.jpg",
                "https://mediapark.uz/img/new-2.jpg",
            ],
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
    assert product_row["publication_state"] == "pending"
    assert product_row["payload_hash"] == second.payload_hash

    images = store.get_raw_product_images(second.raw_product_id)
    assert [row["image_url"] for row in images] == [
        "https://mediapark.uz/img/new-1.jpg",
        "https://mediapark.uz/img/new-2.jpg",
    ]

    specs = store.get_raw_product_specs(second.raw_product_id)
    assert {(row["spec_name"], row["spec_value"]) for row in specs} == {
        ("Color", "Blue"),
        ("Memory", "256 GB"),
    }

    outbox_row = store.get_outbox_row(second.event_id)
    assert outbox_row is not None
    assert outbox_row["payload_hash"] == second.payload_hash
    assert outbox_row["status"] == "pending"
    payload = orjson.loads(str(outbox_row["payload_json"]))
    assert payload["structured_payload"]["price_raw"] == "1200000"


def test_mark_outbox_failed_sets_retryable_status_and_attempt_history(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    persisted = store.persist_snapshot(
        _snapshot(run_id),
        event_type="scraper.product.scraped.v1",
        exchange_name="moscraper.events",
        routing_key="listing.scraped.v1",
    )

    claimed = store.claim_outbox_batch(batch_size=10, publisher_id="publisher", lease_seconds=30)
    assert len(claimed) == 1
    assert claimed[0].event_id == persisted.event_id

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

    product_row = store.get_snapshot_row(scrape_run_id=run_id, identity_key="mediapark:123")
    assert product_row is not None
    assert product_row["publication_state"] == "retryable"

    attempts = store.get_publication_attempts(int(outbox_row["id"]))
    assert len(attempts) == 1
    assert attempts[0]["success"] == 0
    assert attempts[0]["error_message"] == "temporary network issue"
