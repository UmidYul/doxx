from __future__ import annotations

from config.settings import settings
from domain.observability import SyncCorrelationContext

from infrastructure.observability.event_logger import log_sync_event


def emit_operational_event(
    message_code: str,
    *,
    run_id: str,
    store_name: str | None = None,
    status: str | None = None,
    metric_name: str | None = None,
    observed_value: float | None = None,
    threshold_value: float | None = None,
    severity: str | None = None,
    domain: str | None = None,
    recommended_action: str | None = None,
    alert_code: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    if not getattr(settings, "ENABLE_OPERATIONAL_POLICY_LOGS", True):
        return
    if not (settings.ENABLE_STRUCTURED_SYNC_LOGS or settings.ENABLE_IN_MEMORY_TRACE_BUFFER):
        return
    corr = SyncCorrelationContext(
        run_id=run_id,
        spider_name="operational_policy",
        store_name=(store_name or "*").strip() or "*",
    )
    payload = dict(details or {})
    if status is not None:
        payload["status"] = status
    if metric_name is not None:
        payload["metric_name"] = metric_name
    if observed_value is not None:
        payload["observed_value"] = observed_value
    if threshold_value is not None:
        payload["threshold_value"] = threshold_value
    if severity is not None:
        payload["severity"] = severity
    if domain is not None:
        payload["domain"] = domain
    if recommended_action is not None:
        payload["recommended_action"] = recommended_action
    if alert_code is not None:
        payload["alert_code"] = alert_code
    log_level = "info"
    if severity in ("high", "critical"):
        log_level = "warning"
    if severity == "critical":
        log_level = "error"
    log_sync_event(
        "internal",
        log_level,
        message_code,
        corr,
        details=payload,
    )
