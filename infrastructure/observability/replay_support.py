from __future__ import annotations

from config.settings import settings
from domain.operator_support import ReplaySupportDecision, RunbookAction

from infrastructure.security.replay_abuse_guard import validate_replay_request


def explain_replay_risk(event_type: str) -> str:
    et = (event_type or "").strip().lower()
    if et == "product_found":
        return "product_found is idempotency-friendly when CRM honors entity_key + payload_hash; still cap volume."
    if et in ("price_changed", "out_of_stock", "characteristic_added"):
        return "Delta events can duplicate business side-effects if replayed blindly; disabled by default."
    return "Unknown event type: treat replay as manual investigation first."


def can_replay_item(event_type: str) -> bool:
    et = (event_type or "").strip().lower()
    if getattr(settings, "SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY", True):
        return et == "product_found" and bool(settings.SAFE_REPLAY_ALLOW_PRODUCT_FOUND)
    if et == "product_found":
        return bool(settings.SAFE_REPLAY_ALLOW_PRODUCT_FOUND)
    if et in ("price_changed", "out_of_stock", "characteristic_added"):
        return bool(settings.SAFE_REPLAY_ALLOW_DELTA_EVENTS)
    return False


def can_replay_batch(event_types: list[str]) -> bool:
    if not event_types:
        return False
    if len(set(event_types)) > 1:
        return False
    return can_replay_item(event_types[0])


def decide_safe_replay_action(
    event_type: str,
    item_count: int = 1,
    batch_count: int = 1,
) -> ReplaySupportDecision:
    if not settings.ENABLE_SAFE_REPLAY_SUPPORT:
        return ReplaySupportDecision(
            allowed=False,
            action="investigate_manually",
            reason="SAFE_REPLAY_SUPPORT disabled",
            safe_scope="none",
        )

    abuse = validate_replay_request([event_type], item_count, batch_count, settings)
    if not abuse.allowed:
        from infrastructure.security import data_governance_logger as dg_log

        dg_log.emit_replay_abuse_guard_blocked(
            reason=abuse.reason,
            replay_item_count=item_count,
            replay_batch_count=batch_count,
        )
        return ReplaySupportDecision(
            allowed=False,
            action="investigate_manually",
            reason=abuse.reason,
            safe_scope="none",
        )

    et = (event_type or "").strip().lower()
    mi = int(getattr(settings, "SAFE_REPLAY_MAX_ITEMS_PER_ACTION", 20) or 20)
    mb = int(getattr(settings, "SAFE_REPLAY_MAX_BATCHES_PER_ACTION", 3) or 3)

    if item_count == 1 and batch_count <= 1:
        action: RunbookAction = "replay_product_found" if et == "product_found" else "investigate_manually"
        return ReplaySupportDecision(
            allowed=action == "replay_product_found",
            action=action,
            reason="single bounded replay within policy",
            safe_scope="single_item",
        )
    if (
        item_count <= mi
        and batch_count <= mb
        and batch_count >= 1
        and can_replay_item(et)
    ):
        return ReplaySupportDecision(
            allowed=True,
            action="retry_batch_once",
            reason="homogeneous batch within SAFE_REPLAY_MAX_ITEMS_PER_ACTION/BATCHES",
            safe_scope="single_batch",
        )
    return ReplaySupportDecision(
        allowed=False,
        action="investigate_manually",
        reason="replay shape not covered by safe policy",
        safe_scope="none",
    )
