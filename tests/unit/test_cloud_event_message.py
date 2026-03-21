from __future__ import annotations

from datetime import UTC, datetime

import orjson

from domain.message import CloudEvent, ProductData


def test_cloud_event_orjson_roundtrip_shape():
    data = ProductData(
        schema_version=1,
        entity_key="mediapark:1",
        payload_hash="sha256:" + "a" * 64,
        store="mediapark",
        url="https://mediapark.uz/p/1",
        title="Phone",
        scraped_at=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
        source_id="1",
        price_raw="10 сум",
        price_value=10,
        currency="UZS",
        in_stock=True,
        raw_specs={"ram_gb": "8"},
        image_urls=["https://cdn.example/i.jpg"],
    )
    ev = CloudEvent(source="moscraper://mediapark", data=data)
    raw = orjson.dumps(ev.model_dump(mode="json"))
    out = orjson.loads(raw)
    assert out["specversion"] == "1.0"
    assert out["type"] == "com.moscraper.listing.scraped"
    assert out["source"] == "moscraper://mediapark"
    assert out["datacontenttype"] == "application/json"
    assert out["data"]["title"] == "Phone"
    assert out["data"]["entity_key"] == "mediapark:1"
    assert "id" in out and len(out["id"]) == 36
    assert "time" in out and out["time"].endswith("Z")
