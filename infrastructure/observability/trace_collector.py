from __future__ import annotations

import threading
import time
from collections import deque
from datetime import UTC, datetime
from config.settings import settings
from domain.observability import BatchTraceRecord, ParserHealthSnapshot, SyncTraceRecord
from domain.operational_policy import RunOperationalStatus, ThresholdDecision

from infrastructure.observability.dashboard_status import (
    aggregate_errors_by_domain,
    build_run_operational_status,
    summarize_status_for_dashboard,
)
from infrastructure.observability.health_policy import compute_parser_health, merge_health_with_operational
from infrastructure.observability.metrics_collector import get_observability_metrics
from infrastructure.observability import message_codes as omc
from infrastructure.observability.incident_classifier import classify_run_incident
from infrastructure.observability.status_snapshot import serialize_run_status
from infrastructure.observability.store_control import (
    explain_run_action,
    explain_store_action,
    suggest_run_action,
    suggest_store_action,
)
from infrastructure.observability.threshold_evaluator import evaluate_run_thresholds
from infrastructure.observability.diagnostic_snapshot import (
    build_run_diagnostic_snapshot,
    build_store_diagnostic_snapshot,
)
from infrastructure.observability.operator_messages import (
    build_human_runbook_message,
    build_human_status_message,
    build_human_triage_message,
)
from infrastructure.observability.replay_support import decide_safe_replay_action
from infrastructure.observability.runbook_registry import get_runbook_for_domain
from infrastructure.observability.support_serializer import (
    serialize_diagnostic_snapshot,
    serialize_runbook,
    serialize_triage_summary,
)
from infrastructure.observability.triage_engine import (
    build_triage_summary_for_run,
    build_triage_summary_for_store,
)


