from __future__ import annotations

from typing import cast

from domain.compatibility import ChangeType, CompatibilityLevel, ContractChange, ContractSurface

from application.release.deprecation_registry import get_shadow_fields

# Minimal required keys per surface for “required field removal = breaking” heuristics.
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "crm_payload": frozenset(
        {
            "schema_version",
            "entity_key",
            "payload_hash",
            "source_name",
            "source_url",
        }
    ),
    "lifecycle_event": frozenset({"event_type", "payload_hash", "event_id", "sent_at"}),
    "apply_result": frozenset({"ok"}),
    "replay_metadata": frozenset({"replay_mode"}),
    "etl_status": frozenset({"schema", "run_id", "current_status"}),
    "diagnostic_snapshot": frozenset(),
    "operator_summary": frozenset(),
}

# CRM / downstream coupling: unexpected loss of identity or quality metadata is breaking.
# ETL / observability: removing these keys is treated as breaking for downstream dashboards.
_ETL_BREAKING_IF_REMOVED: frozenset[str] = frozenset(
    {
        "counters_summary",
        "errors_by_domain",
        "schema",
    }
)

_QUALITY_ID_KEYS: frozenset[str] = frozenset(
    {
        "entity_key",
        "payload_hash",
        "event_id",
        "request_idempotency_key",
        "replay_mode",
        "crm_listing_id",
        "crm_product_id",
        "source_id",
        "external_ids",
    }
)

_LIFECYCLE_SEMANTIC_KEYS: frozenset[str] = frozenset(
    {
        "lifecycle_default_event",
        "default_event_type",
        "PARSER_LIFECYCLE_DEFAULT_EVENT",
    }
)


def _as_surface(surface: str) -> ContractSurface:
    allowed: tuple[str, ...] = (
        "crm_payload",
        "lifecycle_event",
        "apply_result",
        "replay_metadata",
        "etl_status",
        "diagnostic_snapshot",
        "operator_summary",
    )
    if surface not in allowed:
        raise ValueError(f"unknown contract surface: {surface!r}")
    return cast(ContractSurface, surface)


def _flatten_keys(obj: object, prefix: str = "") -> dict[str, object]:
    """Dot-path flatten for dict nesting; dict keys are always registered (empty dict counts)."""
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out[p] = v
                out.update(_flatten_keys(v, p))
            else:
                out[p] = v
    return out


def is_breaking_field_change(old_value: object, new_value: object) -> bool:
    """Type / representation drift that typically breaks strict CRM consumers."""
    if type(old_value) is not type(new_value):
        # bool is subclass of int in Python — treat as breaking if mixed
        if isinstance(old_value, bool) or isinstance(new_value, bool):
            return isinstance(old_value, bool) != isinstance(new_value, bool)
        if isinstance(old_value, int) and isinstance(new_value, int):
            return False
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            return False
        return True
    if isinstance(old_value, dict) and isinstance(new_value, dict):
        if set(old_value.keys()) != set(new_value.keys()):
            return True
        for k in old_value:
            if is_breaking_field_change(old_value[k], new_value[k]):
                return True
        return False
    if isinstance(old_value, list) and isinstance(new_value, list):
        return False
    return False


def is_additive_field_change(old_payload: dict[str, object], new_payload: dict[str, object]) -> bool:
    """True if new is a superset with compatible values on shared keys."""
    flat_old = _flatten_keys(old_payload)
    flat_new = _flatten_keys(new_payload)
    for k, v_old in flat_old.items():
        if k not in flat_new:
            return False
        if is_breaking_field_change(v_old, flat_new[k]):
            return False
    return any(k not in flat_old for k in flat_new)


def detect_behavioral_change(
    surface: str,
    metadata_before: dict[str, object],
    metadata_after: dict[str, object],
) -> list[ContractChange]:
    """Semantic lifecycle / policy metadata changes (not pure shape)."""
    changes: list[ContractChange] = []
    if surface not in ("lifecycle_event", "crm_payload", "replay_metadata"):
        return changes
    surf = _as_surface(surface)
    for key in _LIFECYCLE_SEMANTIC_KEYS:
        b = metadata_before.get(key)
        a = metadata_after.get(key)
        if b is None and a is None:
            continue
        if b != a:
            level: CompatibilityLevel = "breaking" if key in ("lifecycle_default_event", "default_event_type") else "conditionally_compatible"
            ctype: ChangeType = "breaking" if level == "breaking" else "behavioral"
            changes.append(
                ContractChange(
                    surface=surf,
                    change_name=f"lifecycle_semantic:{key}",
                    change_type=ctype,
                    compatibility_level=level,
                    affected_fields=[key],
                    notes=[f"default lifecycle semantic drift: {b!r} -> {a!r}"],
                )
            )
    return changes


