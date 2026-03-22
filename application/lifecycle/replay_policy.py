from __future__ import annotations

from typing import Any, cast

from application.lifecycle.idempotency import build_request_idempotency_key, is_replay_safe_event_type
from config.settings import settings
from domain.crm_replay import IdempotencyScope, ReplayMode, ReplayDecision


def _parse_replay_mode() -> ReplayMode:
    m = (settings.PARSER_REPLAY_MODE_DEFAULT or "snapshot_upsert").strip().lower()
    if m in ("snapshot_upsert", "delta_if_possible", "reconcile_only"):
        return m  # type: ignore[return-value]
    return "snapshot_upsert"


def _parse_idempotency_scope() -> str:
    s = (settings.PARSER_IDEMPOTENCY_SCOPE_DEFAULT or "entity_payload").strip().lower()
    if s in ("entity_payload", "entity_only", "event_only"):
        return s
    return "entity_payload"


def choose_replay_mode(
    normalized: dict[str, Any],
    selected_event_type: str,
    runtime_ids: dict[str, str] | None = None,
) -> ReplayDecision:
    """Pick replay mode + idempotency key for CRM-facing ``selected_event_type``."""
    from application.crm_sync_builder import build_entity_key

    store = str(normalized.get("store") or "")
    url = str(normalized.get("url") or "")
    sid = normalized.get("source_id")
    if isinstance(sid, str) and not sid.strip():
        sid = None
    entity_key = build_entity_key(store, sid if isinstance(sid, str) else None, url)

    payload_hash = str(normalized.get("_payload_hash") or "")
    if not payload_hash:
        from application.crm_sync_builder import build_crm_sync_item

        tmp = build_crm_sync_item(normalized)
        payload_hash = tmp.payload_hash

    scope = _parse_idempotency_scope()
    if scope == "event_only":
        raise ValueError("PARSER_IDEMPOTENCY_SCOPE_DEFAULT=event_only is invalid for lifecycle build")

    mode = _parse_replay_mode()
    et = (selected_event_type or "product_found").strip()

    key = build_request_idempotency_key(entity_key, payload_hash, et, scope=scope)
    safe = can_safely_resend(et, runtime_ids)

    reason: str | None = None
    fallback = False
    if et != "product_found" and not is_replay_safe_event_type(et):
        if mode == "delta_if_possible" and not _has_trusted_runtime_ids(runtime_ids):
            mode = "snapshot_upsert"
            fallback = True
            reason = "delta_requires_runtime_ids"

    return ReplayDecision(
        replay_mode=mode,
        idempotency_scope=cast(IdempotencyScope, scope),
        request_idempotency_key=key,
        selected_event_type=et,
        fallback_to_product_found=fallback,
        reason=reason,
        safe_to_resend=safe,
    )


def _has_trusted_runtime_ids(runtime_ids: dict[str, str] | None) -> bool:
    if not runtime_ids:
        return False
    return bool(str(runtime_ids.get("crm_listing_id") or "").strip())


def can_safely_resend(event_type: str, runtime_ids: dict[str, str] | None = None) -> bool:
    et = (event_type or "").strip().lower()
    if et == "product_found":
        return bool(settings.PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND)
    if settings.PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS and is_replay_safe_event_type(et):
        return _has_trusted_runtime_ids(runtime_ids)
    return False


def should_downgrade_replay_to_product_found(
    event_type: str,
    runtime_ids: dict[str, str] | None = None,
) -> bool:
    """When delta is not replay-safe and runtime ids are missing, prefer snapshot upsert path."""
    et = (event_type or "").strip().lower()
    if et == "product_found":
        return False
    if is_replay_safe_event_type(et) and settings.PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS:
        return False
    return not _has_trusted_runtime_ids(runtime_ids)
