from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RawProduct(BaseModel):
    """Structured scrape output only; Moscraper is stateless and does not persist HTML or DB rows."""

    source: str
    url: str
    source_id: str
    title: str
    price_str: str
    in_stock: bool = True
    raw_specs: dict = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    description: str = ""
    category_hint: str | None = None

    model_config = {"str_strip_whitespace": True}


def as_scrapy_item_dict(extracted: dict[str, Any]) -> dict[str, Any]:
    """Validate spider output as :class:`RawProduct` and return a plain dict for Scrapy pipelines."""
    if "source" not in extracted or "url" not in extracted:
        raise ValueError("extracted must include 'source' and 'url' before normalization")
    raw_specs = dict(extracted.get("raw_specs") or {})
    raw_specs.pop("_category_hint", None)
    cat_hint = extracted.get("category_hint") or extracted.get("category")
    cat_hint = str(cat_hint).strip() if cat_hint else None
    rp = RawProduct(
        source=str(extracted["source"]),
        url=str(extracted["url"]),
        source_id=str(extracted.get("source_id") or extracted.get("external_id") or ""),
        title=str(extracted.get("title") or extracted.get("name") or ""),
        price_str=str(extracted.get("price_str") or ""),
        in_stock=bool(extracted.get("in_stock", True)),
        raw_specs=raw_specs,
        image_urls=[str(u).strip() for u in (extracted.get("image_urls") or []) if u],
        description=str(extracted.get("description") or ""),
        category_hint=cat_hint,
    )
    return rp.model_dump()
