from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from config.settings import settings

from application.extractors import spec_warning_codes as WC
from application.extractors import unit_normalizer as un
from application.extractors.spec_confidence import get_min_confidence_for_category
from application.extractors.spec_conflicts import is_plausible_typed_value
from application.extractors.spec_coverage import calculate_mapping_ratio
from application.extractors.spec_label_normalizer import normalize_spec_label
from application.extractors.spec_registry_loader import (
    get_category_policy,
    get_field_definitions,
    get_rules_index,
    merged_field_disables,
)
from application.extractors.spec_resolution import resolve_typed_field_candidates
from domain.normalization_quality import FieldConfidence, SuppressedTypedField
from domain.typed_specs import TypedPartialSpecs

logger = logging.getLogger(__name__)

_TYPED_FIELDS = frozenset(TypedPartialSpecs.model_fields.keys())

_PLAUSIBILITY: dict[str, Any] = {
    "is_plausible_ram_gb": un.is_plausible_ram_gb,
    "is_plausible_storage_gb": un.is_plausible_storage_gb,
    "is_plausible_display_size": un.is_plausible_display_size,
    "is_plausible_battery_mah": un.is_plausible_battery_mah,
    "is_plausible_weight_g": un.is_plausible_weight_g,
    "is_plausible_weight_kg": un.is_plausible_weight_kg,
}


def _is_plausible_for_field(field_name: str, value: Any, field_def_plaus: str | None) -> bool:
    if field_def_plaus and field_def_plaus in _PLAUSIBILITY:
        fn = _PLAUSIBILITY[field_def_plaus]
        try:
            return bool(fn(value))
        except (TypeError, ValueError):
            return False
    return is_plausible_typed_value(field_name, value)


