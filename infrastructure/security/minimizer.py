from __future__ import annotations

import copy
from typing import Any

from config.settings import Settings, settings as app_settings
from infrastructure.security.data_policy_registry import default_policy_for_unknown, get_field_policy
from infrastructure.security.redaction import redact_payload, redact_url

_MAX_LOG_STRING = 400
_MAX_LOG_LIST = 30
_MAX_SUPPORT_SPECS_KEYS = 40
_MAX_SUPPORT_IMAGE_URLS = 12


def _settings(s: Settings | None) -> Settings:
    return s or app_settings


def _policy_for(key: str):
    return get_field_policy(key) or default_policy_for_unknown(key)


def minimize_payload_for_logging(payload: dict[str, object]) -> dict[str, object]:
    """Drop or shrink fields that must not appear in structured logs."""
    s = _settings(None)
    if not getattr(s, "ENABLE_DATA_MINIMIZATION", True):
        return dict(payload)
    out: dict[str, object] = {}
    for k, v in payload.items():
        pol = _policy_for(str(k))
        if not pol.loggable:
            continue
        out[k] = _shrink_value(v, max_list=_MAX_LOG_LIST, max_str=_MAX_LOG_STRING)
        if pol.redact_required and isinstance(out[k], dict):
            out[k] = redact_payload(out[k])  # type: ignore[arg-type]
    return out


def minimize_payload_for_support(
    payload: dict[str, object],
    settings: Settings | None = None,
    *,
    purpose: str = "support",
) -> dict[str, object]:
    """Support / export / observability: honor SUPPORT_EXPORT_* and field policies."""
    s = _settings(settings)
    base = copy.deepcopy(payload) if getattr(s, "ENABLE_DATA_MINIMIZATION", True) else dict(payload)

    from infrastructure.security.support_scope_guard import should_include_field

    p = purpose
    out: dict[str, object] = {}
    for k, v in base.items():
        sk = str(k)
        if not should_include_field(sk, p, s):
            continue
        pol = _policy_for(sk)
        if not pol.exportable:
            continue
        if sk == "raw_specs" and not getattr(s, "SUPPORT_EXPORT_INCLUDE_RAW_SPECS", True):
            out[sk] = {"_omitted": True, "count": len(v) if isinstance(v, dict) else None}
            continue
        if sk == "typed_specs" and not getattr(s, "SUPPORT_EXPORT_INCLUDE_TYPED_SPECS", True):
            out[sk] = {"_omitted": True, "count": len(v) if isinstance(v, dict) else None}
            continue
        if sk == "field_confidence" and not getattr(s, "SUPPORT_EXPORT_INCLUDE_FIELD_CONFIDENCE", False):
            continue
        if sk == "suppressed_typed_fields" and not getattr(s, "SUPPORT_EXPORT_INCLUDE_SUPPRESSED_FIELDS", False):
            continue
        if sk in ("source_url", "category_url", "url") and isinstance(v, str):
            out[sk] = _minimize_url_str(v, s)
            continue
        if sk == "image_urls" and isinstance(v, list):
            out[sk] = [_minimize_url_str(str(x), s) for x in v[:_MAX_SUPPORT_IMAGE_URLS]]
            continue
        if sk == "raw_specs" and isinstance(v, dict):
            keys = list(v.keys())[:_MAX_SUPPORT_SPECS_KEYS]
            out[sk] = {kk: _shrink_value(v[kk], max_list=15, max_str=200) for kk in keys}
            continue
        if sk == "typed_specs" and isinstance(v, dict):
            keys = list(v.keys())[:_MAX_SUPPORT_SPECS_KEYS]
            out[sk] = {kk: _shrink_value(v[kk], max_list=15, max_str=200) for kk in keys}
            continue
        out[sk] = _shrink_value(v, max_list=_MAX_LOG_LIST, max_str=_MAX_LOG_STRING)

    return redact_payload(out)  # type: ignore[return-value]


def minimize_headers_for_support(headers: dict[str, object], settings: Settings | None = None) -> dict[str, object]:
    s = _settings(settings)
    if getattr(s, "SUPPORT_EXPORT_INCLUDE_RAW_HEADERS", False):
        from infrastructure.security.redaction import redact_headers

        return redact_headers(headers)
    return {"_omitted": True, "note": "raw_headers_disabled_by_policy"}


