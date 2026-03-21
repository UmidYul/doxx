from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer


class ListingScrapedData(BaseModel):
    """Business payload inside CloudEvents `data` (CRM contract)."""

    schema_version: int
    entity_key: str
    payload_hash: str
    store: str
    url: str
    title: str
    scraped_at: datetime
    source_id: str | None = None
    price_raw: str | None = None
    price_value: int | None = None
    currency: str | None = None
    in_stock: bool | None = None
    brand: str | None = None
    raw_specs: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)

    @field_serializer("scraped_at")
    def _dt(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        s = v.isoformat().replace("+00:00", "Z")
        return s


class CloudEventListingScraped(BaseModel):
    """CloudEvents v1.0-compatible envelope for listing.scraped."""

    specversion: Literal["1.0"] = "1.0"
    type: Literal["com.moscraper.listing.scraped"] = "com.moscraper.listing.scraped"
    source: str
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    datacontenttype: Literal["application/json"] = "application/json"
    subject: str = "listing"
    data: ListingScrapedData

    @field_serializer("time")
    def _time(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat().replace("+00:00", "Z")
