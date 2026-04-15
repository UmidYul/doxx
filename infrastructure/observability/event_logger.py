from __future__ import annotations

import json
import logging
import threading
from typing import cast

from domain.observability import BatchTraceRecord

from config.settings import settings
from domain.observability import (
    FailureDomain,
    FailureType,
    SyncCorrelationContext,
    SyncSeverity,
    SyncTraceRecord,
    SyncTraceStage,
)

from infrastructure.observability.metrics_collector import bump_counter_for_message_code
from infrastructure.observability.trace_collector import record_trace, trim_buffers_if_needed
from infrastructure.security.redaction import redact_mapping_for_logs

logger = logging.getLogger("moscraper.observability.sync")
publisher_logger = logging.getLogger("moscraper.publisher")
_TRIM_GUARD = threading.local()


def log_perf_event(
    message_code: str,
    *,
    stage: str | None = None,
    duration_ms: float | None = None,
    store_name: str | None = None,
    spider_name: str | None = None,
    entity_key: str | None = None,
    batch_id: str | None = None,
    products_per_minute: float | None = None,
    batches_per_minute: float | None = None,
    memory_mb: float | None = None,
    severity: str | None = None,
    threshold_ms: float | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured performance events (8A); does not participate in sync trace buffer."""
    if not getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
        return
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        details = dict(redact_mapping_for_logs(dict(details or {})))
    payload: dict[str, object] = {
        "observability": "parser_perf_v1",
        "message_code": message_code,
        "stage": stage,
        "duration_ms": duration_ms,
        "store_name": store_name,
        "spider_name": spider_name,
        "entity_key": entity_key,
        "batch_id": batch_id,
        "products_per_minute": products_per_minute,
        "batches_per_minute": batches_per_minute,
        "memory_mb": memory_mb,
        "severity": severity,
        "threshold_ms": threshold_ms,
        "details": dict(details or {}),
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    lvl = logging.INFO
    if severity in ("warning", "slow"):
        lvl = logging.WARNING
    elif severity in ("error", "high", "critical"):
        lvl = logging.ERROR
    logging.getLogger("moscraper.performance").log(lvl, "perf_event %s", line)


def log_resource_governance_event(
    message_code: str,
    *,
    store_name: str | None = None,
    purpose: str | None = None,
    mode: str | None = None,
    inflight_requests: int | None = None,
    inflight_batches: int | None = None,
    retryable_queue: int | None = None,
    browser_pages: int | None = None,
    proxy_requests: int | None = None,
    memory_mb: float | None = None,
    selected_limit: int | None = None,
    reason: str | None = None,
    suggested_action: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured resource governance events (8B); optional when governance enabled."""
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        details = dict(redact_mapping_for_logs(dict(details or {})))
    payload: dict[str, object] = {
        "observability": "parser_resource_gov_v1",
        "message_code": message_code,
        "store_name": store_name,
        "purpose": purpose,
        "mode": mode,
        "inflight_requests": inflight_requests,
        "inflight_batches": inflight_batches,
        "retryable_queue": retryable_queue,
        "browser_pages": browser_pages,
        "proxy_requests": proxy_requests,
        "memory_mb": memory_mb,
        "selected_limit": selected_limit,
        "reason": reason,
        "suggested_action": suggested_action,
        "details": dict(details or {}),
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.resource_governance").info("resource_gov_event %s", line)


def log_cost_efficiency_event(
    message_code: str,
    *,
    store_name: str | None = None,
    metric_name: str | None = None,
    estimated_cost_units: float | None = None,
    products_per_cost_unit: float | None = None,
    applied_per_cost_unit: float | None = None,
    signal_code: str | None = None,
    observed_value: float | None = None,
    threshold_value: float | None = None,
    baseline_value: float | None = None,
    current_value: float | None = None,
    regression_pct: float | None = None,
    recommended_action: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured cost / efficiency events (8C)."""
    if not getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True):
        return
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        details = dict(redact_mapping_for_logs(dict(details or {})))
    payload: dict[str, object] = {
        "observability": "parser_cost_efficiency_v1",
        "message_code": message_code,
        "store_name": store_name,
        "metric_name": metric_name,
        "estimated_cost_units": estimated_cost_units,
        "products_per_cost_unit": products_per_cost_unit,
        "applied_per_cost_unit": applied_per_cost_unit,
        "signal_code": signal_code,
        "observed_value": observed_value,
        "threshold_value": threshold_value,
        "baseline_value": baseline_value,
        "current_value": current_value,
        "regression_pct": regression_pct,
        "recommended_action": recommended_action,
        "details": dict(details or {}),
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.cost_efficiency").info("cost_efficiency_event %s", line)


def log_architecture_governance_event(
    message_code: str,
    *,
    source_module: str | None = None,
    target_module: str | None = None,
    violated_rule: str | None = None,
    severity: str | None = None,
    anti_pattern: str | None = None,
    recommended_layer: str | None = None,
    recommended_module: str | None = None,
    risk_level: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured architecture governance events (9A)."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        details = dict(redact_mapping_for_logs(dict(details or {})))
    payload: dict[str, object] = {
        "observability": "parser_architecture_gov_v1",
        "message_code": message_code,
        "source_module": source_module,
        "target_module": target_module,
        "violated_rule": violated_rule,
        "severity": severity,
        "anti_pattern": anti_pattern,
        "recommended_layer": recommended_layer,
        "recommended_module": recommended_module,
        "risk_level": risk_level,
        "details": dict(details or {}),
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.architecture").info("architecture_gov_event %s", line)


def log_developer_experience_event(
    message_code: str,
    *,
    dev_run_mode: str | None = None,
    store_name: str | None = None,
    fixture_name: str | None = None,
    dry_run: bool | None = None,
    sections_included: list[str] | None = None,
    items_count: int | None = None,
    pass_ok: bool | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured developer-experience events (9B); safe for logs, no CRM side effects."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_dx_v1",
        "message_code": message_code,
        "dev_run_mode": dev_run_mode,
        "store_name": store_name,
        "fixture_name": fixture_name,
        "dry_run": dry_run,
        "sections_included": list(sections_included or []),
        "items_count": items_count,
        "pass": pass_ok,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.dx").info("dx_event %s", line)
    bump_counter_for_message_code(message_code)


def log_publisher_event(
    message_code: str,
    *,
    publisher_service: str | None = None,
    exchange_name: str | None = None,
    queue_name: str | None = None,
    routing_key: str | None = None,
    event_id: str | None = None,
    store_name: str | None = None,
    scrape_run_id: str | None = None,
    claimed: int | None = None,
    published: int | None = None,
    failed: int | None = None,
    severity: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured publisher-service events for RabbitMQ delivery diagnostics."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_publisher_v1",
        "message_code": message_code,
        "publisher_service": publisher_service,
        "exchange_name": exchange_name,
        "queue_name": queue_name,
        "routing_key": routing_key,
        "event_id": event_id,
        "store_name": store_name,
        "scrape_run_id": scrape_run_id,
        "claimed": claimed,
        "published": published,
        "failed": failed,
        "severity": severity,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    level = logging.INFO
    if severity == "warning":
        level = logging.WARNING
    elif severity in ("error", "critical"):
        level = logging.ERROR
    publisher_logger.log(level, "publisher_event %s", line)
    bump_counter_for_message_code(message_code)


def log_knowledge_continuity_event(
    message_code: str,
    *,
    asset_name: str | None = None,
    path: str | None = None,
    ownership_area: str | None = None,
    store_name: str | None = None,
    missing_doc: str | None = None,
    coverage_pct: float | None = None,
    risk_level: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured documentation / ownership events (9C)."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_knowledge_v1",
        "message_code": message_code,
        "asset_name": asset_name,
        "path": path,
        "ownership_area": ownership_area,
        "store_name": store_name,
        "missing_doc": missing_doc,
        "coverage_pct": coverage_pct,
        "risk_level": risk_level,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.knowledge").info("knowledge_event %s", line)
    bump_counter_for_message_code(message_code)


def log_readiness_event(
    message_code: str,
    *,
    domain: str | None = None,
    item_code: str | None = None,
    evidence_type: str | None = None,
    artifact_name: str | None = None,
    gap_code: str | None = None,
    severity: str | None = None,
    blocking: bool | None = None,
    overall_status: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured production-readiness events (10A)."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_readiness_v1",
        "message_code": message_code,
        "domain": domain,
        "item_code": item_code,
        "evidence_type": evidence_type,
        "artifact_name": artifact_name,
        "gap_code": gap_code,
        "severity": severity,
        "blocking": blocking,
        "overall_status": overall_status,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.readiness").info("readiness_event %s", line)
    bump_counter_for_message_code(message_code)


def log_roadmap_event(
    message_code: str,
    *,
    item_code: str | None = None,
    phase: str | None = None,
    priority: str | None = None,
    workstream: str | None = None,
    blocking_for_go_live: bool | None = None,
    dependency_from: str | None = None,
    dependency_to: str | None = None,
    reason: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured implementation-roadmap events (10B)."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_roadmap_v1",
        "message_code": message_code,
        "item_code": item_code,
        "phase": phase,
        "priority": priority,
        "workstream": workstream,
        "blocking_for_go_live": blocking_for_go_live,
        "dependency_from": dependency_from,
        "dependency_to": dependency_to,
        "reason": reason,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.roadmap").info("roadmap_event %s", line)
    bump_counter_for_message_code(message_code)


def log_go_live_event(
    message_code: str,
    *,
    decision: str | None = None,
    launch_stage: str | None = None,
    blocker_code: str | None = None,
    criterion_code: str | None = None,
    item_code: str | None = None,
    trigger_code: str | None = None,
    severity: str | None = None,
    passed: bool | None = None,
    recommended_action: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Structured go-live / cutover / stabilization events (10C)."""
    if not getattr(settings, "ENABLE_STRUCTURED_SYNC_LOGS", True):
        return
    det = dict(details or {})
    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        det = dict(redact_mapping_for_logs(det))
    payload: dict[str, object] = {
        "observability": "parser_go_live_v1",
        "message_code": message_code,
        "decision": decision,
        "launch_stage": launch_stage,
        "blocker_code": blocker_code,
        "criterion_code": criterion_code,
        "item_code": item_code,
        "trigger_code": trigger_code,
        "severity": severity,
        "passed": passed,
        "recommended_action": recommended_action,
        "details": det,
    }
    line = json.dumps(payload, default=str, ensure_ascii=False)
    logging.getLogger("moscraper.go_live").info("go_live_event %s", line)
    bump_counter_for_message_code(message_code)


def log_sync_event(
    stage: str,
    severity: str,
    message_code: str,
    correlation: SyncCorrelationContext,
    metrics: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
    failure_domain: str | None = None,
    failure_type: str | None = None,
) -> None:
    """Unified structured log + optional in-memory trace record."""
    if not settings.ENABLE_STRUCTURED_SYNC_LOGS and not settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
        return

    st = cast(SyncTraceStage, stage)
    sev = cast(SyncSeverity, severity)
    fd = cast(FailureDomain | None, failure_domain) if failure_domain else None
    ft = cast(FailureType | None, failure_type) if failure_type else None

    if getattr(settings, "ENABLE_SECRET_REDACTION", True):
        metrics = dict(redact_mapping_for_logs(dict(metrics or {})))
        details = dict(redact_mapping_for_logs(dict(details or {})))

    if getattr(settings, "ENABLE_DATA_MINIMIZATION", True):
        from infrastructure.security.minimizer import minimize_payload_for_logging

        metrics = minimize_payload_for_logging(dict(metrics or {}))
        details = minimize_payload_for_logging(dict(details or {}))

    def _emit() -> None:
        payload: dict[str, object] = {
            "observability": "parser_sync_v1",
            "stage": stage,
            "severity": severity,
            "message_code": message_code,
            "correlation": correlation.model_dump(mode="json"),
            "metrics": dict(metrics or {}),
            "details": dict(details or {}),
        }
        if failure_domain is not None:
            payload["failure_domain"] = failure_domain
        if failure_type is not None:
            payload["failure_type"] = failure_type

        if settings.ENABLE_STRUCTURED_SYNC_LOGS:
            line = json.dumps(payload, default=str, ensure_ascii=False)
            lvl = logging.INFO
            if severity == "debug":
                lvl = logging.DEBUG
            elif severity == "warning":
                lvl = logging.WARNING
            elif severity == "error":
                lvl = logging.ERROR
            elif severity == "critical":
                lvl = logging.CRITICAL
            logger.log(lvl, "sync_event %s", line)

        if settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
            rec = SyncTraceRecord(
                stage=st,
                severity=sev,
                message_code=message_code,
                correlation=correlation,
                metrics=dict(metrics or {}),
                details=dict(details or {}),
                failure_domain=fd,
                failure_type=ft,
            )
            record_trace(rec)

        bump_counter_for_message_code(message_code)
        if not bool(getattr(_TRIM_GUARD, "active", False)):
            _TRIM_GUARD.active = True
            try:
                trim_buffers_if_needed()
            finally:
                _TRIM_GUARD.active = False

    if (
        getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True)
        and getattr(settings, "ENABLE_STAGE_TIMING", True)
    ):
        from infrastructure.performance.timing_profiler import timed_stage

        with timed_stage(
            "observability",
            store_name=correlation.store_name,
            spider_name=correlation.spider_name,
        ):
            _emit()
    else:
        _emit()


def log_batch_trace(record: BatchTraceRecord) -> None:
    from infrastructure.observability.trace_collector import record_batch_trace

    if settings.ENABLE_BATCH_TRACE and settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
        record_batch_trace(record)
