from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from domain.specs.base import BaseSpecs


class NormalizedProduct(BaseModel):
    source: str
    url: str
    source_id: str
    brand: str
    name: str
    price: Decimal
    currency: str = "UZS"
    in_stock: bool
    specs: BaseSpecs
    images: list[str] = Field(default_factory=list)
    extraction_method: str = "structured"
    completeness_score: float = 0.0
