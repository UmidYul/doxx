from __future__ import annotations

from config.settings import settings
from domain.observability import SyncCorrelationContext

from infrastructure.observability import message_codes as omc
from infrastructure.observability.event_logger import log_sync_event


def _corr() -> SyncCorrelationContext:
    return SyncCorrelationContext(
        run_id="data_governance",
        spider_name="data_policy",
        store_name="*",
    )


def _should_emit() -> bool:
    return bool(getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", False))


def emit_data_minimization_applied(
    *,
    purpose: str,
    removed_fields_count: int = 0,
    kept_fields_count: int = 0,
    artifact_name: str = "payload",
) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.DATA_MINIMIZATION_APPLIED,
        _corr(),
        details={
            "artifact_name": artifact_name,
            "purpose": purpose,
            "removed_fields_count": removed_fields_count,
            "kept_fields_count": kept_fields_count,
        },
    )


def emit_retention_policy_applied(
    *,
    artifact_name: str,
    max_age_seconds: int | None,
    max_records: int | None,
    traces_removed: int = 0,
    batches_removed: int = 0,
) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.RETENTION_POLICY_APPLIED,
        _corr(),
        details={
            "artifact_name": artifact_name,
            "purpose": "observability",
            "max_age_seconds": max_age_seconds,
            "max_records": max_records,
            "removed_fields_count": traces_removed + batches_removed,
            "kept_fields_count": 0,
        },
    )


def emit_replay_abuse_guard_blocked(
    *,
    reason: str,
    replay_item_count: int,
    replay_batch_count: int,
    decision: str = "deny",
) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "warning",
        omc.REPLAY_ABUSE_GUARD_BLOCKED,
        _corr(),
        details={
            "reason": reason,
            "replay_item_count": replay_item_count,
            "replay_batch_count": replay_batch_count,
            "decision": decision,
        },
    )


def emit_support_scope_restricted(*, purpose: str, excluded_fields: list[str], reason: str | None = None) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.SUPPORT_SCOPE_RESTRICTED,
        _corr(),
        details={
            "purpose": purpose,
            "excluded_fields": excluded_fields[:40],
            "reason": reason,
        },
    )


def emit_diagnostic_export_minimized(*, artifact_name: str, kept_fields_count: int) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.DIAGNOSTIC_EXPORT_MINIMIZED,
        _corr(),
        details={"artifact_name": artifact_name, "kept_fields_count": kept_fields_count},
    )


def emit_trace_record_expired(*, max_age_seconds: int, removed: int) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.TRACE_RECORD_EXPIRED,
        _corr(),
        details={"max_age_seconds": max_age_seconds, "removed": removed},
    )


def emit_buffer_trimmed(*, artifact_name: str, max_records: int | None, removed: int) -> None:
    if not _should_emit():
        return
    log_sync_event(
        "internal",
        "debug",
        omc.BUFFER_TRIMMED,
        _corr(),
        details={"artifact_name": artifact_name, "max_records": max_records, "removed": removed},
    )