def minimize_trace_record(record: dict[str, object]) -> dict[str, object]:
    """Compact trace-shaped dict for retention / secondary export."""
    s = _settings(None)
    if not getattr(s, "ENABLE_DATA_MINIMIZATION", True):
        return dict(record)
    slim = {
        k: v
        for k, v in record.items()
        if k in ("timestamp", "stage", "severity", "message_code", "failure_domain", "failure_type")
    }
    corr = record.get("correlation")
    if isinstance(corr, dict):
        slim["correlation"] = {
            kk: vv
            for kk, vv in corr.items()
            if kk
            in (
                "run_id",
                "store_name",
                "spider_name",
                "entity_key",
                "event_id",
                "batch_id",
                "source_id",
            )
        }
        su = corr.get("source_url")
        if isinstance(su, str):
            slim["correlation"]["source_url"] = _minimize_url_str(su, s)  # type: ignore[index]
        cu = corr.get("category_url")
        if isinstance(cu, str):
            slim["correlation"]["category_url"] = _minimize_url_str(cu, s)  # type: ignore[index]
    details = record.get("details")
    if isinstance(details, dict):
        slim["details"] = minimize_payload_for_logging(details)  # type: ignore[assignment]
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        slim["metrics"] = minimize_payload_for_logging(metrics)  # type: ignore[assignment]
    return slim


def minimize_diagnostic_snapshot(snapshot: dict[str, object], settings: Settings | None = None) -> dict[str, object]:
    s = _settings(settings)
    if not getattr(s, "ENABLE_SAFE_DIAGNOSTIC_EXPORTS", True):
        return {"enabled": False, "reason": "SAFE_DIAGNOSTIC_EXPORTS disabled"}
    if not getattr(s, "ENABLE_DATA_MINIMIZATION", True):
        return dict(snapshot)
    max_items = int(getattr(s, "DIAGNOSTIC_SNAPSHOT_MAX_ITEMS", 20) or 20)
    out: dict[str, object] = {}
    for k, v in snapshot.items():
        if k.endswith("_sample") or k.startswith("last_") or k == "top_alerts":
            if isinstance(v, list):
                out[k] = [_minimize_nested_dict_item(x, s, max_items) for x in v[:max_items]]
            else:
                out[k] = v
        elif k == "counters_merged_summary" and isinstance(v, dict):
            keys = sorted(v.keys())[:50]
            out[k] = {kk: v[kk] for kk in keys}
        else:
            out[k] = v if not isinstance(v, str) else _minimize_url_str(v, s)
    return redact_payload(out)  # type: ignore[return-value]


def _minimize_nested_dict_item(x: object, s: Settings, max_depth_items: int) -> object:
    if not isinstance(x, dict):
        return x
    d = dict(x)
    if "source_url" in d and isinstance(d["source_url"], str):
        d["source_url"] = _minimize_url_str(d["source_url"], s)
    if "category_url" in d and isinstance(d["category_url"], str):
        d["category_url"] = _minimize_url_str(d["category_url"], s)
    return {ik: iv for ik, iv in list(d.items())[:max_depth_items]}


def _minimize_url_str(url: str, s: Settings) -> str:
    from infrastructure.security.redaction import minimize_url_for_support

    return minimize_url_for_support(
        url,
        full_query_allowed=bool(getattr(s, "SUPPORT_EXPORT_INCLUDE_FULL_URL_QUERY", False)),
    )


def _shrink_value(v: object, *, max_list: int, max_str: int) -> object:
    if isinstance(v, str):
        if len(v) > max_str:
            return v[:max_str] + "…"
        return v
    if isinstance(v, list):
        return [_shrink_value(x, max_list=max_list, max_str=max_str) for x in v[:max_list]]
    if isinstance(v, dict):
        items = list(v.items())[:max_list]
        return {str(kk): _shrink_value(vv, max_list=max_list, max_str=max_str) for kk, vv in items}
    return v


def count_fields(payload: dict[str, object]) -> tuple[int, int]:
    """Return (top_level_keys, approximate_leaf_count)."""
    n_top = len(payload)
    leaves = 0

    def _walk(o: object) -> None:
        nonlocal leaves
        if isinstance(o, dict):
            for vv in o.values():
                _walk(vv)
            leaves += len(o)
        elif isinstance(o, list):
            for vv in o:
                _walk(vv)
            leaves += len(o)
        else:
            leaves += 1

    _walk(payload)
    return n_top, leaves
