from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.scrape_fingerprints import (
    build_product_identity_key,
    build_scraped_payload_hash,
    normalize_external_ids,
    normalize_image_urls,
    normalize_json_dict,
    normalize_text,
)


class ScrapedProductSnapshot(BaseModel):
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
    scraped_at: datetime
    payload_hash: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    scrape_run_id: str
    identity_key: str

    model_config = {"str_strip_whitespace": True}

    @classmethod
    def from_scrapy_item(
        cls,
        item: dict[str, Any],
        *,
        scrape_run_id: str,
        scraped_at: datetime | None = None,
    ) -> "ScrapedProductSnapshot":
        store_name = normalize_text(item.get("source")) or ""
        source_url = normalize_text(item.get("url")) or ""
        source_id = normalize_text(item.get("source_id") or item.get("external_id"))
        title = normalize_text(item.get("title") or item.get("name")) or ""
        brand = normalize_text(item.get("brand"))
        price_raw = normalize_text(item.get("price_raw") or item.get("price_str"))
        description = normalize_text(item.get("description"))
        category_hint = normalize_text(item.get("category_hint") or item.get("category"))
        raw_specs = normalize_json_dict(item.get("raw_specs") if isinstance(item.get("raw_specs"), dict) else {})
        image_urls = normalize_image_urls(item.get("image_urls") if isinstance(item.get("image_urls"), list) else [])
        external_ids = normalize_external_ids(item.get("external_ids") if isinstance(item.get("external_ids"), dict) else {})
        if source_id and store_name and store_name not in external_ids:
            external_ids[store_name] = source_id

        identity_key = build_product_identity_key(store_name, source_id, source_url)
        payload_hash = build_scraped_payload_hash(
            store_name=store_name,
            source_url=source_url,
            source_id=source_id,
            title=title,
            brand=brand,
            price_raw=price_raw,
            in_stock=bool(item.get("in_stock")) if item.get("in_stock") is not None else None,
            raw_specs=raw_specs,
            image_urls=image_urls,
            description=description,
            category_hint=category_hint,
            external_ids=external_ids,
        )
        raw_payload = {
            str(key): value
            for key, value in dict(item).items()
            if not str(key).startswith("_")
        }
        when = scraped_at or datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)

        return cls(
            store_name=store_name,
            source_url=source_url,
            source_id=source_id,
            title=title,
            brand=brand,
            price_raw=price_raw,
            in_stock=bool(item.get("in_stock")) if item.get("in_stock") is not None else None,
            raw_specs=raw_specs,
            image_urls=image_urls,
            description=description,
            category_hint=category_hint,
            external_ids=external_ids,
            scraped_at=when,
            payload_hash=payload_hash,
            raw_payload=raw_payload,
            scrape_run_id=scrape_run_id,
            identity_key=identity_key,
        )