def classify_contract_change(
    surface: str,
    baseline: dict[str, object],
    current: dict[str, object],
) -> list[ContractChange]:
    """
    Diff baseline vs current.

    Policy (high level):
    - optional field addition at top-level → additive
    - removing a field present in baseline → breaking (especially if required for surface)
    - rename without both names → modeled as remove + add → breaking
    - type change on a shared field → breaking
    - loss of ids/quality keys on crm/lifecycle-like surfaces → breaking
    """
    surf = _as_surface(surface)
    changes: list[ContractChange] = []

    flat_b = _flatten_keys(baseline)
    flat_c = _flatten_keys(current)
    required = _REQUIRED_FIELDS.get(surface, frozenset())

    for path in flat_b:
        if path not in flat_c:
            base_key = path.split(".")[-1]
            sev: CompatibilityLevel = "breaking" if base_key in required or path in required else "conditionally_compatible"
            ctype: ChangeType = "breaking" if sev == "breaking" else "deprecation"
            note = "field removed vs baseline"
            if surface == "etl_status" and base_key in _ETL_BREAKING_IF_REMOVED:
                sev = "breaking"
                ctype = "breaking"
                note = "critical ETL export field removed — breaking for observability consumers"
            if base_key in _QUALITY_ID_KEYS and surface in ("crm_payload", "lifecycle_event", "replay_metadata"):
                sev = "breaking"
                ctype = "breaking"
                note = "identity/quality metadata removed — breaking for dependent surfaces"
            changes.append(
                ContractChange(
                    surface=surf,
                    change_name=f"removed_field:{path}",
                    change_type=ctype,
                    compatibility_level=sev,
                    affected_fields=[path],
                    notes=[note],
                )
            )

    for path, cur_v in flat_c.items():
        if path not in flat_b:
            changes.append(
                ContractChange(
                    surface=surf,
                    change_name=f"added_field:{path}",
                    change_type="additive",
                    compatibility_level="backward_compatible",
                    affected_fields=[path],
                    notes=["new optional field vs baseline"],
                )
            )
            continue
        base_v = flat_b[path]
        if is_breaking_field_change(base_v, cur_v):
            changes.append(
                ContractChange(
                    surface=surf,
                    change_name=f"type_or_shape_drift:{path}",
                    change_type="breaking",
                    compatibility_level="breaking",
                    affected_fields=[path],
                    notes=[f"type/shape drift vs baseline ({type(base_v).__name__} -> {type(cur_v).__name__})"],
                )
            )

    changes.extend(detect_behavioral_change(surface, dict(baseline), dict(current)))
    changes = _collapse_shadow_renames(surface, changes)
    changes.extend(_suspected_rename_without_shadow(surface, changes))
    return changes


def _suspected_rename_without_shadow(surface: str, changes: list[ContractChange]) -> list[ContractChange]:
    """If a top-level field disappears and another appears (no shadow_rename), treat as breaking rename."""
    if surface != "crm_payload":
        return []
    if any(c.change_name.startswith("shadow_rename:") for c in changes):
        return []
    removed_tl = [
        c.change_name.removeprefix("removed_field:")
        for c in changes
        if c.change_name.startswith("removed_field:") and "." not in c.change_name.removeprefix("removed_field:")
    ]
    added_tl = [
        c.change_name.removeprefix("added_field:")
        for c in changes
        if c.change_name.startswith("added_field:") and "." not in c.change_name.removeprefix("added_field:")
    ]
    if not removed_tl or not added_tl:
        return []
    surf = _as_surface(surface)
    return [
        ContractChange(
            surface=surf,
            change_name="rename_without_shadow_or_bridge",
            change_type="breaking",
            compatibility_level="breaking",
            affected_fields=sorted(set(removed_tl + added_tl)),
            notes=["rename/remove+add without shadow mapping — breaking for strict CRM consumers"],
        )
    ]


def _collapse_shadow_renames(surface: str, changes: list[ContractChange]) -> list[ContractChange]:
    """If a remove+add matches shadow registry (legacy→canonical), treat as conditional rename, not breaking."""
    shadow = get_shadow_fields(surface)
    if not shadow:
        return changes

    removed: dict[str, ContractChange] = {}
    added: dict[str, ContractChange] = {}
    rest: list[ContractChange] = []
    for c in changes:
        if c.change_name.startswith("removed_field:"):
            field = c.change_name.removeprefix("removed_field:")
            removed[field] = c
        elif c.change_name.startswith("added_field:"):
            field = c.change_name.removeprefix("added_field:")
            added[field] = c
        else:
            rest.append(c)

    consumed_removed: set[str] = set()
    consumed_added: set[str] = set()
    collapsed: list[ContractChange] = []

    for legacy, canonical in shadow.items():
        rchg = removed.get(legacy)
        achg = added.get(canonical)
        if rchg and achg and rchg.compatibility_level != "backward_compatible":
            consumed_removed.add(legacy)
            consumed_added.add(canonical)
            collapsed.append(
                ContractChange(
                    surface=rchg.surface,
                    change_name=f"shadow_rename:{legacy}->{canonical}",
                    change_type="deprecation",
                    compatibility_level="conditionally_compatible",
                    affected_fields=[legacy, canonical],
                    notes=["field rename bridged via shadow mapping; CRM should migrate to canonical field"],
                )
            )

    for k, c in removed.items():
        if k not in consumed_removed:
            rest.append(c)
    for k, c in added.items():
        if k not in consumed_added:
            rest.append(c)
    return rest + collapsed
