from __future__ import annotations

from typing import Any

from application.extractors import spec_warning_codes as WC
from application.extractors.spec_confidence import (
    merge_field_confidences,
    score_typed_field_confidence,
    should_suppress_field,
)
from application.extractors.spec_conflicts import _equivalent, is_plausible_typed_value
from config.settings import settings
from domain.normalization_quality import FieldConfidence, SuppressedTypedField


def _compatible_values(field_name: str, a: Any, b: Any) -> bool:
    if _equivalent(a, b):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        fa, fb = float(a), float(b)
        if fa == 0 and fb == 0:
            return True
        denom = max(abs(fa), abs(fb), 1e-9)
        return abs(fa - fb) / denom <= 0.05
    return False


def _all_pairwise_compatible(field_name: str, values: list[Any]) -> bool:
    if len(values) < 2:
        return True
    first = values[0]
    return all(_compatible_values(field_name, first, v) for v in values[1:])


def _pick_best_candidate(
    field_name: str,
    parsed: list[tuple[str, str, Any, dict[str, Any]]],
    category_hint: str | None,
) -> tuple[Any, FieldConfidence, list[str]]:
    """Pick highest-confidence candidate among compatible values."""
    scored: list[tuple[float, int, Any, FieldConfidence]] = []
    warn: list[str] = []
    for i, (rl, rv, nv, meta) in enumerate(parsed):
        fc = score_typed_field_confidence(
            field_name,
            nv,
            rl,
            rv,
            category_hint,
            warning_codes=meta.get("extra_warnings"),
            direct_key=bool(meta.get("direct_key")),
            rule_priority=meta.get("rule_priority"),
            deprecated_alias=bool(meta.get("deprecated_alias")),
            ambiguous_alias=bool(meta.get("ambiguous_alias")),
            missing_unit=meta.get("missing_unit"),
            store_override_exact_match=bool(meta.get("store_override_exact_match")),
            corrected_value=bool(meta.get("corrected_value")),
            implausible_hint=bool(meta.get("implausible_hint")),
        )
        scored.append((fc.confidence, i, nv, fc))
    scored.sort(key=lambda x: (-x[0], x[1]))
    best_nv = scored[0][2]
    # Merge all compatible-with-best for confidence boost
    compatible_fcs = [
        t[3]
        for t in scored
        if _compatible_values(field_name, t[2], best_nv) and is_plausible_typed_value(field_name, t[2])
    ]
    merged = merge_field_confidences(field_name, compatible_fcs, category_hint)
    if len(parsed) > 1:
        warn.append(WC.CONFLICTING_VALUES)
        merged = merged.model_copy(
            update={
                "resolution_reason": merged.resolution_reason or "picked_best_compatible_candidate",
                "warning_codes": list(
                    dict.fromkeys([*merged.warning_codes, WC.CONFLICTING_VALUES]),
                ),
            }
        )
    return best_nv, merged, warn


