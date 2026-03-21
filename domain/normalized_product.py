from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NormalizedProduct(BaseModel):
    """Deterministic scrape normalization. ``raw_specs`` stay opaque; CRM maps semantics."""

    model_config = ConfigDict(str_strip_whitespace=True)

    store: str
    url: str
    title: str
    source_id: str | None = None
    price_raw: str | None = None
    price: float | None = None
    currency: str = "UZS"
    in_stock: bool = True
    brand: str | None = None
    raw_specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)
