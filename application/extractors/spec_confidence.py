from __future__ import annotations

import re
from typing import Any

from config.settings import settings

from application.extractors import spec_warning_codes as WC
from domain.normalization_quality import FieldConfidence

_UNIT_HINT_RE = re.compile(
    r"(?:gb|гб|tb|тб|mb|мб|mhz|мгц|ghz|ггц|inch|дюйм|\"|″|mah|мач|mAh|"
    r"wh|вт\s*ч|кг|kg|g\b|г\b|mm|мм|cm|см|w\b|вт|l\b|л\b|mp|мп)",
    re.IGNORECASE,
)


def get_min_confidence_for_category(category_hint: str | None) -> float:
    if not category_hint:
        return settings.TYPED_SPEC_MIN_CONFIDENCE_DEFAULT
    c = str(category_hint).strip().lower()
    if c == "phone":
        return settings.TYPED_SPEC_MIN_CONFIDENCE_PHONE
    if c == "laptop":
        return settings.TYPED_SPEC_MIN_CONFIDENCE_LAPTOP
    if c == "tv":
        return settings.TYPED_SPEC_MIN_CONFIDENCE_TV
    if c == "tablet":
        return settings.TYPED_SPEC_MIN_CONFIDENCE_TABLET
    if c == "appliance":
        return settings.TYPED_SPEC_MIN_CONFIDENCE_APPLIANCE
    return settings.TYPED_SPEC_MIN_CONFIDENCE_DEFAULT


def _numericish_field(field_name: str) -> bool:
    return field_name in {
        "ram_gb",
        "storage_gb",
        "display_size_inch",
        "battery_mah",
        "battery_wh",
        "weight_g",
        "weight_kg",
        "main_camera_mp",
        "front_camera_mp",
        "volume_l",
        "power_w",
        "hdmi_count",
        "usb_c_count",
        "refresh_rate_hz",
        "sim_count",
        "warranty_months",
    }


def detect_missing_unit(field_name: str, raw_value: str) -> bool:
    if not _numericish_field(field_name):
        return False
    s = (raw_value or "").strip()
    if not s:
        return True
    if _UNIT_HINT_RE.search(s):
        return False
    # Bare digits / digit+comma — likely missing unit for RAM/storage/etc.
    if re.fullmatch(r"\d+(?:[.,]\d+)?", s):
        return True
    return False


def score_typed_field_confidence(
    field_name: str,
    normalized_value: object,
    raw_label: str,
    raw_value: str,
    category_hint: str | None,
    warning_codes: list[str] | None = None,
    *,
    direct_key: bool = False,
    rule_priority: int | None = None,
    deprecated_alias: bool = False,
    ambiguous_alias: bool = False,
    missing_unit: bool | None = None,
    store_override_exact_match: bool = False,
    implausible_hint: bool = False,
    corrected_value: bool = False,
) -> FieldConfidence:
    """Heuristic confidence in [0.35, 0.98] for one evidence row."""
    wc = list(warning_codes or [])
    mu = detect_missing_unit(field_name, raw_value) if missing_unit is None else missing_unit
    if mu and WC.MISSING_UNIT not in wc:
        wc.append(WC.MISSING_UNIT)

    base = 0.58
    if direct_key:
        base += 0.26
    else:
        base += 0.17  # registry alias / rule match — still CRM-useful signal

    if rule_priority is not None:
        if rule_priority >= 70:
            base += 0.12  # store-scoped / high-priority rules
        elif rule_priority >= 10:
            base += 0.06  # category-scoped-ish

    if deprecated_alias:
        base -= 0.06  # warn CRM via code, but keep usually above phone threshold
        if WC.DEPRECATED_ALIAS not in wc:
            wc.append(WC.DEPRECATED_ALIAS)

    if ambiguous_alias:
        base -= 0.10
        if WC.AMBIGUOUS_ALIAS not in wc:
            wc.append(WC.AMBIGUOUS_ALIAS)

    if mu:
        base -= 0.08
    elif _numericish_field(field_name) and len((raw_value or "").strip()) > 2:
        # e.g. "8 GB", "5000 mAh" — grounded extraction, not a bare digit
        base += 0.04

    if store_override_exact_match:
        base += 0.06

    if corrected_value:
        base -= 0.18
        if WC.CORRECTED_VALUE not in wc:
            wc.append(WC.CORRECTED_VALUE)

    if implausible_hint:
        base -= 0.35
        if WC.IMPLAUSIBLE_VALUE not in wc:
            wc.append(WC.IMPLAUSIBLE_VALUE)

    for code in wc:
        if code == WC.CATEGORY_MISMATCH:
            base -= 0.08
        elif code == WC.RAM_STORAGE_SWAP_SUSPECTED:
            base -= 0.05  # intentional mapper reroute; keep usable for CRM

    conf = max(0.35, min(0.98, base))
    return FieldConfidence(
        field_name=field_name,
        confidence=round(conf, 4),
        source_labels=[raw_label],
        source_values=[raw_value],
        resolution_reason=None,
        warning_codes=list(dict.fromkeys(wc)),
    )


def merge_field_confidences(
    field_name: str,
    evidences: list[FieldConfidence],
    category_hint: str | None = None,
) -> FieldConfidence:
    """Merge multiple evidences that support the same normalized value."""
    if not evidences:
        return FieldConfidence(
            field_name=field_name,
            confidence=0.35,
            source_labels=[],
            source_values=[],
            resolution_reason="no_evidence",
            warning_codes=[WC.LOW_CONFIDENCE],
        )
    if len(evidences) == 1:
        e = evidences[0]
        return e.model_copy(update={"field_name": field_name})

    labels: list[str] = []
    values: list[str] = []
    all_wc: list[str] = []
    max_c = max(e.confidence for e in evidences)
    for e in evidences:
        labels.extend(e.source_labels)
        all_wc.extend(e.warning_codes)
        values.extend(e.source_values)
    bump = min(0.12, 0.04 * (len(evidences) - 1))
    merged_conf = min(0.98, max_c + bump)
    uniq_wc = list(dict.fromkeys(all_wc))
    _ = category_hint  # reserved for future category-specific merge
    return FieldConfidence(
        field_name=field_name,
        confidence=round(merged_conf, 4),
        source_labels=list(dict.fromkeys(labels)),
        source_values=list(dict.fromkeys(values)),
        resolution_reason="merged_equivalent_sources",
        warning_codes=uniq_wc,
    )


def should_suppress_field(field_confidence: FieldConfidence, category_hint: str | None = None) -> bool:
    if not settings.ENABLE_TYPED_SPEC_SUPPRESSION:
        return False
    if not settings.ENABLE_TYPED_SPEC_CONFIDENCE:
        return False
    thr = get_min_confidence_for_category(category_hint)
    return field_confidence.confidence < thr
