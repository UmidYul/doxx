from __future__ import annotations

from config.settings import settings
from domain.operator_support import RunbookPlan, TriageSummary
from infrastructure.security.minimizer import minimize_payload_for_support
from infrastructure.security.redaction import redact_payload

# Keys that must never appear in operator-facing JSON (avoid blob / noise).
_NOISY_SNAPSHOT_KEYS = frozenset({"details", "raw", "payload", "response_body", "stack_trace", "trace_dump"})


def serialize_triage_summary(summary: TriageSummary) -> dict[str, object]:
    d = summary.model_dump(mode="json")
    d["evidence"] = [_strip_evidence_row(e) for e in summary.evidence]
    redacted = redact_payload(d)
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        return minimize_payload_for_support(redacted, settings)
    return redacted


def _strip_evidence_row(row: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in row.items() if k not in _NOISY_SNAPSHOT_KEYS}


def serialize_runbook(plan: RunbookPlan) -> dict[str, object]:
    raw = redact_payload(plan.model_dump(mode="json"))
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        return minimize_payload_for_support(raw, settings)
    return raw


def serialize_diagnostic_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    """Return a JSON-friendly snapshot without trace dumps or oversized blobs."""
    out: dict[str, object] = {}
    for k, v in snapshot.items():
        if k in _NOISY_SNAPSHOT_KEYS:
            continue
        if k.endswith("_sample") or k.startswith("last_") or k == "top_alerts":
            out[k] = _sanitize_list(v)
        elif k == "counters_merged_summary" and isinstance(v, dict):
            out[k] = {sk: sv for sk, sv in list(v.items())[:50]}
        else:
            out[k] = v
    from application.release.shape_compat import apply_export_compatibility

    from infrastructure.security.minimizer import minimize_diagnostic_snapshot

    compat = apply_export_compatibility("diagnostic_snapshot", out)
    red = redact_payload(compat)
    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True) and getattr(settings, "ENABLE_SAFE_DIAGNOSTIC_EXPORTS", True):
        return minimize_diagnostic_snapshot(red, settings)  # type: ignore[return-value]
    return red  # type: ignore[return-value]


def _sanitize_list(v: object) -> object:
    if not isinstance(v, list):
        return v
    cleaned: list[object] = []
    for item in v[:50]:
        if isinstance(item, dict):
            cleaned.append({ik: iv for ik, iv in item.items() if ik not in _NOISY_SNAPSHOT_KEYS})
        else:
            cleaned.append(item)
    return cleaned
