from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from application.crm_sync_builder import build_crm_sync_item
from application.lifecycle.delta_downgrade import downgrade_reason, should_downgrade_delta_event_to_product_found
from application.lifecycle.lifecycle_policy import (
    build_identity_context,
    choose_lifecycle_event_type,
)
from application.lifecycle.replay_policy import choose_replay_mode
from config.settings import settings
from domain.crm_lifecycle import LifecycleDecision, ParserLifecycleEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.correlation import build_correlation_context
from infrastructure.observability.event_logger import log_sync_event
from domain.crm_sync import CrmSyncItem
from domain.parser_event import ParserSyncEvent

logger = logging.getLogger(__name__)

_lifecycle_dev_debug_emit_count: int = 0


def _lifecycle_log(event: str, **fields: Any) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    payload["event"] = event
    logger.info("lifecycle %s", json.dumps(payload, default=str, ensure_ascii=False))


def parser_sync_event_from_lifecycle(
    ple: ParserLifecycleEvent,
    *,
    normalized_for_reconcile: dict[str, Any] | None = None,
) -> ParserSyncEvent:
    """Wire envelope for HTTP transport; ``payload_hash`` mirrors business data only."""
    data_dict = dict(ple.data)
    sync_item = CrmSyncItem.model_validate(data_dict)
    if sync_item.payload_hash != ple.payload_hash:
        raise ValueError("lifecycle payload_hash mismatch vs CrmSyncItem")
    return ParserSyncEvent(
        event_id=ple.event_id,
        event_type=ple.event_type,
        sent_at=ple.sent_at,
        identity=ple.identity,
        payload_hash=ple.payload_hash,
        data=sync_item,
        request_idempotency_key=ple.request_idempotency_key,
        replay_mode=ple.replay_mode,
        original_intent_event_type=ple.original_intent_event_type,
        normalized_for_reconcile=dict(normalized_for_reconcile) if normalized_for_reconcile is not None else None,
    )


def build_lifecycle_event(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
    requested_event_type: str | None = None,
) -> tuple[ParserLifecycleEvent, LifecycleDecision]:
    """Build logical lifecycle event + decision; replay-safe metadata from 4C."""
    from infrastructure.performance.timing_profiler import timed_stage

    st = str(normalized.get("store") or "").strip() or "unknown"
    with timed_stage("lifecycle_build", store_name=st, spider_name="lifecycle"):
        return _build_lifecycle_event_impl(normalized, runtime_ids, requested_event_type)


