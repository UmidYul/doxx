from __future__ import annotations

from typing import Any

from application.extractors import unit_normalizer as un


def _equivalent(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) < 1e-6
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return str(a).strip().lower() == str(b).strip().lower()


def is_plausible_typed_value(field_name: str, value: Any) -> bool:
    if value is None:
        return False
    if field_name == "ram_gb":
        return un.is_plausible_ram_gb(int(value)) if isinstance(value, (int, float)) else False
    if field_name == "storage_gb":
        return un.is_plausible_storage_gb(int(value)) if isinstance(value, (int, float)) else False
    if field_name == "display_size_inch":
        return un.is_plausible_display_size(float(value)) if isinstance(value, (int, float)) else False
    if field_name == "battery_mah":
        return un.is_plausible_battery_mah(int(value)) if isinstance(value, (int, float)) else False
    if field_name == "weight_g":
        return un.is_plausible_weight_g(int(value)) if isinstance(value, (int, float)) else False
    if field_name == "weight_kg":
        return un.is_plausible_weight_kg(float(value)) if isinstance(value, (int, float)) else False
    return True


def resolve_typed_field_candidates(
    field_name: str,
    candidates: list[tuple[str, str, Any]],
) -> tuple[Any | None, list[str]]:
    """Merge multiple raw contributions to one typed field.

    Returns ``(chosen_value, warning_codes)``.
    """
    warnings: list[str] = []
    parsed = [(rk, rv, nv) for rk, rv, nv in candidates if nv is not None]
    if not parsed:
        return None, warnings

    values = [nv for _, _, nv in parsed]
    if len(values) == 1:
        v = values[0]
        if not is_plausible_typed_value(field_name, v):
            return None, ["implausible_value"]
        return v, warnings

    first = values[0]
    if all(_equivalent(first, v) for v in values[1:]):
        if not is_plausible_typed_value(field_name, first):
            return None, ["implausible_value"]
        return first, warnings

    plausible_vals = [v for v in values if is_plausible_typed_value(field_name, v)]
    if not plausible_vals:
        return None, warnings + ["implausible_value", "multiple_values_for_same_field"]

    warnings.append("multiple_values_for_same_field")
    # Prefer first plausible in crawl order (deterministic).
    return plausible_vals[0], warnings
