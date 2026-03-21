from __future__ import annotations

from datetime import UTC, datetime

import pytest

from application.message_builder import build_entity_key, build_listing_event, build_payload_hash


def test_entity_key_with_source_id():
    assert build_entity_key("mediapark", "123", "https://x/y") == "mediapark:123"


def test_entity_key_without_source_id_stable():
    k1 = build_entity_key("mediapark", None, "https://Mediapark.uz/path/?q=1")
    k2 = build_entity_key("mediapark", "", "https://mediapark.uz/path/")
    assert k1 == k2
    assert k1.startswith("mediapark:")


def test_payload_hash_stable():
    when = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)
    h1 = build_payload_hash(
        schema_version=1,
        store="mediapark",
        url="https://example.com/p",
        title="Phone",
        scraped_at=when,
        source_id="1",
        price_raw="1 sum",
        price_value=1,
        currency="UZS",
        in_stock=True,
        brand="X",
        raw_specs={"a": "b"},
        description="d",
        image_urls=["https://i/x.jpg"],
    )
    h2 = build_payload_hash(
        schema_version=1,
        store="mediapark",
        url="https://example.com/p",
        title="Phone",
        scraped_at=when,
        source_id="1",
        price_raw="1 sum",
        price_value=1,
        currency="UZS",
        in_stock=True,
        brand="X",
        raw_specs={"a": "b"},
        description="d",
        image_urls=["https://i/x.jpg"],
    )
    assert h1 == h2
    assert h1.startswith("sha256:")


@pytest.mark.parametrize("extra", [{"price_value": 2}, {"title": "Other"}])
def test_payload_hash_changes(extra):
    base = dict(
        schema_version=1,
        store="mediapark",
        url="https://example.com/p",
        title="Phone",
        scraped_at=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
        source_id="1",
        price_raw="1 sum",
        price_value=1,
        currency="UZS",
        in_stock=True,
        brand="X",
        raw_specs={},
        description=None,
        image_urls=[],
    )
    h0 = build_payload_hash(**base)
    base.update(extra)
    assert build_payload_hash(**base) != h0


def test_build_listing_event_validates():
    ev = build_listing_event(
        store="mediapark",
        url="https://mediapark.uz/x",
        title="  Test  ",
        source_id="99",
        price_raw="10 сум",
        price_value=10,
    )
    assert ev.specversion == "1.0"
    assert ev.type == "com.moscraper.listing.scraped"
    assert ev.data.title == "Test"
    assert ev.data.entity_key == "mediapark:99"
    assert ev.data.payload_hash.startswith("sha256:")
