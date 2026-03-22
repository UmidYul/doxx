from __future__ import annotations

import hashlib
import json
from typing import Any

from config.settings import settings


def build_request_idempotency_key(
    entity_key: str,
    payload_hash: str,
    event_type: str,
    scope: str = "entity_payload",
) -> str:
    """Deterministic idempotency key; never uses ``event_id`` (except ``event_only`` scope)."""
    scope = scope or settings.PARSER_IDEMPOTENCY_SCOPE_DEFAULT
    et = (event_type or "product_found").strip()
    ek = (entity_key or "").strip()
    ph = (payload_hash or "").strip()

    if scope == "entity_only":
        raw = f"{ek}|{et}"
    elif scope == "event_only":
        raise ValueError("event_only scope requires explicit event_id — use build_event_only_idempotency_key()")
    else:
        raw = f"{ek}|{ph}|{et}"

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"idemp:v1:{scope}:{digest[:48]}"


def build_event_only_idempotency_key(event_id: str) -> str:
    """Debug/legacy: ties key to a single delivery attempt (not replay-stable)."""
    h = hashlib.sha256(f"event_only|{event_id}".encode()).hexdigest()
    return f"idemp:v1:event_only:{h[:48]}"


def build_snapshot_fingerprint(normalized: dict[str, Any]) -> str:
    """Stable fingerprint of normalized snapshot fields (subset of CRM payload identity)."""
    store = str(normalized.get("store") or "")
    url = str(normalized.get("url") or "")
    sid = normalized.get("source_id")
    sid = str(sid).strip() if isinstance(sid, str) else ""
    title = str(normalized.get("title_clean") or normalized.get("title") or "")
    pv = normalized.get("price_value")
    stock = normalized.get("in_stock")
    blob = json.dumps(
        {"store": store, "url": url, "source_id": sid, "title": title, "price_value": pv, "in_stock": stock},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def is_replay_safe_event_type(event_type: str) -> bool:
    """``product_found`` is replay-safe core; deltas are not by default."""
    et = (event_type or "").strip().lower()
    if et == "product_found":
        return True
    return bool(settings.PARSER_ALLOW_SAFE_RESEND_DELTA_EVENTS) and et in (
        "price_changed",
        "out_of_stock",
        "characteristic_added",
    )
