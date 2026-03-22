from __future__ import annotations

from typing import Any

from infrastructure.observability.payload_summary import summarize_apply_result, summarize_normalized_payload
from infrastructure.security.minimizer import minimize_payload_for_logging
from infrastructure.security.redaction import redact_mapping_for_logs


def _clip_dict(d: dict[str, Any], max_keys: int) -> dict[str, Any]:
    if len(d) <= max_keys:
        return d
    keys = list(d.keys())[:max_keys]
    return {k: d[k] for k in keys}


def build_normalized_debug_view(normalized: dict[str, object], settings: Any) -> dict[str, object]:
    """Compact normalized slice for dev consoles (9B)."""
    stg = settings
    max_items = int(getattr(stg, "DEV_DEBUG_MAX_ITEMS", 20))
    out: dict[str, object] = {
        "kind": "normalized_debug_v1",
        "summary": summarize_normalized_payload(normalized if isinstance(normalized, dict) else {}),
    }
    if getattr(stg, "DEV_DEBUG_INCLUDE_RAW_SPECS", True) and isinstance(normalized, dict):
        raw = normalized.get("raw_specs")
        if isinstance(raw, dict):
            out["raw_specs_sample"] = _clip_dict(
                {k: str(v)[:200] for k, v in raw.items()},
                max_items,
            )
    if getattr(stg, "DEV_DEBUG_INCLUDE_TYPED_SPECS", True) and isinstance(normalized, dict):
        typed = normalized.get("typed_specs")
        if hasattr(typed, "model_dump"):
            typed = typed.model_dump(mode="json")
        if isinstance(typed, dict):
            out["typed_specs_sample"] = _clip_dict({k: str(v)[:200] for k, v in typed.items()}, max_items)
    return redact_mapping_for_logs(out)


def build_lifecycle_debug_view(
    event: dict[str, object],
    decision: dict[str, object] | None = None,
) -> dict[str, object]:
    ev = minimize_payload_for_logging(dict(event)) if isinstance(event, dict) else {}
    dec = minimize_payload_for_logging(dict(decision or {}))
    return {
        "kind": "lifecycle_debug_v1",
        "event_preview": ev,
        "decision_preview": dec,
    }


def build_apply_debug_view(result: dict[str, object]) -> dict[str, object]:
    """Wrap payload_summary for dict-shaped apply results."""
    from domain.crm_apply_result import CrmApplyResult

    if isinstance(result, dict) and "success" in result:
        try:
            r = CrmApplyResult.model_validate(result)
            return {"kind": "apply_debug_v1", "summary": summarize_apply_result(r)}
        except Exception:
            pass
    return {"kind": "apply_debug_v1", "summary": redact_mapping_for_logs(dict(result))}


def build_store_debug_summary(
    *,
    store_name: str,
    normalized: dict[str, object] | None = None,
    lifecycle_event: dict[str, object] | None = None,
    apply_summary: dict[str, object] | None = None,
    settings: Any | None = None,
) -> dict[str, object]:
    from config.settings import settings as app_settings

    stg = settings if settings is not None else app_settings
    sections: list[str] = []
    payload: dict[str, object] = {"kind": "store_debug_summary_v1", "store_name": store_name}
    if normalized is not None and getattr(stg, "DEV_DEBUG_INCLUDE_RAW_SPECS", True):
        payload["normalized"] = build_normalized_debug_view(normalized, stg)
        sections.append("normalized")
    if lifecycle_event is not None and getattr(stg, "DEV_DEBUG_INCLUDE_LIFECYCLE", True):
        payload["lifecycle"] = build_lifecycle_debug_view(lifecycle_event)
        sections.append("lifecycle")
    if apply_summary is not None and getattr(stg, "DEV_DEBUG_INCLUDE_APPLY_RESULTS", True):
        payload["apply"] = apply_summary
        sections.append("apply")
    payload["sections_included"] = sections
    return redact_mapping_for_logs(payload)