def _log_norm(
    event: str,
    *,
    store: str = "",
    source_id: str | None = None,
    url: str = "",
    category_hint: str | None = None,
    raw_label: str | None = None,
    normalized_label: str | None = None,
    typed_field: str | None = None,
    field_name: str | None = None,
    raw_value: str | None = None,
    normalized_value: Any = None,
    confidence: float | None = None,
    threshold: float | None = None,
    reason_code: str | None = None,
    warning_codes: list[str] | None = None,
    alias_priority: int | None = None,
    mapping_ratio: float | None = None,
    raw_field: str | None = None,
) -> None:
    payload = {
        "event": event,
        "store": store or None,
        "source_id": source_id,
        "url": url or None,
        "category_hint": category_hint,
        "raw_label": raw_label,
        "normalized_label": normalized_label,
        "typed_field": typed_field or field_name,
        "field_name": field_name or typed_field,
        "raw_field": raw_field or raw_label,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "confidence": confidence,
        "threshold": threshold,
        "reason_code": reason_code,
        "warning_codes": warning_codes,
        "alias_priority": alias_priority,
        "mapping_ratio": mapping_ratio,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    logger.info("normalize_specs %s", json.dumps(payload, ensure_ascii=False, default=str))


def _candidate_meta(
    *,
    nk: str,
    typed_field: str,
    rule_priority: int | None,
    deprecated_rule: bool,
) -> dict[str, Any]:
    direct_key = nk in _TYPED_FIELDS and typed_field == nk
    ambiguous = (not direct_key) and len(nk) < 4
    store_override_exact = rule_priority is not None and rule_priority >= 70
    return {
        "direct_key": direct_key,
        "rule_priority": rule_priority,
        "deprecated_alias": deprecated_rule,
        "ambiguous_alias": ambiguous,
        "missing_unit": None,
        "store_override_exact_match": store_override_exact,
        "extra_warnings": [],
    }


def resolve_raw_label(
    raw_label: str,
    category_hint: str | None,
    store_name: str | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(canonical_label, typed_field)`` using registry merge order."""
    nk = normalize_spec_label(raw_label)
    if not nk:
        return None, None
    if nk in _TYPED_FIELDS:
        return nk, nk
    idx = get_rules_index(category_hint, store_name)
    rules = idx.get(nk, [])
    if not rules:
        return None, None
    best = rules[0]
    return best.canonical_label, best.typed_field


def _resolve_rule_targets(
    nk: str,
    idx: dict[str, list[Any]],
) -> list[tuple[str, int | None, bool]]:
    if nk in _TYPED_FIELDS:
        return [(nk, None, False)]

    rules = idx.get(nk, [])
    if not rules:
        return []

    best_by_field: dict[str, Any] = {}
    for rule in rules:
        best_by_field.setdefault(rule.typed_field, rule)

    return [
        (typed_field, rule.priority, bool(rule.is_deprecated))
        for typed_field, rule in best_by_field.items()
    ]


def _collect_candidate_from_target(
    *,
    nk: str,
    raw_key: str,
    raw_val: str,
    typed_field: str,
    rule_priority: int | None,
    deprecated_rule: bool,
    st: str | None,
    source_id: str | None,
    url: str,
    category_hint: str | None,
    allowed: frozenset[str],
    disables: frozenset[str],
    field_defs: dict[str, Any],
    warnings: list[str],
    candidates: dict[str, list[tuple[str, str, Any, dict[str, Any]]]],
    mapped_raw_keys: set[str],
    deprecated_hits: list[str],
) -> None:
    if deprecated_rule and settings.ENABLE_DEPRECATED_ALIAS_WARNINGS:
        deprecated_hits.append(nk)
        warnings.append(WC.DEPRECATED_ALIAS)
        _log_norm(
            "SPEC_ALIAS_DEPRECATED",
            store=st or "",
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            raw_label=raw_key,
            normalized_label=nk,
            typed_field=typed_field,
            alias_priority=rule_priority,
            reason_code=WC.DEPRECATED_ALIAS,
            warning_codes=[WC.DEPRECATED_ALIAS],
        )

    _log_norm(
        "SPEC_ALIAS_RESOLVED",
        store=st or "",
        source_id=source_id,
        url=url,
        category_hint=category_hint,
        raw_label=raw_key,
        normalized_label=nk,
        typed_field=typed_field,
        alias_priority=rule_priority,
    )

    if typed_field in disables:
        warnings.append(WC.FIELD_DISABLED_BY_STORE_OVERRIDE)
        _log_norm(
            "SPEC_FIELD_DISABLED_BY_OVERRIDE",
            store=st or "",
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            raw_label=raw_key,
            typed_field=typed_field,
            reason_code=WC.FIELD_DISABLED_BY_STORE_OVERRIDE,
        )
        return

    if typed_field not in allowed:
        warnings.append(WC.CATEGORY_MISMATCH)
        _log_norm(
            "NORMALIZATION_WARNING",
            store=st or "",
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            raw_field=raw_key,
            typed_field=typed_field,
            raw_value=raw_val,
            reason_code=WC.CATEGORY_MISMATCH,
            warning_codes=[WC.CATEGORY_MISMATCH],
        )
        return

    cmeta = _candidate_meta(
        nk=nk,
        typed_field=typed_field,
        rule_priority=rule_priority,
        deprecated_rule=deprecated_rule,
    )

    if typed_field == "ram_gb":
        nv_ram = un.normalize_field_value("ram_gb", raw_val)
        if nv_ram is None:
            stor = un.normalize_storage(raw_val)
            if stor is not None and un.is_plausible_storage_gb(stor):
                cmeta = _candidate_meta(
                    nk=nk,
                    typed_field="storage_gb",
                    rule_priority=rule_priority,
                    deprecated_rule=deprecated_rule,
                )
                cmeta["extra_warnings"] = [WC.RAM_STORAGE_SWAP_SUSPECTED]
                candidates["storage_gb"].append((raw_key, raw_val, stor, cmeta))
                warnings.append(WC.RAM_STORAGE_SWAP_SUSPECTED)
                mapped_raw_keys.add(raw_key)
                _log_norm(
                    "NORMALIZATION_WARNING",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    raw_field=raw_key,
                    typed_field="storage_gb",
                    raw_value=raw_val,
                    normalized_value=stor,
                    reason_code=WC.RAM_STORAGE_SWAP_SUSPECTED,
                    warning_codes=[WC.RAM_STORAGE_SWAP_SUSPECTED],
                )
                return

    nv = un.normalize_field_value(typed_field, raw_val)
    if nv is None:
        if typed_field == "battery_mah" and re.search("(?:mah|\u043c\u0430\u0447)", raw_val, re.I):
            m = re.search(r"(\d+)", raw_val)
            if m and not un.is_plausible_battery_mah(int(m.group(1))):
                warnings.append(WC.IMPLAUSIBLE_VALUE)
                _log_norm(
                    "SPEC_IMPLAUSIBLE",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    raw_field=raw_key,
                    typed_field=typed_field,
                    raw_value=raw_val,
                    reason_code=WC.IMPLAUSIBLE_VALUE,
                    warning_codes=[WC.IMPLAUSIBLE_VALUE],
                )
        if typed_field == "display_size_inch":
            m = re.search(r"(\d+[.,]?\d*)\s*(?:inch|\"|\u2033|\u0434\u044e\u0439\u043c)", raw_val, re.I)
            if m:
                try:
                    dv = float(m.group(1).replace(",", "."))
                    if not un.is_plausible_display_size(dv):
                        warnings.append(WC.IMPLAUSIBLE_VALUE)
                        _log_norm(
                            "SPEC_IMPLAUSIBLE",
                            store=st or "",
                            source_id=source_id,
                            url=url,
                            category_hint=category_hint,
                            raw_field=raw_key,
                            typed_field=typed_field,
                            raw_value=raw_val,
                            normalized_value=dv,
                            reason_code=WC.IMPLAUSIBLE_VALUE,
                            warning_codes=[WC.IMPLAUSIBLE_VALUE],
                        )
                except ValueError:
                    pass
        return

    fd = field_defs.get(typed_field)
    pl_name = fd.plausibility_checker if fd else None
    if not _is_plausible_for_field(typed_field, nv, pl_name):
        warnings.append(WC.IMPLAUSIBLE_VALUE)
        _log_norm(
            "SPEC_IMPLAUSIBLE",
            store=st or "",
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            raw_field=raw_key,
            typed_field=typed_field,
            raw_value=raw_val,
            normalized_value=nv,
            reason_code=WC.IMPLAUSIBLE_VALUE,
            warning_codes=[WC.IMPLAUSIBLE_VALUE],
        )
        return

    candidates[typed_field].append((raw_key, raw_val, nv, cmeta))
    mapped_raw_keys.add(raw_key)
    _log_norm(
        "SPEC_MAPPED",
        store=st or "",
        source_id=source_id,
        url=url,
        category_hint=category_hint,
        raw_field=raw_key,
        typed_field=typed_field,
        raw_value=raw_val,
        normalized_value=nv,
    )


def map_raw_specs_to_typed_partial(
    raw_specs: dict[str, str],
    category_hint: str | None = None,
    *,
    store_name: str | None = None,
    store: str | None = None,
    source_id: str | None = None,
    url: str = "",
) -> tuple[TypedPartialSpecs, list[str], dict[str, Any]]:
    """Registry-driven mapping; returns ``(specs, warnings, meta)``."""
    from application.crm_sync_builder import build_entity_key
    from application.release.rollout_policy_engine import is_feature_enabled

    st = (store_name or store or "").strip() or None
    if st:
        ek = build_entity_key(st, source_id, url)
        if not is_feature_enabled("typed_specs_mapping", st, ek):
            empty = TypedPartialSpecs()
            uc = len([k for k in raw_specs if str(k).strip() and str(raw_specs[k]).strip()])
            return empty, ["typed_specs_mapping_disabled_by_rollout"], {
                "mapping_ratio": 0.0,
                "mapped_fields_count": 0,
                "unmapped_fields_count": uc,
                "field_confidence": {},
                "suppressed_typed_fields": [],
                "conflicting_fields": [],
            }
    warnings: list[str] = []
    policy = get_category_policy(category_hint)
    allowed = policy.enabled_fields
    field_defs = get_field_definitions(category_hint)
    disables = merged_field_disables(st or "", category_hint) if st else frozenset()
    idx = get_rules_index(category_hint, st)

    candidates: dict[str, list[tuple[str, str, Any, dict[str, Any]]]] = defaultdict(list)
    mapped_raw_keys: set[str] = set()
    unmapped_labels: list[str] = []
    deprecated_hits: list[str] = []
    conflicting_fields: list[str] = []
    all_suppressed: list[SuppressedTypedField] = []
    field_confidence: dict[str, FieldConfidence] = {}

    for raw_key, raw_val in raw_specs.items():
        if not str(raw_key).strip() or not str(raw_val).strip():
            continue
        nk = normalize_spec_label(raw_key)
        targets = _resolve_rule_targets(nk, idx)

        if not targets:
            unmapped_labels.append(raw_key)
            _log_norm(
                "SPEC_LABEL_UNMAPPED",
                store=st or "",
                source_id=source_id,
                url=url,
                category_hint=category_hint,
                raw_label=raw_key,
                normalized_label=nk,
                reason_code=WC.UNMAPPED_LABEL,
            )
            continue

        for typed_field, rule_priority, deprecated_rule in targets:
            _collect_candidate_from_target(
                nk=nk,
                raw_key=raw_key,
                raw_val=raw_val,
                typed_field=typed_field,
                rule_priority=rule_priority,
                deprecated_rule=deprecated_rule,
                st=st,
                source_id=source_id,
                url=url,
                category_hint=category_hint,
                allowed=allowed,
                disables=disables,
                field_defs=field_defs,
                warnings=warnings,
                candidates=candidates,
                mapped_raw_keys=mapped_raw_keys,
                deprecated_hits=deprecated_hits,
            )

    order = list(policy.extraction_priority_order)
    rank = {name: i for i, name in enumerate(order)}

    resolved: dict[str, Any] = {}
    thr = get_min_confidence_for_category(category_hint)

    for tf in sorted(candidates.keys(), key=lambda x: (rank.get(x, 999), x)):
        rows = candidates.get(tf) or []
        slim = [(a, b, c) for a, b, c, _ in rows]
        metas = [r[3] for r in rows]

        chosen, w2, fcs, sups = resolve_typed_field_candidates(
            tf,
            slim,
            category_hint,
            candidate_meta=metas,
        )
        all_suppressed.extend(sups)
        for sp in sups:
            _log_norm(
                "TYPED_FIELD_SUPPRESSED",
                store=st or "",
                source_id=source_id,
                url=url,
                category_hint=category_hint,
                field_name=sp.field_name,
                reason_code=sp.reason_code,
                warning_codes=[sp.reason_code],
                normalized_value=None,
            )

        if WC.CONFLICTING_VALUES in w2:
            conflicting_fields.append(tf)
        for w in w2:
            if w not in warnings:
                warnings.append(w)
            if w == WC.CONFLICTING_VALUES:
                _log_norm(
                    "SPEC_CONFLICT",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    typed_field=tf,
                    reason_code=WC.CONFLICTING_VALUES,
                    warning_codes=[WC.CONFLICTING_VALUES],
                )
            elif w == WC.IMPLAUSIBLE_VALUE:
                _log_norm(
                    "SPEC_IMPLAUSIBLE",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    typed_field=tf,
                    reason_code=WC.IMPLAUSIBLE_VALUE,
                    warning_codes=[WC.IMPLAUSIBLE_VALUE],
                )
            elif w == WC.LOW_CONFIDENCE:
                _log_norm(
                    "TYPED_FIELD_SUPPRESSED",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    field_name=tf,
                    reason_code=WC.SUPPRESSED_BY_CONFIDENCE,
                    warning_codes=[WC.LOW_CONFIDENCE],
                )

        if chosen is not None and len(fcs) == 1:
            fc = fcs[0]
            if settings.ENABLE_TYPED_SPEC_CONFIDENCE:
                field_confidence[tf] = fc
                _log_norm(
                    "TYPED_FIELD_CONFIDENCE",
                    store=st or "",
                    source_id=source_id,
                    url=url,
                    category_hint=category_hint,
                    field_name=tf,
                    normalized_value=chosen,
                    confidence=fc.confidence,
                    threshold=thr,
                    warning_codes=fc.warning_codes,
                )
            resolved[tf] = chosen
    specs = TypedPartialSpecs.model_validate(resolved)
    uniq_warnings = list(dict.fromkeys(warnings))

    raw_total = len([k for k, v in raw_specs.items() if str(k).strip() and str(v).strip()])
    ratio = calculate_mapping_ratio(raw_specs, len(mapped_raw_keys))

    fc_compact: dict[str, Any] = {
        k: v.to_compact_dict() for k, v in field_confidence.items() if v is not None
    }
    if not settings.ENABLE_TYPED_SPEC_CONFIDENCE:
        fc_compact = {}

    sup_compact = [s.to_compact_dict() for s in all_suppressed]

    meta: dict[str, Any] = {
        "mapped_fields_count": len(mapped_raw_keys),
        "unmapped_fields_count": len(unmapped_labels),
        "unmapped_labels": unmapped_labels,
        "conflicting_fields": list(dict.fromkeys(conflicting_fields)),
        "deprecated_alias_hits": deprecated_hits,
        "field_confidence": fc_compact,
        "suppressed_typed_fields": sup_compact,
        "mapping_ratio": ratio,
        "normalization_quality": {},
    }

    if (
        settings.ENABLE_SPEC_COVERAGE_REPORT
        and ratio < settings.SPEC_MAPPING_MIN_COVERAGE_WARNING
        and raw_total >= 3
    ):
        _log_norm(
            "SPEC_MAPPING_COVERAGE_LOW",
            store=st or "",
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            mapping_ratio=ratio,
            reason_code=WC.LOW_MAPPING_COVERAGE,
            warning_codes=[WC.LOW_MAPPING_COVERAGE],
        )

    return specs, uniq_warnings, meta
