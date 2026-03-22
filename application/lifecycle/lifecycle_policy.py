from __future__ import annotations

import json
import logging
from typing import Any, cast

from config.settings import settings
from domain.crm_lifecycle import CrmIdentityContext, LifecycleDecision, ParserLifecycleEventType
from domain.crm_sync import CrmSyncItem

logger = logging.getLogger(__name__)

_ALLOWED: tuple[ParserLifecycleEventType, ...] = (
    "product_found",
    "price_changed",
    "out_of_stock",
    "characteristic_added",
)


def _clean_id(v: object | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def build_identity_context(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> CrmIdentityContext:
    """Stable identity from normalized item + optional in-run CRM ids."""
    from application.crm_sync_builder import build_entity_key

    store = str(normalized.get("store") or "")
    url = str(normalized.get("url") or "")
    source_id = normalized.get("source_id")
    if isinstance(source_id, str) and not source_id.strip():
        source_id = None
    entity_key = build_entity_key(store, source_id if isinstance(source_id, str) else None, url)

    external_ids: dict[str, str] = dict(normalized.get("external_ids") or {})
    if not external_ids and source_id and store:
        external_ids = {store: str(source_id)}

    barcode = normalized.get("barcode")
    if barcode is not None and isinstance(barcode, str) and not barcode.strip():
        barcode = None

    rt = runtime_ids or {}
    return CrmIdentityContext(
        entity_key=entity_key,
        external_ids=external_ids,
        barcode=barcode if isinstance(barcode, str) else None,
        source_name=store,
        source_url=url.strip(),
        source_id=source_id if isinstance(source_id, str) else None,
        crm_listing_id=_clean_id(rt.get("crm_listing_id")),
        crm_product_id=_clean_id(rt.get("crm_product_id")),
    )


def _default_event_type() -> ParserLifecycleEventType:
    d = (settings.PARSER_LIFECYCLE_DEFAULT_EVENT or "product_found").strip()
    if d in _ALLOWED:
        return cast(ParserLifecycleEventType, d)
    return "product_found"


def _runtime_deltas_enabled() -> bool:
    return settings.PARSER_ENABLE_RUNTIME_DELTA_EVENTS and settings.PARSER_ENABLE_DELTA_EVENTS


def _infer_requested_event_type(sync_item: CrmSyncItem) -> ParserLifecycleEventType:
    """Map change_hint + legacy per-delta flags to a requested CRM event type."""
    if not settings.PARSER_ENABLE_DELTA_EVENTS:
        return _default_event_type()
    ch = sync_item.change_hint
    if settings.PARSER_ENABLE_PRICE_CHANGED_EVENT and ch == "price_update":
        return "price_changed"
    if settings.PARSER_ENABLE_OUT_OF_STOCK_EVENT and ch == "stock_update":
        return "out_of_stock"
    if settings.PARSER_ENABLE_CHARACTERISTIC_ADDED_EVENT and ch == "spec_update":
        return "characteristic_added"
    return _default_event_type()


def _has_spec_change_signal(normalized: dict[str, Any], sync_item: CrmSyncItem) -> bool:
    if bool(normalized.get("lifecycle_spec_update")):
        return True
    return sync_item.change_hint == "spec_update"


def can_emit_event(
    event_type: str,
    identity: CrmIdentityContext,
    normalized: dict[str, Any],
    *,
    sync_item: CrmSyncItem | None = None,
) -> LifecycleDecision:
    """Whether ``event_type`` is allowed given identity bridge + normalized hints."""
    et = event_type if event_type in _ALLOWED else "product_found"
    notes: list[str] = []
    required: list[str] = []

    if et == "product_found":
        return LifecycleDecision(
            selected_event_type="product_found",
            allowed=True,
            fallback_applied=False,
            notes=["product_found_always_safe"],
        )

    if not _runtime_deltas_enabled():
        return LifecycleDecision(
            selected_event_type=et,
            allowed=False,
            fallback_applied=False,
            fallback_reason="runtime_delta_events_disabled",
            notes=["PARSER_ENABLE_RUNTIME_DELTA_EVENTS_or_PARSER_ENABLE_DELTA_EVENTS_off"],
        )

    if et == "price_changed":
        if not settings.PARSER_ALLOW_PRICE_CHANGED_WITH_RUNTIME_IDS:
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="price_changed_disabled_by_policy",
                notes=[],
            )
        if not identity.crm_listing_id:
            required.append("crm_listing_id")
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="missing_crm_listing_id",
                required_ids=required,
                notes=["price_changed_requires_runtime_listing_id"],
            )
        return LifecycleDecision(
            selected_event_type="price_changed",
            allowed=True,
            fallback_applied=False,
            notes=["listing_id_present"],
        )

    if et == "out_of_stock":
        if not settings.PARSER_ALLOW_OUT_OF_STOCK_WITH_RUNTIME_IDS:
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="out_of_stock_disabled_by_policy",
                notes=[],
            )
        if not identity.crm_listing_id:
            required.append("crm_listing_id")
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="missing_crm_listing_id",
                required_ids=required,
                notes=["out_of_stock_requires_runtime_listing_id"],
            )
        return LifecycleDecision(
            selected_event_type="out_of_stock",
            allowed=True,
            fallback_applied=False,
            notes=["listing_id_present"],
        )

    if et == "characteristic_added":
        if not settings.PARSER_ALLOW_CHARACTERISTIC_ADDED_WITH_RUNTIME_IDS:
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="characteristic_added_disabled_by_policy",
                notes=[],
            )
        if not identity.crm_product_id:
            required.append("crm_product_id")
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="missing_crm_product_id",
                required_ids=required,
                notes=["characteristic_added_requires_runtime_product_id"],
            )
        si = sync_item
        if si is None:
            from application.crm_sync_builder import build_crm_sync_item

            si = build_crm_sync_item(normalized)
        if not _has_spec_change_signal(normalized, si):
            return LifecycleDecision(
                selected_event_type=et,
                allowed=False,
                fallback_applied=False,
                fallback_reason="insufficient_spec_change_signal",
                notes=["need_lifecycle_spec_update_or_change_hint_spec_update"],
            )
        return LifecycleDecision(
            selected_event_type="characteristic_added",
            allowed=True,
            fallback_applied=False,
            notes=["product_id_and_spec_signal_present"],
        )

    return LifecycleDecision(
        selected_event_type="product_found",
        allowed=True,
        fallback_applied=False,
        notes=["unknown_type_defaulted"],
    )


