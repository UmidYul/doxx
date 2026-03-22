from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import orjson

from config.settings import settings
from domain.messages import CloudEventListingScraped, ListingScrapedData


def _canonical_url(url: str) -> str:
    p = urlparse(url.strip())
    netloc = (p.netloc or "").lower()
    path = p.path or "/"
    return f"{p.scheme}://{netloc}{path}"


def build_entity_key(store: str, source_id: str | None, url: str) -> str:
    sid = (source_id or "").strip()
    if sid:
        return f"{store}:{sid}"
    h = hashlib.sha256(_canonical_url(url).encode()).hexdigest()[:16]
    return f"{store}:{h}"


def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def build_payload_hash(
    *,
    schema_version: int,
    store: str,
    url: str,
    title: str,
    scraped_at: datetime | None = None,
    source_id: str | None,
    price_raw: str | None,
    price_value: int | None,
    currency: str | None,
    in_stock: bool | None,
    brand: str | None,
    raw_specs: dict[str, Any],
    description: str | None,
    image_urls: list[str],
) -> str:
    """SHA-256 over business-only fields.

    ``scraped_at`` is accepted for backward compatibility but intentionally
    excluded from the hash so that re-scraping the same product with identical
    business data produces the same hash regardless of timing.
    """
    blob = {
        "schema_version": schema_version,
        "store": store,
        "url": _canonical_url(url),
        "title": _light_title(title),
        "source_id": source_id if source_id else None,
        "price_raw": price_raw,
        "price_value": price_value,
        "currency": currency,
        "in_stock": in_stock,
        "brand": brand,
        "raw_specs": raw_specs,
        "description": description,
        "image_urls": image_urls,
    }
    raw = orjson.dumps(blob, option=orjson.OPT_SORT_KEYS)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


_WS_RE = re.compile(r"\s+")


def _light_title(title: str) -> str:
    return _WS_RE.sub(" ", (title or "").strip())


def build_listing_event(
    *,
    store: str,
    url: str,
    title: str,
    scraped_at: datetime | None = None,
    source_id: str | None = None,
    price_raw: str | None = None,
    price_value: int | None = None,
    currency: str | None = None,
    in_stock: bool | None = None,
    brand: str | None = None,
    raw_specs: dict[str, Any] | None = None,
    description: str | None = None,
    image_urls: list[str] | None = None,
) -> CloudEventListingScraped:
    when = scraped_at or datetime.now(UTC)
    rs = dict(raw_specs or {})
    imgs = list(image_urls or [])
    schema_version = settings.MESSAGE_SCHEMA_VERSION
    cur = currency or settings.DEFAULT_CURRENCY

    entity_key = build_entity_key(store, source_id, url)
    payload_hash = build_payload_hash(
        schema_version=schema_version,
        store=store,
        url=url,
        title=title,
        scraped_at=when,
        source_id=source_id,
        price_raw=price_raw,
        price_value=price_value,
        currency=cur,
        in_stock=in_stock,
        brand=brand,
        raw_specs=rs,
        description=description,
        image_urls=imgs,
    )

    data = ListingScrapedData(
        schema_version=schema_version,
        entity_key=entity_key,
        payload_hash=payload_hash,
        store=store,
        url=url.strip(),
        title=_light_title(title),
        scraped_at=when,
        source_id=source_id if source_id else None,
        price_raw=price_raw,
        price_value=price_value,
        currency=cur,
        in_stock=in_stock,
        brand=brand,
        raw_specs=rs,
        description=description,
        image_urls=imgs,
    )

    return CloudEventListingScraped(
        id=str(uuid.uuid4()),
        source=f"moscraper://{store}",
        time=when,
        data=data,
    )
