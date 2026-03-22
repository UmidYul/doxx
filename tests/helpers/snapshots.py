from __future__ import annotations

import re
from typing import Any

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def normalize_stable_value(v: Any, *, key_hint: str = "") -> Any:
    """Replace volatile scalars for contract snapshots."""
    if isinstance(v, dict):
        return normalize_stable_dict(v)
    if isinstance(v, list):
        return [normalize_stable_value(x, key_hint="") for x in v]
    if isinstance(v, str):
        kl = key_hint.lower()
        if kl in ("id", "event_id", "request_idempotency_key") and _UUID_RE.match(v):
            return "<uuid>"
        if kl.endswith("_at") or kl in ("time", "scraped_at", "sent_at", "started_at", "created_at", "flushed_at"):
            if _ISO_RE.match(v) or "T" in v[:20]:
                return "<iso8601>"
        if kl == "payload_hash" and v.startswith("sha256:"):
            return "sha256:<redacted>"
        return v
    return v


def normalize_stable_dict(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in sorted(d.items()):
        out[k] = normalize_stable_value(v, key_hint=k)
    return out
