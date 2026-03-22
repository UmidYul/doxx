from __future__ import annotations

from domain.crm_replay import ReplayDecision


def downgrade_reason(
    original_event_type: str,
    runtime_ids: dict[str, str] | None,
    replay_decision: ReplayDecision | None = None,
) -> str:
    parts: list[str] = [f"from_{original_event_type}_to_product_found"]
    if not _has_listing(runtime_ids):
        parts.append("missing_runtime_listing_id")
    if replay_decision and not replay_decision.safe_to_resend:
        parts.append("not_safe_to_resend_delta")
    if replay_decision and replay_decision.replay_mode == "reconcile_only":
        parts.append("reconcile_only_mode")
    return ";".join(parts)


def _has_listing(runtime_ids: dict[str, str] | None) -> bool:
    if not runtime_ids:
        return False
    return bool(str(runtime_ids.get("crm_listing_id") or "").strip())


def should_downgrade_delta_event_to_product_found(
    event_type: str,
    runtime_ids: dict[str, str] | None,
    replay_decision: ReplayDecision,
) -> bool:
    """Downgrade delta to ``product_found`` when runtime CRM ids are missing or reconcile-only mode."""
    et = (event_type or "").strip().lower()
    if et == "product_found":
        return False
    from application.lifecycle.replay_policy import should_downgrade_replay_to_product_found

    if _has_listing(runtime_ids):
        return False
    if should_downgrade_replay_to_product_found(et, runtime_ids):
        return True
    if replay_decision.replay_mode == "reconcile_only":
        return True
    return False
