"""Parser↔CRM lifecycle policy and event construction (stateless-safe defaults)."""

from application.lifecycle.lifecycle_builder import (
    build_characteristic_added_event,
    build_lifecycle_event,
    build_out_of_stock_event,
    build_price_changed_event,
    build_product_found_event,
    parser_sync_event_from_lifecycle,
)
from application.lifecycle.lifecycle_policy import (
    build_identity_context,
    can_emit_event,
    choose_lifecycle_event_type,
    should_fallback_to_product_found,
)

__all__ = [
    "build_characteristic_added_event",
    "build_lifecycle_event",
    "build_out_of_stock_event",
    "build_price_changed_event",
    "build_product_found_event",
    "parser_sync_event_from_lifecycle",
    "build_identity_context",
    "can_emit_event",
    "choose_lifecycle_event_type",
    "should_fallback_to_product_found",
]