def _build_lifecycle_event_impl(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
    requested_event_type: str | None = None,
) -> tuple[ParserLifecycleEvent, LifecycleDecision]:
    sync_item = build_crm_sync_item(normalized)
    decision = choose_lifecycle_event_type(normalized, runtime_ids, requested_event_type)
    identity = build_identity_context(normalized, runtime_ids)
    identity = identity.model_copy(update={"entity_key": sync_item.entity_key})

    intent_type = decision.selected_event_type
    rd_intent = choose_replay_mode(normalized, intent_type, runtime_ids)
    original_intent: str | None = None
    final_type = intent_type
    rd = rd_intent

    if should_downgrade_delta_event_to_product_found(intent_type, runtime_ids, rd_intent):
        original_intent = intent_type
        final_type = "product_found"
        sync_item = sync_item.model_copy(update={"change_hint": "new_product"})
        rd = choose_replay_mode(normalized, final_type, runtime_ids).model_copy(
            update={
                "fallback_to_product_found": True,
                "reason": downgrade_reason(intent_type, runtime_ids, rd_intent),
                "safe_to_resend": True,
            }
        )
        _lifecycle_log(
            "DELTA_DOWNGRADED_TO_PRODUCT_FOUND",
            store=identity.source_name,
            entity_key=identity.entity_key,
            event_type=intent_type,
            selected_event_type=final_type,
            payload_hash=sync_item.payload_hash,
            request_idempotency_key=rd.request_idempotency_key,
            replay_mode=rd.replay_mode,
            reason=rd.reason,
        )
        log_sync_event(
            "lifecycle_select",
            "warning",
            obs_mc.LIFECYCLE_FALLBACK_APPLIED,
            build_correlation_context(
                "lifecycle",
                identity.source_name,
                source_url=identity.source_url,
                source_id=identity.source_id,
                entity_key=identity.entity_key,
                payload_hash=sync_item.payload_hash,
                request_idempotency_key=rd.request_idempotency_key,
            ),
            details={
                "from_event_type": intent_type,
                "to_event_type": final_type,
                "reason": rd.reason,
            },
            failure_domain="lifecycle",
            failure_type="event_fallback",
        )

    if settings.PARSER_INCLUDE_IDEMPOTENCY_KEY_IN_PAYLOAD and rd.request_idempotency_key:
        sync_item = sync_item.model_copy(update={"request_idempotency_key": rd.request_idempotency_key})

    data_payload = sync_item.model_dump(mode="json")
    if settings.PARSER_INCLUDE_IDEMPOTENCY_KEY_IN_PAYLOAD and rd.request_idempotency_key:
        data_payload["request_idempotency_key"] = rd.request_idempotency_key

    from application.release.shape_compat import apply_export_compatibility

    data_payload = apply_export_compatibility("crm_payload", data_payload)

    _lifecycle_log(
        "LIFECYCLE_EVENT_SELECTED",
        store=identity.source_name,
        source_id=identity.source_id,
        source_url=identity.source_url,
        entity_key=identity.entity_key,
        requested_event_type=requested_event_type,
        selected_event_type=final_type,
        fallback_reason=decision.fallback_reason if decision.fallback_applied else None,
        crm_listing_id=identity.crm_listing_id,
        crm_product_id=identity.crm_product_id,
        action=None,
        payload_hash=sync_item.payload_hash,
    )
    log_sync_event(
        "lifecycle_select",
        "info",
        obs_mc.LIFECYCLE_EVENT_SELECTED,
        build_correlation_context(
            "lifecycle",
            identity.source_name,
            source_url=identity.source_url,
            source_id=identity.source_id,
            entity_key=identity.entity_key,
            payload_hash=sync_item.payload_hash,
            request_idempotency_key=rd.request_idempotency_key,
        ),
        details={
            "requested_event_type": requested_event_type,
            "selected_event_type": final_type,
            "fallback_applied": decision.fallback_applied,
            "fallback_reason": decision.fallback_reason if decision.fallback_applied else None,
        },
    )
    _lifecycle_log(
        "IDEMPOTENCY_KEY_BUILT",
        store=identity.source_name,
        entity_key=identity.entity_key,
        event_type=final_type,
        selected_event_type=final_type,
        payload_hash=sync_item.payload_hash,
        request_idempotency_key=rd.request_idempotency_key,
        replay_mode=rd.replay_mode,
        reason=rd.reason,
    )
    _lifecycle_log(
        "REPLAY_DECISION_SELECTED",
        store=identity.source_name,
        entity_key=identity.entity_key,
        event_type=final_type,
        selected_event_type=rd.selected_event_type,
        payload_hash=sync_item.payload_hash,
        request_idempotency_key=rd.request_idempotency_key,
        replay_mode=rd.replay_mode,
        safe_to_resend=rd.safe_to_resend,
        fallback_to_product_found=rd.fallback_to_product_found,
        reason=rd.reason,
    )

    ple = ParserLifecycleEvent(
        event_id=str(uuid.uuid4()),
        event_type=final_type,
        sent_at=datetime.now(UTC),
        identity=identity,
        payload_hash=sync_item.payload_hash,
        data=data_payload,
        request_idempotency_key=rd.request_idempotency_key,
        replay_mode=rd.replay_mode,
        original_intent_event_type=original_intent,
    )
    if settings.DEV_MODE and settings.DEV_ENABLE_DEBUG_SUMMARIES and settings.DEV_DEBUG_INCLUDE_LIFECYCLE:
        global _lifecycle_dev_debug_emit_count
        cap = 20 if settings.DEV_ENABLE_VERBOSE_STAGE_OUTPUT else 5
        _lifecycle_dev_debug_emit_count += 1
        if _lifecycle_dev_debug_emit_count <= cap:
            from application.dev.debug_summary import build_lifecycle_debug_view
            from infrastructure.observability.event_logger import log_developer_experience_event

            ev_dict = ple.model_dump(mode="json")
            dec_dict = decision.model_dump(mode="json")
            view = build_lifecycle_debug_view(ev_dict, dec_dict)
            log_developer_experience_event(
                obs_mc.DEV_DEBUG_SUMMARY_BUILT,
                dev_run_mode=settings.DEV_RUN_MODE,
                store_name=identity.source_name,
                sections_included=["lifecycle"],
                items_count=1,
                details={"preview": view},
            )
    return ple, decision


def build_product_found_event(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> ParserLifecycleEvent:
    ple, _ = build_lifecycle_event(normalized, runtime_ids, requested_event_type="product_found")
    return ple


def build_price_changed_event(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> tuple[ParserLifecycleEvent, LifecycleDecision]:
    return build_lifecycle_event(normalized, runtime_ids, "price_changed")


def build_out_of_stock_event(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> tuple[ParserLifecycleEvent, LifecycleDecision]:
    return build_lifecycle_event(normalized, runtime_ids, "out_of_stock")


def build_characteristic_added_event(
    normalized: dict[str, Any],
    runtime_ids: dict[str, str] | None = None,
) -> tuple[ParserLifecycleEvent, LifecycleDecision]:
    return build_lifecycle_event(normalized, runtime_ids, "characteristic_added")
