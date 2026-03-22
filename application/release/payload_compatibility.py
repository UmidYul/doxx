from __future__ import annotations

from typing import Any

from domain.release_quality import CheckCategory, ReleaseCheckResult

from application.release import release_logger as rel_log


def _type_ok(baseline_val: Any, current_val: Any) -> bool:
    if baseline_val is None:
        return True
    if isinstance(baseline_val, bool):
        return isinstance(current_val, bool)
    if isinstance(baseline_val, int) and not isinstance(baseline_val, bool):
        return isinstance(current_val, int) and not isinstance(current_val, bool)
    if isinstance(baseline_val, float):
        return isinstance(current_val, (int, float))
    if isinstance(baseline_val, str):
        return isinstance(current_val, str)
    if isinstance(baseline_val, list):
        return isinstance(current_val, list)
    if isinstance(baseline_val, dict):
        return isinstance(current_val, dict)
    return type(current_val) is type(baseline_val)


def _compare_shapes(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    check_name: str,
    category: CheckCategory,
    path: str = "",
) -> ReleaseCheckResult:
    notes: list[str] = []
    for key, base_v in baseline.items():
        p = f"{path}.{key}" if path else key
        if key not in current:
            notes.append(f"missing_required:{p}")
            continue
        cur_v = current[key]
        if isinstance(base_v, dict) and isinstance(cur_v, dict):
            sub = _compare_shapes(cur_v, base_v, check_name=check_name, category=category, path=p)
            notes.extend(sub.notes)
        elif not _type_ok(base_v, cur_v):
            notes.append(f"type_drift:{p} expected={type(base_v).__name__} got={type(cur_v).__name__}")
    passed = not notes
    res = ReleaseCheckResult(
        check_name=check_name,
        passed=passed,
        category=category,
        notes=notes,
        artifacts=[],
    )
    if not passed and category == "compatibility":
        rel_log.emit_contract_drift(check_name=check_name, notes=notes)
    return res


def compare_payload_shapes(current_payload: dict[str, object], baseline_payload: dict[str, object]) -> ReleaseCheckResult:
    """Breaking removal/rename or type change of baseline keys fails; extra keys in current are allowed."""
    return _compare_shapes(
        dict(current_payload),
        dict(baseline_payload),
        check_name="payload_shape_compat",
        category="compatibility",
    )


def compare_lifecycle_shapes(current_event: dict[str, object], baseline_event: dict[str, object]) -> ReleaseCheckResult:
    return _compare_shapes(
        dict(current_event),
        dict(baseline_event),
        check_name="lifecycle_shape_compat",
        category="compatibility",
    )


def compare_observability_shapes(current_status: dict[str, object], baseline_status: dict[str, object]) -> ReleaseCheckResult:
    return _compare_shapes(
        dict(current_status),
        dict(baseline_status),
        check_name="observability_shape_compat",
        category="compatibility",
    )
