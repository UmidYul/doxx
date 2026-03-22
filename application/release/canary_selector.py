from __future__ import annotations

import hashlib


def build_rollout_key(store_name: str, entity_key: str | None = None, feature_name: str | None = None) -> str:
    parts = [store_name.strip().lower()]
    if entity_key and str(entity_key).strip():
        parts.append(str(entity_key).strip())
    elif feature_name:
        parts.append(f"feature:{feature_name.strip()}")
    else:
        parts.append("nostore")
    if feature_name and (entity_key and str(entity_key).strip()):
        parts.append(feature_name.strip())
    return "|".join(parts)


def select_canary_bucket(key: str, percentage: int) -> bool:
    """Deterministic [0,100) bucket: same key always maps to same in/out decision."""
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    h = hashlib.sha256(key.encode("utf-8")).digest()
    bucket = int.from_bytes(h[:4], "big") % 100
    return bucket < percentage
