from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, Field, PlainSerializer


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_serialize_datetime, return_type=str, when_used="json")]


class _UtcModel(BaseModel):
    pass


class ScrapedProductPayload(_UtcModel):
    store_name: str
    source_url: str
    source_id: str | None = None
    title: str
    brand: str | None = None
    price_raw: str | None = None
    in_stock: bool | None = None
    raw_specs: dict[str, Any] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    description: str | None = None
    category_hint: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    scraped_at: UtcDateTime
    payload_hash: str
    raw_payload_snapshot: dict[str, Any] = Field(default_factory=dict)
    scrape_run_id: str
    identity_key: str


class PublicationMetadata(_UtcModel):
    publication_version: int = Field(
        default=1,
        validation_alias=AliasChoices("publication_version", "contract_version"),
        serialization_alias="publication_version",
    )
    exchange_name: str | None = None
    queue_name: str | None = None
    routing_key: str | None = None
    outbox_status: str = "pending"
    attempt_number: int = 0
    publisher_service: str | None = None
    outbox_created_at: UtcDateTime
    published_at: UtcDateTime | None = None

    @property
    def contract_version(self) -> int:
        return self.publication_version


class ScraperProductEvent(_UtcModel):
    event_id: str
    event_type: str
    schema_version: int = 1
    store_name: str
    source_id: str | None = None
    source_url: str
    scrape_run_id: str
    scraped_at: UtcDateTime
    payload_hash: str
    structured_payload: ScrapedProductPayload = Field(
        validation_alias=AliasChoices("structured_payload", "product"),
        serialization_alias="structured_payload",
    )
    publication: PublicationMetadata

    @property
    def product(self) -> ScrapedProductPayload:
        return self.structured_payload
