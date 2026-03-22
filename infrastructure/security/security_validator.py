from __future__ import annotations

from typing import cast

from config.settings import Settings
from domain.security import (
    RequestIntegrityMode,
    SecurityMode,
    SecurityValidationResult,
)

from infrastructure.security.secret_loader import is_secret_configured, normalize_header_name

_MIN_KEY_HARD_ERROR = 8
_MIN_KEY_WARN_BASELINE = 16
_MIN_KEY_STRICT_HARDENED = 24


def _parse_security_mode(raw: str) -> SecurityMode:
    v = (raw or "baseline").strip().lower()
    if v == "hardened":
        return "hardened"
    return "baseline"


def _parse_integrity_mode(raw: str) -> RequestIntegrityMode:
    v = (raw or "none").strip().lower()
    if v in ("hmac_optional", "optional"):
        return "hmac_optional"
    if v in ("hmac_required", "required"):
        return "hmac_required"
    return "none"


def _header_name_errors(settings: Settings, attr: str) -> list[str]:
    raw = getattr(settings, attr, "") or ""
    name = raw if isinstance(raw, str) else ""
    n = normalize_header_name(name)
    if not n:
        return [f"{attr} must be a non-empty header name"]
    if any(c in n for c in "\r\n\t"):
        return [f"{attr} contains illegal characters"]
    if len(n) > 128:
        return [f"{attr} is unreasonably long"]
    return []


def validate_parser_key(settings: Settings) -> list[str]:
    errors: list[str] = []
    pk = settings.CRM_PARSER_KEY
    env_set = is_secret_configured(pk if isinstance(pk, str) else None)
    fp_raw = getattr(settings, "CRM_PARSER_KEY_FILE", "") or ""
    fp = fp_raw.strip() if isinstance(fp_raw, str) else ""
    fallback = bool(getattr(settings, "ENABLE_SECRET_FILE_FALLBACK", True))

    if not env_set and (not fallback or not fp):
        errors.append("CRM_PARSER_KEY is required (set env CRM_PARSER_KEY or CRM_PARSER_KEY_FILE with file fallback enabled)")

    # Length check on inline env value when present (file content checked after load in transport)
    key_preview = (settings.CRM_PARSER_KEY if isinstance(settings.CRM_PARSER_KEY, str) else "") or ""
    key_preview = key_preview.strip()
    if key_preview and len(key_preview) < _MIN_KEY_HARD_ERROR:
        errors.append(f"CRM_PARSER_KEY is too short (minimum {_MIN_KEY_HARD_ERROR} characters)")

    return errors


def validate_parser_key_length_after_load(secret: str | None, mode: SecurityMode) -> tuple[list[str], list[str]]:
    """Run after load_secret for final materialized key."""
    errs: list[str] = []
    warns: list[str] = []
    if not secret:
        return (["parser key resolved empty"], [])
    ln = len(secret)
    if ln < _MIN_KEY_HARD_ERROR:
        errs.append(f"resolved parser key too short (< {_MIN_KEY_HARD_ERROR})")
    elif ln < _MIN_KEY_WARN_BASELINE:
        warns.append(f"parser key shorter than recommended ({_MIN_KEY_WARN_BASELINE}+ chars)")
    if mode == "hardened" and ln < _MIN_KEY_STRICT_HARDENED:
        errs.append(f"hardened SECURITY_MODE requires parser key length >= {_MIN_KEY_STRICT_HARDENED}")
    return (errs, warns)


def validate_integrity_settings(settings: Settings) -> list[str]:
    errors: list[str] = []
    mode = _parse_integrity_mode(getattr(settings, "CRM_REQUEST_INTEGRITY_MODE", "none"))

    errors.extend(_header_name_errors(settings, "CRM_REQUEST_TIMESTAMP_HEADER"))
    errors.extend(_header_name_errors(settings, "CRM_REQUEST_NONCE_HEADER"))
    errors.extend(_header_name_errors(settings, "CRM_REQUEST_SIGNATURE_HEADER"))

    algo_raw = getattr(settings, "CRM_REQUEST_SIGNATURE_ALGORITHM", "") or ""
    algo = (algo_raw if isinstance(algo_raw, str) else "").strip().lower()
    if mode != "none" and algo not in ("hmac-sha256", "hmac_sha256"):
        errors.append("CRM_REQUEST_SIGNATURE_ALGORITHM must be hmac-sha256 for this release")

    if mode == "hmac_required":
        ss = getattr(settings, "CRM_REQUEST_SIGNING_SECRET", "")
        env_s = is_secret_configured(ss if isinstance(ss, str) else None)
        sfp = getattr(settings, "CRM_REQUEST_SIGNING_SECRET_FILE", "")
        fp = (sfp if isinstance(sfp, str) else "").strip()
        fb = bool(getattr(settings, "ENABLE_SECRET_FILE_FALLBACK", True))
        if not env_s and (not fb or not fp):
            errors.append("CRM_REQUEST_INTEGRITY_MODE=hmac_required requires CRM_REQUEST_SIGNING_SECRET or secret file")

    return errors


def validate_security_settings(settings: Settings) -> SecurityValidationResult:
    mode = _parse_security_mode(getattr(settings, "SECURITY_MODE", "baseline"))
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = ["X-Parser-Key remains the primary CRM auth channel"]

    errors.extend(validate_parser_key(settings))
    errors.extend(validate_integrity_settings(settings))

    if getattr(settings, "TRANSPORT_TYPE", "").lower() == "crm_http":
        if not (getattr(settings, "CRM_BASE_URL", "") or "").strip():
            warnings.append("CRM_BASE_URL is empty — HTTP transport may fail at runtime")

    passed = len(errors) == 0
    return SecurityValidationResult(
        passed=passed,
        mode=cast(SecurityMode, mode),
        errors=errors,
        warnings=warnings,
        notes=notes,
    )