class TraceCollector:
    """In-memory bounded trace buffers for diagnostics and ETL-oriented export."""

    __slots__ = (
        "_lock",
        "_traces",
        "_batch_traces",
        "_trace_maxlen",
        "_batch_maxlen",
        "_run_id",
        "_started_at",
        "_stores",
        "_last_health_status",
        "_last_snapshot_at",
        "_cached_snapshot",
        "_last_operational_status",
    )

    def __init__(self, *, max_records: int) -> None:
        self._lock = threading.RLock()
        self._trace_maxlen = max(1, int(max_records))
        self._batch_maxlen = max(1, min(500, int(max_records)))
        self._traces: deque[SyncTraceRecord] = deque(maxlen=self._trace_maxlen)
        self._batch_traces: deque[BatchTraceRecord] = deque(maxlen=self._batch_maxlen)
        self._run_id: str = "unknown"
        self._started_at: datetime = datetime.now(UTC)
        self._stores: list[str] = []
        self._last_health_status: str = "healthy"
        self._last_snapshot_at: float = 0.0
        self._cached_snapshot: ParserHealthSnapshot | None = None
        self._last_operational_status: str = "healthy"

    @property
    def current_run_id(self) -> str:
        with self._lock:
            return self._run_id

    def list_stores(self) -> list[str]:
        with self._lock:
            return list(self._stores)

    def set_run_context(self, *, run_id: str, stores: list[str] | None = None) -> None:
        with self._lock:
            self._run_id = run_id
            self._started_at = datetime.now(UTC)
            if stores is not None:
                self._stores = list(stores)
            self._cached_snapshot = None

    def record_trace(self, record: SyncTraceRecord) -> None:
        with self._lock:
            self._traces.append(record)

    def record_batch_trace(self, record: BatchTraceRecord) -> None:
        with self._lock:
            self._batch_traces.append(record)

    def get_recent_traces(self, limit: int = 100) -> list[SyncTraceRecord]:
        self.trim_buffers_if_needed()
        with self._lock:
            if limit <= 0:
                return []
            return list(self._traces)[-limit:]

    def get_recent_batch_traces(self, limit: int = 50) -> list[BatchTraceRecord]:
        self.trim_buffers_if_needed()
        with self._lock:
            if limit <= 0:
                return []
            return list(self._batch_traces)[-limit:]

    def trim_buffers_if_needed(self) -> None:
        """Age + count retention (7C); deques stay maxlen-bounded."""
        if not getattr(settings, "ENABLE_RUNTIME_RETENTION_LIMITS", True):
            return
        from infrastructure.security import data_governance_logger as dg_log
        from infrastructure.security.retention_guard import apply_retention_policies

        with self._lock:
            traces = list(self._traces)
            batches = list(self._batch_traces)
        res = apply_retention_policies(traces=traces, batch_traces=batches, settings=settings)
        new_t = res["traces"]
        new_b = res["batch_traces"]
        tr = int(res.get("traces_removed") or 0)
        br = int(res.get("batches_removed") or 0)
        if tr > 0 or br > 0:
            if tr > 0:
                dg_log.emit_trace_record_expired(
                    max_age_seconds=int(getattr(settings, "TRACE_MAX_AGE_SECONDS", 3600) or 0),
                    removed=tr,
                )
            if br > 0:
                dg_log.emit_buffer_trimmed(
                    artifact_name="batch_trace_buffer",
                    max_records=self._batch_maxlen,
                    removed=br,
                )
            dg_log.emit_retention_policy_applied(
                artifact_name="trace_and_batch_buffers",
                max_age_seconds=int(getattr(settings, "TRACE_MAX_AGE_SECONDS", 3600) or 0),
                max_records=self._trace_maxlen,
                traces_removed=tr,
                batches_removed=br,
            )
            with self._lock:
                self._traces = deque(new_t, maxlen=self._trace_maxlen)
                self._batch_traces = deque(new_b, maxlen=self._batch_maxlen)

    def build_health_snapshot(self, *, extra_counters: dict[str, int | float] | None = None) -> ParserHealthSnapshot:
        now = time.monotonic()
        interval = float(getattr(settings, "HEALTH_SNAPSHOT_INTERVAL_SECONDS", 60) or 60)
        with self._lock:
            if (
                self._cached_snapshot is not None
                and settings.ENABLE_HEALTH_SNAPSHOT
                and (now - self._last_snapshot_at) < interval
            ):
                return self._cached_snapshot

        obs = get_observability_metrics().snapshot()
        merged: dict[str, int | float] = {k: float(v) for k, v in obs.items()}
        if extra_counters:
            for k, v in extra_counters.items():
                merged[k] = float(v) if isinstance(v, (int, float)) else v  # type: ignore[assignment]

        recent = self.get_recent_traces(200)
        failures = [r for r in recent if r.severity in ("error", "critical", "warning")]
        heuristic_status = compute_parser_health(merged, failures)

        last_errors: list[dict[str, object]] = []
        err_for_agg: list[dict[str, object]] = []
        for r in recent[-30:]:
            if r.severity in ("error", "critical"):
                row = {
                    "timestamp": r.timestamp.isoformat(),
                    "stage": r.stage,
                    "message_code": r.message_code,
                    "failure_domain": r.failure_domain,
                    "failure_type": r.failure_type,
                    "entity_key": r.correlation.entity_key,
                    "event_id": r.correlation.event_id,
                }
                last_errors.append(row)
        for r in recent[-100:]:
            if r.severity in ("error", "critical", "warning"):
                err_for_agg.append(
                    {
                        "failure_domain": r.failure_domain or "unknown",
                        "severity": r.severity,
                    }
                )

        stores_list = list(self._stores) or ["default"]
        store_counters = {s: dict(merged) for s in stores_list}
        run_op = build_run_operational_status(self._run_id, store_counters)
        status = merge_health_with_operational(heuristic_status, run_op.status)

        threshold_decisions = evaluate_run_thresholds(merged)
        op_alerts = [a.model_dump(mode="json") for ss in run_op.store_statuses for a in ss.alerts]
        op_alerts.extend(a.model_dump(mode="json") for a in run_op.global_alerts)

        dash = summarize_status_for_dashboard(run_op)
        dash["recommended_run_action"] = suggest_run_action(run_op)
        dash["recommended_per_store"] = {ss.store_name: suggest_store_action(ss) for ss in run_op.store_statuses}
        dash["run_incident_domain"] = classify_run_incident(run_op)
        dash["run_action_explain"] = explain_run_action(run_op)

        batch_recent = self.get_recent_batch_traces(80)
        operator_support = self._build_operator_support_payload(
            run_op=run_op,
            recent=recent,
            batches=batch_recent,
            operational_alerts=op_alerts,
        )
        if operator_support:
            dash["operator_headline"] = operator_support.get("operator_headline")
            dash["operator_triage_domain"] = operator_support.get("operator_triage_domain")
            dash["recommended_operator_action"] = operator_support.get("recommended_operator_action")
            dash["operator_status_explanation"] = build_human_status_message(run_op)
            dash["operator_runbook_explanation"] = operator_support.get("operator_runbook_explanation")

        snap = ParserHealthSnapshot(
            run_id=self._run_id,
            started_at=self._started_at,
            stores=list(self._stores),
            counters=merged,
            last_errors=last_errors,
            status=status,
            threshold_decisions=[d.model_dump(mode="json") for d in threshold_decisions],
            operational_alerts=op_alerts,
            dashboard_summary=dash,
            serialized_run_operational=serialize_run_status(run_op),
            error_aggregates_by_domain=aggregate_errors_by_domain(err_for_agg),
            operator_support=operator_support,
        )

        prev_op = self._last_operational_status
        self._emit_operational_signals(
            merged_status=status,
            run_op=run_op,
            threshold_decisions=threshold_decisions,
            run_id=self._run_id,
            prev_op_status=prev_op,
        )
        self._emit_operator_support_signals(
            run_id=self._run_id,
            operator_support=operator_support,
        )

        with self._lock:
            self._last_health_status = status
            self._last_snapshot_at = now
            self._cached_snapshot = snap
            self._last_operational_status = run_op.status
        return snap

    def _emit_operational_signals(
        self,
        *,
        merged_status: str,
        run_op: RunOperationalStatus,
        threshold_decisions: list[ThresholdDecision],
        run_id: str,
        prev_op_status: str,
    ) -> None:
        if not getattr(settings, "ENABLE_OPERATIONAL_POLICY_LOGS", True):
            return
        from infrastructure.observability.operational_logger import emit_operational_event

        for d in [x for x in threshold_decisions if x.breached][:12]:
            emit_operational_event(
                omc.THRESHOLD_BREACHED,
                run_id=run_id,
                metric_name=d.metric_name,
                observed_value=float(d.observed_value),
                threshold_value=float(d.threshold_value),
                severity=d.severity or "warning",
                details={"comparator": d.comparator, "notes": d.notes},
            )
        if run_op.status == "degraded" and prev_op_status != "degraded":
            emit_operational_event(
                omc.RUN_STATUS_DEGRADED,
                run_id=run_id,
                status=run_op.status,
                details={"operational": True},
            )
        dom = classify_run_incident(run_op)
        if run_op.status == "failing" and prev_op_status != "failing":
            emit_operational_event(
                omc.RUN_STATUS_FAILING,
                run_id=run_id,
                status=run_op.status,
                severity="critical",
                domain=str(dom) if dom else None,
                details={"operational": True},
            )
        emit_operational_event(
            omc.INCIDENT_CLASSIFIED,
            run_id=run_id,
            domain=str(dom) if dom else None,
            status=merged_status,
            details={"run_operational_status": run_op.status},
        )
        emit_operational_event(
            omc.ALERT_EMITTED,
            run_id=run_id,
            details={
                "total_alerts": sum(len(ss.alerts) for ss in run_op.store_statuses) + len(run_op.global_alerts),
            },
        )
        emit_operational_event(
            omc.RUN_ACTION_SUGGESTED,
            run_id=run_id,
            recommended_action=suggest_run_action(run_op),
            status=merged_status,
            details={"explain": explain_run_action(run_op)},
        )
        for ss in run_op.store_statuses:
            if ss.status == "degraded":
                emit_operational_event(
                    omc.STORE_STATUS_DEGRADED,
                    run_id=run_id,
                    store_name=ss.store_name,
                    status=ss.status,
                )
            elif ss.status == "failing":
                emit_operational_event(
                    omc.STORE_STATUS_FAILING,
                    run_id=run_id,
                    store_name=ss.store_name,
                    status=ss.status,
                    severity="critical",
                )
            if ss.status != "healthy":
                emit_operational_event(
                    omc.STORE_ACTION_SUGGESTED,
                    run_id=run_id,
                    store_name=ss.store_name,
                    recommended_action=suggest_store_action(ss),
                    details={"explain": explain_store_action(ss)},
                )

    def _build_operator_support_payload(
        self,
        *,
        run_op: RunOperationalStatus,
        recent: list[SyncTraceRecord],
        batches: list[BatchTraceRecord],
        operational_alerts: list[dict[str, object]],
    ) -> dict[str, object]:
        """5C: triage, runbooks, diagnostics, replay hints — compact JSON for export/tooling."""
        if not any(
            (
                settings.ENABLE_OPERATOR_TRIAGE_SUMMARY,
                settings.ENABLE_RUNBOOK_GENERATION,
                settings.ENABLE_DIAGNOSTIC_SNAPSHOTS,
                settings.ENABLE_SAFE_REPLAY_SUPPORT,
            )
        ):
            return {}

        out: dict[str, object] = {}
        triage_run = build_triage_summary_for_run(run_op, recent, batches)
        out["triage_run"] = serialize_triage_summary(triage_run)
        out["operator_headline"] = build_human_triage_message(triage_run)
        out["operator_triage_domain"] = triage_run.domain
        out["recommended_operator_action"] = triage_run.recommended_action

        out["triage_by_store"] = {
            ss.store_name: serialize_triage_summary(
                build_triage_summary_for_store(self._run_id, ss, recent, batches),
            )
            for ss in run_op.store_statuses
        }

        if settings.ENABLE_RUNBOOK_GENERATION:
            rb = get_runbook_for_domain(triage_run.domain, triage_run.severity)
            out["runbook"] = serialize_runbook(rb)
            out["operator_runbook_explanation"] = build_human_runbook_message(rb)
        else:
            out["operator_runbook_explanation"] = ""

        if settings.ENABLE_DIAGNOSTIC_SNAPSHOTS:
            dr = build_run_diagnostic_snapshot(self._run_id, run_op, recent, batches)
            out["diagnostic_run"] = serialize_diagnostic_snapshot(dr)
            by_store: dict[str, object] = {}
            for ss in run_op.store_statuses:
                st_alerts = [a for a in operational_alerts if a.get("store_name") in (ss.store_name, None)]
                ds = build_store_diagnostic_snapshot(
                    ss.store_name,
                    self._run_id,
                    recent,
                    batches,
                    dict(ss.counters),
                    st_alerts,
                )
                by_store[ss.store_name] = serialize_diagnostic_snapshot(ds)
            out["diagnostic_by_store"] = by_store
        else:
            out["diagnostic_run"] = {}
            out["diagnostic_by_store"] = {}

        if settings.ENABLE_SAFE_REPLAY_SUPPORT:
            replay_pf = decide_safe_replay_action("product_found", item_count=1, batch_count=1)
            replay_delta = decide_safe_replay_action("price_changed", item_count=1, batch_count=1)
            out["replay_hints"] = {
                "product_found_single_item": replay_pf.model_dump(mode="json"),
                "delta_price_changed_single_item": replay_delta.model_dump(mode="json"),
            }
        return out

    def _emit_operator_support_signals(
        self,
        *,
        run_id: str,
        operator_support: dict[str, object],
    ) -> None:
        if not operator_support or not getattr(settings, "ENABLE_OPERATIONAL_POLICY_LOGS", True):
            return
        from infrastructure.observability.operational_logger import emit_operational_event

        triage = operator_support.get("triage_run")
        if isinstance(triage, dict) and settings.ENABLE_OPERATOR_TRIAGE_SUMMARY:
            emit_operational_event(
                omc.TRIAGE_SUMMARY_BUILT,
                run_id=run_id,
                store_name=None,
                domain=str(triage.get("domain")),
                severity=str(triage.get("severity")),
                recommended_action=str(triage.get("recommended_action")),
                details={
                    "suspected_root_cause": triage.get("suspected_root_cause"),
                    "evidence_count": len(triage.get("evidence") or []),
                    "safe_scope": None,
                },
            )
            emit_operational_event(
                omc.OPERATOR_ACTION_RECOMMENDED,
                run_id=run_id,
                domain=str(triage.get("domain")),
                severity=str(triage.get("severity")),
                recommended_action=str(triage.get("recommended_action")),
                details={
                    "suspected_root_cause": triage.get("suspected_root_cause"),
                    "evidence_count": len(triage.get("evidence") or []),
                },
            )
        if settings.ENABLE_RUNBOOK_GENERATION:
            rb = operator_support.get("runbook")
            if isinstance(rb, dict):
                emit_operational_event(
                    omc.RUNBOOK_PLAN_BUILT,
                    run_id=run_id,
                    domain=str(rb.get("domain")),
                    severity=str(rb.get("severity")),
                    recommended_action=str(rb.get("final_recommendation")),
                    details={"steps": len(rb.get("steps") or [])},
                )
        if settings.ENABLE_DIAGNOSTIC_SNAPSHOTS:
            dr = operator_support.get("diagnostic_run")
            if isinstance(dr, dict) and dr.get("enabled") is not False:
                emit_operational_event(
                    omc.DIAGNOSTIC_SNAPSHOT_BUILT,
                    run_id=run_id,
                    domain=str(dr.get("runbook_domain")),
                    severity=str(dr.get("current_status")),
                    recommended_action=str(dr.get("recommended_action")),
                    details={
                        "top_alerts": len(dr.get("top_alerts") or []),
                        "failed_sample": len(dr.get("recent_failed_items_sample") or []),
                    },
                )
        if settings.ENABLE_SAFE_REPLAY_SUPPORT and operator_support.get("replay_hints"):
            hints = operator_support.get("replay_hints")
            if isinstance(hints, dict) and hints:
                pf = hints.get("product_found_single_item")
                safe_scope = pf.get("safe_scope") if isinstance(pf, dict) else None
                emit_operational_event(
                    omc.SAFE_REPLAY_DECISION,
                    run_id=run_id,
                    recommended_action=str(pf.get("action")) if isinstance(pf, dict) else None,
                    details={"replay_hints": hints, "safe_scope": safe_scope},
                )


