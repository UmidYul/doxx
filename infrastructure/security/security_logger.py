from __future__ import annotations

from config.settings import settings
from domain.observability import SyncCorrelationContext

from infrastructure.observability import message_codes as omc
from infrastructure.observability.event_logger import log_sync_event


def _corr() -> SyncCorrelationContext:
    return SyncCorrelationContext(run_id="security_baseline", spider_name="security", store_name="*")


def _should_log() -> bool:
    return bool(getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", False) or getattr(settings, "ENABLE_IN_MEMORY_TRACE_BUFFER", False))


def emit_security_startup_validated(
    *,
    security_mode: str,
    validation_passed: bool,
    warning_count: int,
    error_count: int,
    integrity_mode: str,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "info",
        omc.SECURITY_STARTUP_VALIDATED,
        _corr(),
        details={
            "security_mode": security_mode,
            "validation_passed": validation_passed,
            "warning_count": warning_count,
            "error_count": error_count,
            "integrity_mode": integrity_mode,
        },
    )


def emit_security_secret_loaded(
    *,
    secret_name: str,
    secret_source: str,
    configured: bool,
) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "info",
        omc.SECURITY_SECRET_LOADED,
        _corr(),
        details={
            "secret_name": secret_name,
            "secret_source": secret_source,
            "configured": configured,
        },
    )


def emit_security_request_signed(*, integrity_mode: str, signed: bool) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "info",
        omc.SECURITY_REQUEST_SIGNED,
        _corr(),
        details={"integrity_mode": integrity_mode, "signed": signed},
    )


def emit_security_redaction_applied(*, context: str) -> None:
    if not getattr(settings, "ENABLE_SECRET_REDACTION", True):
        return
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.SECURITY_REDACTION_APPLIED,
        _corr(),
        details={"context": context},
    )


def emit_security_config_warning(*, message: str) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.SECURITY_CONFIG_WARNING,
        _corr(),
        details={"message": message[:500]},
    )


def emit_security_config_invalid(*, errors: list[str]) -> None:
    if not _should_log():
        return
    log_sync_event(
        "internal",
        "error",
        omc.SECURITY_CONFIG_INVALID,
        _corr(),
        details={"error_count": len(errors), "errors": [e[:300] for e in errors]},
    )