def choose_lifecycle_event_type(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
    requested_event_type: str | None = None,
) -> LifecycleDecision:
    """Pick final CRM event type; fall back to ``product_found`` when unsafe."""
    from application.crm_sync_builder import build_crm_sync_item
    from application.release.rollout_policy_engine import is_feature_enabled

    sync_item = build_crm_sync_item(normalized)
    if not is_feature_enabled("lifecycle_delta_events", sync_item.source_name, sync_item.entity_key):
        return LifecycleDecision(
            selected_event_type="product_found",
            allowed=True,
            fallback_applied=False,
            notes=["lifecycle_delta_events_disabled_by_rollout"],
        )
    identity = build_identity_context(normalized, runtime_ids)
    identity = identity.model_copy(update={"entity_key": sync_item.entity_key})

    inferred = _infer_requested_event_type(sync_item)
    if requested_event_type is not None and str(requested_event_type).strip():
        requested = str(requested_event_type).strip()
    else:
        requested = inferred
    if requested not in _ALLOWED:
        requested = "product_found"

    if requested == "product_found":
        return LifecycleDecision(
            selected_event_type="product_found",
            allowed=True,
            fallback_applied=False,
            notes=["explicit_or_default_product_found"],
        )

    probe = can_emit_event(requested, identity, normalized, sync_item=sync_item)
    if probe.allowed:
        return LifecycleDecision(
            selected_event_type=probe.selected_event_type,
            allowed=True,
            fallback_applied=False,
            required_ids=probe.required_ids,
            notes=probe.notes,
        )

    if settings.PARSER_FORCE_PRODUCT_FOUND_FALLBACK:
        logger.info(
            "lifecycle %s",
            json.dumps(
                {
                    "event": "LIFECYCLE_DELTA_BLOCKED",
                    "store": identity.source_name,
                    "source_id": identity.source_id,
                    "source_url": identity.source_url,
                    "entity_key": identity.entity_key,
                    "requested_event_type": requested,
                    "selected_event_type": "product_found",
                    "fallback_reason": probe.fallback_reason,
                    "crm_listing_id": identity.crm_listing_id,
                    "crm_product_id": identity.crm_product_id,
                    "required_ids": probe.required_ids,
                },
                default=str,
                ensure_ascii=False,
            ),
        )
        logger.info(
            "lifecycle %s",
            json.dumps(
                {
                    "event": "LIFECYCLE_FALLBACK_APPLIED",
                    "store": identity.source_name,
                    "source_id": identity.source_id,
                    "source_url": identity.source_url,
                    "entity_key": identity.entity_key,
                    "requested_event_type": requested,
                    "selected_event_type": "product_found",
                    "fallback_reason": probe.fallback_reason,
                    "crm_listing_id": identity.crm_listing_id,
                    "crm_product_id": identity.crm_product_id,
                    "action": None,
                    "payload_hash": sync_item.payload_hash,
                },
                default=str,
                ensure_ascii=False,
            ),
        )
        return LifecycleDecision(
            selected_event_type="product_found",
            allowed=True,
            fallback_applied=True,
            fallback_reason=probe.fallback_reason,
            required_ids=probe.required_ids,
            notes=[*(probe.notes or []), "forced_product_found_fallback"],
        )

    # Ultra-safe default even if force flag is off (stateless parser should not block delivery)
    return LifecycleDecision(
        selected_event_type="product_found",
        allowed=True,
        fallback_applied=True,
        fallback_reason=probe.fallback_reason or "policy_denied_delta",
        required_ids=probe.required_ids,
        notes=[*(probe.notes or []), "default_safe_product_found"],
    )


def should_fallback_to_product_found(decision: LifecycleDecision) -> bool:
    return bool(decision.fallback_applied)
