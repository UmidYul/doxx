from __future__ import annotations

from config.settings import Settings
from domain.security import SecurityValidationResult

from infrastructure.security import security_logger as sec_log
from infrastructure.security.security_validator import (
    _parse_integrity_mode,
    _parse_security_mode,
    validate_security_settings,
)

_last_result: SecurityValidationResult | None = None


def reset_startup_security_checks_for_tests() -> None:
    global _last_result
    _last_result = None


def run_startup_security_checks(cfg: Settings, *, force: bool = False) -> SecurityValidationResult:
    """
    Run once per process unless ``force=True`` (tests).
    Respects ENABLE_SECURITY_STARTUP_VALIDATION; when disabled, returns a passed stub for crm_http.
    """
    global _last_result
    if _last_result is not None and not force:
        return _last_result

    s = cfg
    if not getattr(s, "ENABLE_SECURITY_STARTUP_VALIDATION", True):
        mode = _parse_security_mode(getattr(s, "SECURITY_MODE", "baseline"))
        _last_result = SecurityValidationResult(
            passed=True,
            mode=mode,
            errors=[],
            warnings=["ENABLE_SECURITY_STARTUP_VALIDATION=false — startup security checks skipped"],
            notes=[],
        )
        return _last_result

    result = validate_security_settings(s)
    integrity = _parse_integrity_mode(getattr(s, "CRM_REQUEST_INTEGRITY_MODE", "none"))

    if result.warnings:
        for w in result.warnings:
            sec_log.emit_security_config_warning(message=w)

    if not result.passed:
        sec_log.emit_security_config_invalid(errors=result.errors)
        sec_log.emit_security_startup_validated(
            security_mode=result.mode,
            validation_passed=False,
            warning_count=len(result.warnings),
            error_count=len(result.errors),
            integrity_mode=integrity,
        )
        if getattr(s, "SECURITY_FAIL_FAST_ON_INVALID_CONFIG", True):
            msg = "; ".join(result.errors)
            raise RuntimeError(f"SECURITY: invalid configuration ({msg})")
    else:
        sec_log.emit_security_startup_validated(
            security_mode=result.mode,
            validation_passed=True,
            warning_count=len(result.warnings),
            error_count=0,
            integrity_mode=integrity,
        )

    _last_result = result
    return result
