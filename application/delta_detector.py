from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from domain.events import (
    BaseEvent,
    CharacteristicAddedEvent,
    ListingPayload,
    OutOfStockEvent,
    PriceChangedEvent,
    ProductFoundEvent,
    ProductPayload,
)
from domain.normalized_product import NormalizedProduct
from domain.specs.base import BaseSpecs

logger = logging.getLogger(__name__)

PRICE_TOLERANCE = Decimal("100")


class DeltaDetector:
    def detect(self, normalized: NormalizedProduct, cache, crm_response=None) -> list[BaseEvent]:
        now = datetime.now(timezone.utc)

        if cache is None:
            specs_dict = self._specs_to_dict(normalized.specs)
            return [
                ProductFoundEvent(
                    source=normalized.source,
                    source_url=normalized.url,
                    source_id=normalized.source_id,
                    crm_product_id=crm_response.crm_product_id if crm_response else None,
                    product=ProductPayload(
                        name=normalized.name,
                        brand=normalized.brand,
                        characteristics=specs_dict,
                    ),
                    listing=ListingPayload(
                        price=normalized.price,
                        currency=normalized.currency,
                        in_stock=normalized.in_stock,
                        parsed_at=now,
                    ),
                )
            ]

        events: list[BaseEvent] = []

        listing_id = cache.crm_listing_id
        if listing_id is not None:
            if cache.last_price is not None and normalized.price is not None:
                if self._price_changed(normalized.price, Decimal(str(cache.last_price))):
                    events.append(
                        PriceChangedEvent(
                            crm_listing_id=listing_id,
                            listing=ListingPayload(
                                price=normalized.price,
                                currency=normalized.currency,
                                in_stock=normalized.in_stock,
                                parsed_at=now,
                            ),
                        )
                    )

            if cache.last_in_stock and not normalized.in_stock:
                events.append(OutOfStockEvent(crm_listing_id=listing_id, parsed_at=now))

            if not cache.last_in_stock and normalized.in_stock:
                events.append(
                    PriceChangedEvent(
                        crm_listing_id=listing_id,
                        listing=ListingPayload(
                            price=normalized.price,
                            currency=normalized.currency,
                            in_stock=normalized.in_stock,
                            parsed_at=now,
                        ),
                    )
                )

        if cache.crm_product_id:
            specs_dict = self._specs_to_dict(normalized.specs)
            new_chars = {k: v for k, v in specs_dict.items() if v is not None}
            if new_chars and normalized.extraction_method != "unknown":
                events.append(
                    CharacteristicAddedEvent(
                        crm_product_id=cache.crm_product_id,
                        characteristics=new_chars,
                    )
                )

        if not events:
            logger.debug("[DELTA_EMPTY] No changes for %s", normalized.url)

        return events

    def _specs_to_dict(self, specs: BaseSpecs) -> dict:
        meta_fields = {"completeness_score", "extraction_method", "raw_fields"}
        return {k: v for k, v in specs.model_dump().items() if k not in meta_fields and v is not None}

    def _price_changed(self, new: Decimal, old: Decimal, tolerance: Decimal = PRICE_TOLERANCE) -> bool:
        return abs(new - old) > tolerance
