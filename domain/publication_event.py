from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, PlainSerializer

SCRAPER_PRODUCT_EVENT_TYPE = "scraper.product.scraped.v1"
SCRAPER_PRODUCT_SCHEMA_VERSION = 1


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_serialize_datetime, return_type=str, when_used="json")]


class _UtcModel(BaseModel):
    model_config = {"str_strip_whitespace": True}


def _is_valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parts = urlsplit(value)
    return parts.scheme.lower() in {"http", "https"} and bool(parts.netloc)


def _is_non_empty_string(value: object | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


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

    def assert_rabbit_publish_contract(self) -> None:
        errors: list[str] = []
        payload = self.structured_payload
        publication = self.publication

        if not _is_non_empty_string(self.event_id):
            errors.append("event_id must be a non-empty string")
        if self.event_type != SCRAPER_PRODUCT_EVENT_TYPE:
            errors.append(f"event_type must be {SCRAPER_PRODUCT_EVENT_TYPE!r}")
        if self.schema_version != SCRAPER_PRODUCT_SCHEMA_VERSION:
            errors.append(f"schema_version must be {SCRAPER_PRODUCT_SCHEMA_VERSION}")
        if not _is_non_empty_string(self.store_name):
            errors.append("store_name must be a non-empty string")
        if not _is_valid_http_url(self.source_url):
            errors.append("source_url must be a valid http/https URL")
        if not _is_non_empty_string(self.scrape_run_id):
            errors.append("scrape_run_id must be a non-empty string")
        if not _is_non_empty_string(self.payload_hash):
            errors.append("payload_hash must be a non-empty string")

        if payload.store_name != self.store_name:
            errors.append("structured_payload.store_name must match store_name")
        if payload.source_url != self.source_url:
            errors.append("structured_payload.source_url must match source_url")
        if payload.source_id != self.source_id:
            errors.append("structured_payload.source_id must match source_id")
        if payload.scraped_at != self.scraped_at:
            errors.append("structured_payload.scraped_at must match scraped_at")
        if payload.payload_hash != self.payload_hash:
            errors.append("structured_payload.payload_hash must match payload_hash")
        if payload.scrape_run_id != self.scrape_run_id:
            errors.append("structured_payload.scrape_run_id must match scrape_run_id")

        if not _is_non_empty_string(payload.title):
            errors.append("structured_payload.title must be a non-empty string")
        if not isinstance(payload.in_stock, bool):
            errors.append("structured_payload.in_stock must be boolean")
        if not isinstance(payload.raw_specs, dict):
            errors.append("structured_payload.raw_specs must be a JSON object")
        if not isinstance(payload.external_ids, dict):
            errors.append("structured_payload.external_ids must be a JSON object")
        if not _is_non_empty_string(payload.identity_key):
            errors.append("structured_payload.identity_key must be a non-empty string")
        if len(payload.image_urls) > 100:
            errors.append("structured_payload.image_urls must contain at most 100 URLs")
        for index, image_url in enumerate(payload.image_urls):
            if not _is_valid_http_url(image_url):
                errors.append(f"structured_payload.image_urls[{index}] must be a valid http/https URL")

        if publication.publication_version < 1:
            errors.append("publication.publication_version must be >= 1")
        if not _is_non_empty_string(publication.exchange_name):
            errors.append("publication.exchange_name must be a non-empty string")
        if not _is_non_empty_string(publication.queue_name):
            errors.append("publication.queue_name must be a non-empty string")
        if not _is_non_empty_string(publication.routing_key):
            errors.append("publication.routing_key must be a non-empty string")
        if publication.outbox_status != "published":
            errors.append("publication.outbox_status must be 'published' before Rabbit publish")
        if publication.attempt_number < 0:
            errors.append("publication.attempt_number must be >= 0")
        if not _is_non_empty_string(publication.publisher_service):
            errors.append("publication.publisher_service must be a non-empty string")
        if publication.published_at is None:
            errors.append("publication.published_at must be set for a published Rabbit event")

        if errors:
            raise ValueError("; ".join(errors))
