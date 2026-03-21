from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ProductPayload(BaseModel):
    name: str
    brand: str
    characteristics: dict


class ListingPayload(BaseModel):
    price: Decimal
    currency: str = "UZS"
    in_stock: bool
    parsed_at: datetime


class ProductFoundEvent(BaseModel):
    event: Literal["product_found"] = "product_found"
    source: str
    source_url: str
    source_id: str
    crm_product_id: UUID | None = None
    product: ProductPayload
    listing: ListingPayload


class PriceChangedEvent(BaseModel):
    event: Literal["price_changed"] = "price_changed"
    crm_listing_id: UUID
    listing: ListingPayload


class OutOfStockEvent(BaseModel):
    event: Literal["out_of_stock"] = "out_of_stock"
    crm_listing_id: UUID
    parsed_at: datetime


class CharacteristicAddedEvent(BaseModel):
    event: Literal["characteristic_added"] = "characteristic_added"
    crm_product_id: UUID
    characteristics: dict


class CRMSyncResponse(BaseModel):
    status: Literal["ok", "error"]
    crm_listing_id: UUID | None = None
    crm_product_id: UUID | None = None
    action: Literal["created", "matched", "needs_review"]


BaseEvent = ProductFoundEvent | PriceChangedEvent | OutOfStockEvent | CharacteristicAddedEvent

__all__ = [
    "BaseEvent",
    "CRMSyncResponse",
    "CharacteristicAddedEvent",
    "ListingPayload",
    "OutOfStockEvent",
    "PriceChangedEvent",
    "ProductFoundEvent",
    "ProductPayload",
]