_collector: TraceCollector | None = None
_collector_lock = threading.Lock()


def get_trace_collector() -> TraceCollector:
    global _collector
    with _collector_lock:
        if _collector is None:
            max_r = int(getattr(settings, "TRACE_BUFFER_MAX_RECORDS", 5000) or 5000)
            _collector = TraceCollector(max_records=max_r)
        return _collector


def reset_trace_collector_for_tests() -> None:
    global _collector
    with _collector_lock:
        max_r = int(getattr(settings, "TRACE_BUFFER_MAX_RECORDS", 5000) or 5000)
        _collector = TraceCollector(max_records=max_r)


def set_parser_run_context(*, run_id: str, stores: list[str] | None = None) -> None:
    get_trace_collector().set_run_context(run_id=run_id, stores=stores)


def record_trace(record: SyncTraceRecord) -> None:
    if not settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
        return
    get_trace_collector().record_trace(record)


def record_batch_trace(record: BatchTraceRecord) -> None:
    if not settings.ENABLE_BATCH_TRACE or not settings.ENABLE_IN_MEMORY_TRACE_BUFFER:
        return
    get_trace_collector().record_batch_trace(record)


def get_recent_traces(limit: int = 100) -> list[SyncTraceRecord]:
    return get_trace_collector().get_recent_traces(limit)


def get_recent_batch_traces(limit: int = 50) -> list[BatchTraceRecord]:
    return get_trace_collector().get_recent_batch_traces(limit)


def build_health_snapshot(extra_counters: dict[str, int | float] | None = None) -> ParserHealthSnapshot:
    tc = get_trace_collector()
    if not settings.ENABLE_HEALTH_SNAPSHOT:
        return ParserHealthSnapshot(
            run_id=tc.current_run_id,
            started_at=datetime.now(UTC),
            stores=tc.list_stores(),
            counters={},
            last_errors=[],
            status="healthy",
        )
    return tc.build_health_snapshot(extra_counters=extra_counters)


def trim_buffers_if_needed() -> None:
    get_trace_collector().trim_buffers_if_needed()