def resolve_typed_field_candidates(
    field_name: str,
    candidates: list[tuple[str, str, Any]],
    category_hint: str | None = None,
    *,
    candidate_meta: list[dict[str, Any]] | None = None,
) -> tuple[Any | None, list[str], list[FieldConfidence], list[SuppressedTypedField]]:
    """
    ``candidate`` is ``(raw_label, raw_value, normalized_value)``.
    Optional ``candidate_meta`` aligns 1:1 with ``candidates`` for scoring hints.
    """
    warnings: list[str] = []
    all_fc: list[FieldConfidence] = []
    suppressed: list[SuppressedTypedField] = []

    metas = candidate_meta or [{} for _ in candidates]
    if len(metas) != len(candidates):
        metas = [{} for _ in candidates]

    parsed: list[tuple[str, str, Any, dict[str, Any]]] = []
    for (rk, rv, nv), meta in zip(candidates, metas, strict=False):
        if nv is not None:
            parsed.append((rk, rv, nv, dict(meta)))

    if not parsed:
        return None, warnings, all_fc, suppressed

    values = [nv for _, _, nv, _ in parsed]

    if len(values) == 1:
        rl, rv, nv, meta = parsed[0]
        if not is_plausible_typed_value(field_name, nv):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv],
                    reason_code=WC.SUPPRESSED_BY_PLAUSIBILITY,
                    details="single_candidate_implausible",
                )
            )
            warnings.append(WC.IMPLAUSIBLE_VALUE)
            fc = score_typed_field_confidence(
                field_name,
                nv,
                rl,
                rv,
                category_hint,
                implausible_hint=True,
                direct_key=bool(meta.get("direct_key")),
                rule_priority=meta.get("rule_priority"),
                deprecated_alias=bool(meta.get("deprecated_alias")),
                ambiguous_alias=bool(meta.get("ambiguous_alias")),
                missing_unit=meta.get("missing_unit"),
            )
            all_fc.append(fc)
            return None, warnings, all_fc, suppressed

        fc = score_typed_field_confidence(
            field_name,
            nv,
            rl,
            rv,
            category_hint,
            warning_codes=meta.get("extra_warnings"),
            direct_key=bool(meta.get("direct_key")),
            rule_priority=meta.get("rule_priority"),
            deprecated_alias=bool(meta.get("deprecated_alias")),
            ambiguous_alias=bool(meta.get("ambiguous_alias")),
            missing_unit=meta.get("missing_unit"),
            store_override_exact_match=bool(meta.get("store_override_exact_match")),
            corrected_value=bool(meta.get("corrected_value")),
        )
        all_fc.append(fc)
        if settings.ENABLE_TYPED_SPEC_CONFIDENCE and should_suppress_field(fc, category_hint):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv],
                    reason_code=WC.SUPPRESSED_BY_CONFIDENCE,
                    details=None,
                )
            )
            warnings.append(WC.LOW_CONFIDENCE)
            return None, warnings, all_fc, suppressed
        return nv, warnings, all_fc, suppressed

    first = values[0]
    all_equiv = all(_equivalent(first, v) for v in values[1:])
    if all_equiv:
        fcs: list[FieldConfidence] = []
        for rl, rv, nv, meta in parsed:
            fcs.append(
                score_typed_field_confidence(
                    field_name,
                    nv,
                    rl,
                    rv,
                    category_hint,
                    warning_codes=meta.get("extra_warnings"),
                    direct_key=bool(meta.get("direct_key")),
                    rule_priority=meta.get("rule_priority"),
                    deprecated_alias=bool(meta.get("deprecated_alias")),
                    ambiguous_alias=bool(meta.get("ambiguous_alias")),
                    missing_unit=meta.get("missing_unit"),
                    store_override_exact_match=bool(meta.get("store_override_exact_match")),
                    corrected_value=bool(meta.get("corrected_value")),
                )
            )
        merged = merge_field_confidences(field_name, fcs, category_hint)
        all_fc.append(merged)
        if not is_plausible_typed_value(field_name, first):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv for _, rv, _, _ in parsed],
                    reason_code=WC.SUPPRESSED_BY_PLAUSIBILITY,
                    details="merged_equivalent_implausible",
                )
            )
            warnings.append(WC.IMPLAUSIBLE_VALUE)
            return None, warnings, all_fc, suppressed
        if settings.ENABLE_TYPED_SPEC_CONFIDENCE and should_suppress_field(merged, category_hint):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv for _, rv, _, _ in parsed],
                    reason_code=WC.SUPPRESSED_BY_CONFIDENCE,
                    details=None,
                )
            )
            warnings.append(WC.LOW_CONFIDENCE)
            return None, warnings, all_fc, suppressed
        return first, warnings, all_fc, suppressed

    plausible_rows = [p for p in parsed if is_plausible_typed_value(field_name, p[2])]
    if not plausible_rows:
        suppressed.append(
            SuppressedTypedField(
                field_name=field_name,
                raw_values=[rv for _, rv, _, _ in parsed],
                reason_code=WC.SUPPRESSED_BY_PLAUSIBILITY,
                details="all_candidates_implausible",
            )
        )
        warnings.append(WC.IMPLAUSIBLE_VALUE)
        for rl, rv, nv, meta in parsed:
            all_fc.append(
                score_typed_field_confidence(
                    field_name,
                    nv,
                    rl,
                    rv,
                    category_hint,
                    implausible_hint=True,
                    direct_key=bool(meta.get("direct_key")),
                    rule_priority=meta.get("rule_priority"),
                    deprecated_alias=bool(meta.get("deprecated_alias")),
                    ambiguous_alias=bool(meta.get("ambiguous_alias")),
                    missing_unit=meta.get("missing_unit"),
                )
            )
        return None, warnings, all_fc, suppressed

    # Not all equivalent — try compatible cluster
    if _all_pairwise_compatible(field_name, values):
        nv, merged, w_extra = _pick_best_candidate(field_name, parsed, category_hint)
        warnings.extend(w_extra)
        all_fc.append(merged)
        if not is_plausible_typed_value(field_name, nv):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv for _, rv, _, _ in parsed],
                    reason_code=WC.SUPPRESSED_BY_PLAUSIBILITY,
                    details="compatible_cluster_implausible",
                )
            )
            warnings.append(WC.IMPLAUSIBLE_VALUE)
            return None, warnings, all_fc, suppressed
        if settings.ENABLE_TYPED_SPEC_CONFIDENCE and should_suppress_field(merged, category_hint):
            suppressed.append(
                SuppressedTypedField(
                    field_name=field_name,
                    raw_values=[rv for _, rv, _, _ in parsed],
                    reason_code=WC.SUPPRESSED_BY_CONFIDENCE,
                    details=None,
                )
            )
            warnings.append(WC.LOW_CONFIDENCE)
            return None, warnings, all_fc, suppressed
        return nv, warnings, all_fc, suppressed

    # Hard conflict — suppress typed field
    raw_vals = [rv for _, rv, _, _ in parsed]
    suppressed.append(
        SuppressedTypedField(
            field_name=field_name,
            raw_values=raw_vals,
            reason_code=WC.SUPPRESSED_BY_CONFLICT,
            details="incompatible_normalized_values",
        )
    )
    warnings.append(WC.CONFLICTING_VALUES)
    for rl, rv, nv, meta in parsed:
        all_fc.append(
            score_typed_field_confidence(
                field_name,
                nv,
                rl,
                rv,
                category_hint,
                warning_codes=[*(meta.get("extra_warnings") or []), WC.CONFLICTING_VALUES],
                direct_key=bool(meta.get("direct_key")),
                rule_priority=meta.get("rule_priority"),
                deprecated_alias=bool(meta.get("deprecated_alias")),
                ambiguous_alias=bool(meta.get("ambiguous_alias")),
                missing_unit=meta.get("missing_unit"),
            )
        )
    return None, warnings, all_fc, suppressed
