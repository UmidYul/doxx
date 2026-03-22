from __future__ import annotations

from domain.compatibility import DeprecationNotice, DeprecationStatus

# Static registry: extend per release. Tests may patch ``_REGISTRY`` or ``get_deprecations``.
_REGISTRY: dict[str, list[DeprecationNotice]] = {
    "crm_payload": [],
    "lifecycle_event": [],
    "etl_status": [],
    "diagnostic_snapshot": [],
}


def get_deprecations(surface: str) -> list[DeprecationNotice]:
    return list(_REGISTRY.get(surface, []))


def get_shadow_fields(surface: str) -> dict[str, str]:
    """
    Map **legacy/shadow field name → canonical replacement field**.
    When ``replacement_field`` is set and status is ``shadow``, both may be emitted.
    """
    out: dict[str, str] = {}
    for n in get_deprecations(surface):
        if n.status == "shadow" and n.replacement_field:
            out[n.field_name] = n.replacement_field
    return dict(out)


def is_field_deprecated(surface: str, field_name: str) -> bool:
    for n in get_deprecations(surface):
        if n.field_name == field_name and n.status in ("deprecated", "shadow"):
            return True
    return False


def build_deprecation_warnings(surface: str, payload: dict[str, object]) -> list[str]:
    """Human-readable warnings when payload still uses deprecated field names."""
    warnings: list[str] = []
    flat: dict[str, object] = {}
    stack: list[tuple[str, dict[str, object]]] = [("", payload)]
    while stack:
        prefix, d = stack.pop()
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                stack.append((path, v))
            flat[path] = v
    keys = set(flat.keys()) | set(payload.keys())
    for n in get_deprecations(surface):
        if n.status not in ("deprecated", "shadow"):
            continue
        if n.field_name in keys or any(p == n.field_name or p.endswith(f".{n.field_name}") for p in keys):
            rep = n.replacement_field or "n/a"
            warnings.append(
                f"deprecated_field:{surface}:{n.field_name}:replacement={rep}:reason={n.deprecation_reason}"
            )
    return warnings


def register_deprecation_notice(notice: DeprecationNotice) -> None:
    """Register a deprecation (used by tests and release prep; not for hot reload in production)."""
    surf: str = str(notice.surface)
    if surf not in _REGISTRY:
        _REGISTRY[surf] = []
    _REGISTRY[surf].append(notice)


def clear_deprecation_registry_for_tests() -> None:
    """Test helper: reset registry to known empty surfaces."""
    _REGISTRY.clear()
    for k in ("crm_payload", "lifecycle_event", "etl_status", "diagnostic_snapshot"):
        _REGISTRY[k] = []
