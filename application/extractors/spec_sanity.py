from __future__ import annotations

import json
import logging
from typing import Any

from application.extractors import spec_warning_codes as WC
from domain.normalization_quality import SuppressedTypedField
from domain.typed_specs import TypedPartialSpecs

logger = logging.getLogger(__name__)


def _log_sanity(
    *,
    store: str = "",
    source_id: str | None = None,
    url: str = "",
    category_hint: str | None = None,
    field_name: str | None = None,
    raw_label: str | None = None,
    raw_value: str | None = None,
    normalized_value: Any = None,
    confidence: float | None = None,
    threshold: float | None = None,
    reason_code: str | None = None,
    warning_codes: list[str] | None = None,
) -> None:
    payload = {
        "event": "CROSS_FIELD_SANITY_WARNING",
        "store": store or None,
        "source_id": source_id,
        "url": url or None,
        "category_hint": category_hint,
        "field_name": field_name,
        "raw_label": raw_label,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "confidence": confidence,
        "threshold": threshold,
        "reason_code": reason_code,
        "warning_codes": warning_codes,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    logger.info("normalize_specs %s", json.dumps(payload, ensure_ascii=False, default=str))


def _cat_lower(category_hint: str | None) -> str:
    return (category_hint or "").strip().lower()


def _display_plausible_for_category(size: float, category_hint: str | None) -> bool:
    c = _cat_lower(category_hint)
    if c == "phone":
        return 3.0 <= size <= 8.5
    if c == "tablet":
        return 5.0 <= size <= 22.0
    if c == "laptop":
        return 9.0 <= size <= 21.0
    if c == "tv":
        return 12.0 <= size <= 120.0
    return 1.0 <= size <= 100.0


def apply_cross_field_sanity_checks(
    typed_specs: TypedPartialSpecs,
    category_hint: str | None = None,
    *,
    store: str = "",
    source_id: str | None = None,
    url: str = "",
) -> tuple[TypedPartialSpecs, list[str], list[SuppressedTypedField]]:
    warnings: list[str] = []
    suppressed: list[SuppressedTypedField] = []
    data = typed_specs.model_dump()
    c = _cat_lower(category_hint)

    def _drop(field: str, reason: str, details: str | None, raw_vals: list[str] | None = None) -> None:
        if data.get(field) is None:
            return
        val = data[field]
        data[field] = None
        suppressed.append(
            SuppressedTypedField(
                field_name=field,
                raw_values=list(raw_vals or []),
                reason_code=reason,
                details=details,
            )
        )
        _log_sanity(
            store=store,
            source_id=source_id,
            url=url,
            category_hint=category_hint,
            field_name=field,
            normalized_value=val,
            reason_code=reason,
            warning_codes=[reason],
        )

    # --- RAM vs storage (phone / tablet / laptop) ---
    ram = data.get("ram_gb")
    sto = data.get("storage_gb")
    if (
        ram is not None
        and sto is not None
        and c in {"phone", "tablet", "laptop"}
        and int(ram) > int(sto)
    ):
        warnings.append(WC.RAM_STORAGE_SWAP_SUSPECTED)
        _drop(
            "ram_gb",
            WC.RAM_STORAGE_SWAP_SUSPECTED,
            "ram_gb_gt_storage_gb",
        )

    # --- Display size vs category ---
    disp = data.get("display_size_inch")
    if disp is not None and not _display_plausible_for_category(float(disp), category_hint):
        warnings.append(WC.CATEGORY_MISMATCH)
        _drop(
            "display_size_inch",
            WC.CROSS_FIELD_CONFLICT,
            "display_size_implausible_for_category",
        )

    # --- Battery vs category ---
    mah = data.get("battery_mah")
    wh = data.get("battery_wh")
    if mah is not None:
        if c in {"laptop", "tv", "appliance"} and (int(mah) < 500 or int(mah) > 50000):
            warnings.append(WC.CATEGORY_MISMATCH)
            _drop("battery_mah", WC.CATEGORY_MISMATCH, "battery_mah_unusual_for_category")
        elif c == "laptop" and wh is None and int(mah) > 25000:
            warnings.append(WC.CATEGORY_MISMATCH)
            _drop("battery_mah", WC.CROSS_FIELD_CONFLICT, "battery_mah_too_large_for_laptop")
    if wh is not None and c in {"phone", "tablet"}:
        warnings.append(WC.CATEGORY_MISMATCH)
        _drop("battery_wh", WC.CATEGORY_MISMATCH, "battery_wh_unusual_for_mobile")

    # --- Weight consistency ---
    wg = data.get("weight_g")
    wkg = data.get("weight_kg")
    if wg is not None and wkg is not None:
        try:
            expected = int(float(wkg) * 1000)
            g = int(wg)
            if abs(g - expected) > max(100, int(0.2 * max(g, 1))):
                warnings.append(WC.INCONSISTENT_WEIGHT_UNITS)
                _drop("weight_g", WC.INCONSISTENT_WEIGHT_UNITS, "weight_g_kg_mismatch", [])
                _drop("weight_kg", WC.INCONSISTENT_WEIGHT_UNITS, "weight_g_kg_mismatch", [])
        except (TypeError, ValueError):
            pass

    # --- Cameras ---
    main = data.get("main_camera_mp")
    if main is not None and (int(main) < 1 or int(main) > 200):
        warnings.append(WC.IMPLAUSIBLE_VALUE)
        _drop("main_camera_mp", WC.IMPLAUSIBLE_VALUE, "main_camera_out_of_range")
    front = data.get("front_camera_mp")
    if front is not None and (int(front) < 1 or int(front) > 64):
        warnings.append(WC.IMPLAUSIBLE_VALUE)
        _drop("front_camera_mp", WC.IMPLAUSIBLE_VALUE, "front_camera_out_of_range")

    # --- Appliance ---
    if c == "appliance":
        vol = data.get("volume_l")
        if vol is not None and (float(vol) < 0.01 or float(vol) > 800):
            warnings.append(WC.IMPLAUSIBLE_VALUE)
            _drop("volume_l", WC.IMPLAUSIBLE_VALUE, "volume_l_out_of_range")
        pw = data.get("power_w")
        if pw is not None and (int(pw) < 1 or int(pw) > 30_000):
            warnings.append(WC.IMPLAUSIBLE_VALUE)
            _drop("power_w", WC.IMPLAUSIBLE_VALUE, "power_w_out_of_range")

    # --- smart_tv on wrong categories ---
    if data.get("smart_tv") is True and c in {"appliance", "phone"}:
        warnings.append(WC.CROSS_FIELD_CONFLICT)
        _drop("smart_tv", WC.CROSS_FIELD_CONFLICT, "smart_tv_unlikely_for_category")

    # --- HDMI state ---
    hdmi = data.get("hdmi")
    hcnt = data.get("hdmi_count")
    if hdmi is False and hcnt is not None and int(hcnt) > 0:
        warnings.append(WC.INCONSISTENT_HDMI_STATE)
        _drop("hdmi_count", WC.INCONSISTENT_HDMI_STATE, "hdmi_false_but_positive_count")

    out = TypedPartialSpecs.model_validate({k: v for k, v in data.items()})
    uniq_warn = list(dict.fromkeys(warnings))
    return out, uniq_warn, suppressed
