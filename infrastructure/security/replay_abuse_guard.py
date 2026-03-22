from __future__ import annotations

from config.settings import Settings, settings as app_settings
from domain.data_governance import ReplayAbuseDecision

_DELTA_TYPES = frozenset({"price_changed", "out_of_stock", "characteristic_added"})


def _safe_event_types(settings: Settings) -> list[str]:
    if getattr(settings, "SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY", True):
        if getattr(settings, "SAFE_REPLAY_ALLOW_PRODUCT_FOUND", True):
            return ["product_found"]
        return []
    out: list[str] = []
    if getattr(settings, "SAFE_REPLAY_ALLOW_PRODUCT_FOUND", True):
        out.append("product_found")
    if getattr(settings, "SAFE_REPLAY_ALLOW_DELTA_EVENTS", False):
        out.extend(sorted(_DELTA_TYPES))
    return out


def is_safe_replay_event_set(event_types: list[str], settings: Settings | None = None) -> bool:
    s = settings or app_settings
    if not getattr(s, "ENABLE_REPLAY_ABUSE_GUARDS", True):
        return True
    if not event_types:
        return False
    allowed = set(_safe_event_types(s))
    norm = {str(e).strip().lower() for e in event_types}
    if len(norm) != 1:
        return False
    et = next(iter(norm))
    return et in allowed


def is_safe_replay_scope(item_count: int, batch_count: int, settings: Settings | None = None) -> bool:
    s = settings or app_settings
    if not getattr(s, "ENABLE_REPLAY_ABUSE_GUARDS", True):
        return True
    mi = int(getattr(s, "SAFE_REPLAY_MAX_ITEMS_PER_ACTION", 20) or 20)
    mb = int(getattr(s, "SAFE_REPLAY_MAX_BATCHES_PER_ACTION", 3) or 3)
    return item_count <= mi and batch_count <= mb


def validate_replay_request(
    event_types: list[str],
    item_count: int,
    batch_count: int,
    settings: Settings | None = None,
) -> ReplayAbuseDecision:
    s = settings or app_settings
    mi = int(getattr(s, "SAFE_REPLAY_MAX_ITEMS_PER_ACTION", 20) or 20)
    mb = int(getattr(s, "SAFE_REPLAY_MAX_BATCHES_PER_ACTION", 3) or 3)
    safe_types = _safe_event_types(s)

    if not getattr(s, "ENABLE_REPLAY_ABUSE_GUARDS", True):
        return ReplayAbuseDecision(
            allowed=True,
            reason="replay_abuse_guards_disabled",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    if not is_safe_replay_scope(item_count, batch_count, s):
        return ReplayAbuseDecision(
            allowed=False,
            reason=f"scope_exceeds_policy items={item_count} batches={batch_count}",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    if not event_types:
        return ReplayAbuseDecision(
            allowed=False,
            reason="empty_event_types",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    norm = [str(e).strip().lower() for e in event_types]
    if len(set(norm)) > 1:
        return ReplayAbuseDecision(
            allowed=False,
            reason="heterogeneous_event_types_not_allowed",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    et = norm[0]
    if getattr(s, "SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY", True) and et != "product_found":
        return ReplayAbuseDecision(
            allowed=False,
            reason="SAFE_REPLAY_REQUIRE_PRODUCT_FOUND_ONLY",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    if et not in safe_types:
        return ReplayAbuseDecision(
            allowed=False,
            reason=f"event_type_not_allowed:{et}",
            max_items=mi,
            max_batches=mb,
            safe_event_types=safe_types,
        )

    return ReplayAbuseDecision(
        allowed=True,
        reason="within_replay_policy",
        max_items=mi,
        max_batches=mb,
        safe_event_types=safe_types,
    )
