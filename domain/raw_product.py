from __future__ import annotations

from pydantic import BaseModel, Field


class RawProduct(BaseModel):
    source: str
    url: str
    source_id: str
    title: str
    price_str: str
    in_stock: bool = True
    raw_specs: dict = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    description: str = ""
    raw_html: str | None = None

    model_config = {"str_strip_whitespace": True}
