from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx
import inspect

from datetime import UTC, datetime

from application.crm_sync_builder import build_entity_key
from application.release.rollout_policy_engine import is_feature_enabled
from application.lifecycle.lifecycle_builder import build_lifecycle_event, parser_sync_event_from_lifecycle
from application.lifecycle.reconciliation import (
    decide_reconciliation,
    reconcile_after_ambiguous_response,
    reconcile_missing_ids,
)
from config.settings import settings
from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult, MalformedCrmBatchResponse, summarize_batch_result
from domain.observability import BatchTraceRecord
from domain.parser_event import ParserSyncEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.correlation import build_batch_id, build_correlation_context, build_run_id
from infrastructure.observability.event_logger import log_batch_trace, log_developer_experience_event, log_sync_event
from infrastructure.observability.failure_classifier import classify_apply_result, classify_http_failure
from infrastructure.observability.metrics_collector import get_observability_metrics, DELIVERY_ITEMS_TOTAL
from infrastructure.observability.payload_summary import summarize_apply_result
from infrastructure.observability.trace_collector import build_health_snapshot, set_parser_run_context
from infrastructure.performance.perf_collector import set_run_context
from infrastructure.sync.batch_coordinator import BatchCoordinator
from infrastructure.sync.metrics import SyncMetricsCollector, emit_metrics_snapshot
from infrastructure.sync.runtime_identity_bridge import RuntimeIdentityBridge
from infrastructure.sync.runtime_registry import RuntimeSyncRegistry
from infrastructure.sync.runtime_replay_journal import RuntimeReplayJournal
from infrastructure.transports.dry_run import DryRunTransport
from infrastructure.transports.factory import get_transport

if TYPE_CHECKING:
    from infrastructure.transports.base import BaseTransport

logger = logging.getLogger(__name__)


def _slog(level: int, **fields: Any) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.log(level, "sync_delivery %s", json.dumps(payload, default=str, ensure_ascii=False))


class SyncPipeline:
    """Delivery-oriented sync: batch coordinator, item-level apply, runtime id bridge."""

    def __init__(self) -> None:
        self._transport: BaseTransport | None = None
        self._batch_size: int = min(settings.CRM_BATCH_SIZE, 100)
        self._registry = RuntimeSyncRegistry()
        self._identity_bridge = RuntimeIdentityBridge()
        self._coordinator = BatchCoordinator()
        self._metrics = SyncMetricsCollector()
        self._attempts: dict[str, int] = {}
        self._requeued_event_ids: set[str] = set()
        self._replay_journal = RuntimeReplayJournal()
        self._reconcile_resend_counts: dict[str, int] = {}
        self._run_id: str | None = None
        self._batch_seq: int = 0
        self._spider_name: str | None = None
        self._current_batch_id: str | None = None
        self._last_health_status: str = "healthy"
        self._store_name: str | None = None

    @classmethod
    def from_crawler(cls, _crawler):
        return cls()

    def open_spider(self, spider) -> None:
        self._transport = get_transport()
        if getattr(settings, "DEV_MODE", False):
            log_developer_experience_event(
                obs_mc.DEV_MODE_ENABLED,
                dev_run_mode=str(getattr(settings, "DEV_RUN_MODE", "normal")),
                store_name=getattr(spider, "store_name", None) or spider.name,
                dry_run=isinstance(self._transport, DryRunTransport),
                details={"spider": spider.name, "transport": type(self._transport).__name__},
            )
        if hasattr(self._transport, "attach_metrics"):
            self._transport.attach_metrics(self._metrics)
        self._registry = RuntimeSyncRegistry()
        self._identity_bridge = RuntimeIdentityBridge()
        self._coordinator = BatchCoordinator()
        self._coordinator.mark_flushed(now_mono=time.monotonic())
        self._metrics = SyncMetricsCollector()
        self._attempts.clear()
        self._requeued_event_ids.clear()
        self._replay_journal = RuntimeReplayJournal()
        self._reconcile_resend_counts.clear()
        rid = getattr(spider, "_parser_run_id", None) or build_run_id(spider.name)
        spider._parser_run_id = rid  # noqa: SLF001 — observability run anchor
        self._run_id = rid
        self._spider_name = spider.name
        self._batch_seq = 0
        store = getattr(spider, "store_name", None) or spider.name
        self._store_name = store
        set_parser_run_context(run_id=rid, stores=[store])
        set_run_context(run_id=rid, stores=[store])

    def _obs_corr(self, ev: ParserSyncEvent, *, batch_id: str | None = None):
        return build_correlation_context(
            self._spider_name or "unknown",
            ev.data.source_name,
            run_id=self._run_id,
            source_url=ev.data.source_url,
            source_id=ev.data.source_id,
            entity_key=ev.data.entity_key,
            event_id=ev.event_id,
            payload_hash=ev.data.payload_hash,
            request_idempotency_key=ev.request_idempotency_key,
            batch_id=batch_id,
        )

    async def close_spider(self, spider) -> None:
        rounds = 0
        while self._coordinator.has_work() and rounds < 2000:
            await self._flush_one_round(reason="close_spider", force=True)
            rounds += 1
        emit_metrics_snapshot(self._metrics)
        self._metrics.log_summary()
        try:
            extra: dict[str, float] = {k: float(v) for k, v in self._metrics.to_dict().items()}
            cr = getattr(spider, "crawl_registry", None)
            if cr is not None:
                snap = cr.snapshot_metrics()
                for k in (
                    "categories_started_total",
                    "categories_zero_result_total",
                    "listing_pages_seen_total",
                    "product_items_yielded_total",
                    "product_parse_failed_total",
                    "product_pages_seen_total",
                ):
                    if k in snap:
                        extra[k] = float(snap[k])
            store_nm = getattr(spider, "store_name", None) or spider.name
            if is_feature_enabled("observability_export", str(store_nm)):
                health = build_health_snapshot(extra_counters=extra)
            else:
                health = None
            if health is not None and health.status != self._last_health_status:
                self._last_health_status = health.status
                log_sync_event(
                    "reconcile",
                    "info",
                    obs_mc.HEALTH_STATUS_CHANGED,
                    build_correlation_context(
                        self._spider_name or spider.name,
                        getattr(spider, "store_name", None) or spider.name,
                        run_id=self._run_id,
                    ),
                    metrics={"status": health.status},
                    details={"counters": dict(health.counters)},
                )
        except Exception:
            logger.debug("observability health snapshot on close failed", exc_info=True)
        if self._transport:
            await self._transport.close()
        self._transport = None
        try:
            if getattr(settings, "ENABLE_RUN_PERFORMANCE_SNAPSHOT", True) and self._run_id:
                from infrastructure.observability import message_codes as pmc
                from infrastructure.observability.event_logger import log_perf_event
                from infrastructure.performance.bottleneck_detector import detect_bottlenecks
                from infrastructure.performance.perf_collector import build_run_snapshot
                from infrastructure.performance.performance_exporter import (
                    build_bottleneck_summary,
                    build_run_performance_payload,
                )
                from infrastructure.performance.resource_snapshot import build_resource_snapshot

                store_nm = getattr(spider, "store_name", None) or spider.name
                snap = build_run_snapshot(self._run_id, [store_nm])
                log_perf_event(
                    pmc.PERF_RUN_SNAPSHOT_BUILT,
                    details={"run": build_run_performance_payload(snap)},
                )
                if getattr(settings, "ENABLE_BOTTLENECK_DETECTION", True):
                    sigs = detect_bottlenecks(snap, settings)
                    if sigs:
                        log_perf_event(
                            pmc.PERF_BOTTLENECK_DETECTED,
                            details=build_bottleneck_summary(sigs),
                        )
                log_perf_event(
                    pmc.PERF_RESOURCE_SNAPSHOT,
                    details=build_resource_snapshot(),
                )
                if getattr(settings, "ENABLE_STORE_PERFORMANCE_SNAPSHOT", True):
                    for ss in snap.store_snapshots:
                        from infrastructure.performance.performance_exporter import (
                            build_store_performance_payload,
                        )

                        log_perf_event(
                            pmc.PERF_STORE_SNAPSHOT_BUILT,
                            store_name=ss.store_name,
                            products_per_minute=ss.products_per_minute,
                            batches_per_minute=ss.batches_per_minute,
                            memory_mb=ss.memory_estimate_mb,
                            details={"store": build_store_performance_payload(ss)},
                        )
        except Exception:
            logger.debug("performance snapshot on close failed", exc_info=True)
        try:
            if getattr(settings, "ENABLE_COST_EFFICIENCY_TRACKING", True) and self._run_id:
                from infrastructure.observability import message_codes as cost_mc
                from infrastructure.observability.event_logger import log_cost_efficiency_event
                from infrastructure.performance.cost_exporter import build_run_cost_payload
                from infrastructure.performance.cost_model import build_run_cost_snapshot
                from infrastructure.performance.perf_collector import export_all_store_cost_counters, get_store_cost_counters

                store_nm = getattr(spider, "store_name", None) or spider.name
                ctr = dict(export_all_store_cost_counters())
                ctr.setdefault(store_nm, get_store_cost_counters(store_nm))
                cost_snap = build_run_cost_snapshot(self._run_id, ctr, settings)
                log_cost_efficiency_event(
                    cost_mc.COST_SNAPSHOT_BUILT,
                    store_name=store_nm,
                    estimated_cost_units=cost_snap.total_estimated_cost_units,
                    details=build_run_cost_payload(cost_snap),
                )
                from application.performance.cost_degradation_advisor import (
                    explain_cost_reduction_action,
                    suggest_cost_reduction_action,
                )
                from infrastructure.performance.cost_exporter import build_efficiency_signal_payload
                from infrastructure.performance.efficiency_evaluator import evaluate_store_efficiency

                for ss in cost_snap.store_snapshots:
                    sigs = evaluate_store_efficiency(ss, settings)
                    if not sigs:
                        continue
                    log_cost_efficiency_event(
                        cost_mc.EFFICIENCY_SIGNAL_DETECTED,
                        store_name=ss.store_name,
                        estimated_cost_units=ss.estimated_cost_units,
                        products_per_cost_unit=ss.products_per_cost_unit,
                        applied_per_cost_unit=ss.applied_per_cost_unit,
                        details=build_efficiency_signal_payload(sigs),
                    )
                    action = suggest_cost_reduction_action(ss, sigs)
                    if action != "none":
                        log_cost_efficiency_event(
                            cost_mc.COST_REDUCTION_ACTION_SUGGESTED,
                            store_name=ss.store_name,
                            recommended_action=action,
                            details={"lines": explain_cost_reduction_action(ss, sigs)},
                        )
        except Exception:
            logger.debug("cost efficiency snapshot on close failed", exc_info=True)

    async def process_item(self, item, spider):
        if self._transport is None:
            raise RuntimeError("SyncPipeline: transport not initialized")

        self._metrics.items_seen_total += 1

        norm = item.get("_normalized")
        if not norm:
            _slog(
                logging.WARNING,
                result="skip",
                error_message="missing_normalized",
                source_url=item.get("url"),
            )
            return item

        store = str(norm.get("store") or "")
        url = str(norm.get("url") or "")
        sid = norm.get("source_id")
        if isinstance(sid, str) and not sid.strip():
            sid = None
        entity_key = build_entity_key(store, sid if isinstance(sid, str) else None, url)
        runtime_ids = self._identity_bridge.get_runtime_ids(entity_key)
        _ple, _decision = build_lifecycle_event(norm, runtime_ids=runtime_ids, requested_event_type=None)
        event = parser_sync_event_from_lifecycle(_ple, normalized_for_reconcile=dict(norm))
        sync_item = event.data
        item["_sync_payload_entity_key"] = sync_item.entity_key
        item["_parser_sync_event_id"] = event.event_id

        if settings.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD and self._identity_bridge.should_skip_event(
            sync_item.entity_key,
            sync_item.payload_hash,
        ):
            self._metrics.duplicate_payload_skips_total += 1
            _slog(
                logging.INFO,
                event="RUNTIME_DUPLICATE_PAYLOAD_SKIPPED",
                store=sync_item.source_name,
                entity_key=sync_item.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=sync_item.payload_hash,
            )
            log_sync_event(
                "lifecycle_select",
                "info",
                obs_mc.DUPLICATE_PAYLOAD_SKIPPED,
                self._obs_corr(event),
                details={"reason": "runtime_same_entity_same_payload"},
                failure_domain="internal",
                failure_type="duplicate_payload_skipped",
            )
            return item

        if self._registry.should_skip(sync_item.entity_key, sync_item.payload_hash):
            self._metrics.items_deduped_total += 1
            _slog(
                logging.INFO,
                event_type=event.event_type,
                event_id=event.event_id,
                entity_key=sync_item.entity_key,
                payload_hash=sync_item.payload_hash,
                store=sync_item.source_name,
                source_id=sync_item.source_id,
                source_url=sync_item.source_url,
                result="deduped_skip",
            )
            return item

        if not self._coordinator.add_event(event):
            self._metrics.duplicate_payload_skips_total += 1
            _slog(
                logging.INFO,
                event="RUNTIME_DUPLICATE_PAYLOAD_SKIPPED",
                store=sync_item.source_name,
                entity_key=sync_item.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=sync_item.payload_hash,
                reason="duplicate_in_flight_queue",
            )
            log_sync_event(
                "delivery_send",
                "info",
                obs_mc.DUPLICATE_PAYLOAD_SKIPPED,
                self._obs_corr(event),
                details={"reason": "duplicate_in_flight_queue"},
                failure_domain="internal",
                failure_type="duplicate_payload_skipped",
            )
            return item

        self._sync_retry_queue_tracker()

        now = time.monotonic()
        if self._coordinator.should_flush(
            now_mono=now,
            interval_seconds=settings.SYNC_BUFFER_FLUSH_SECONDS,
            batch_size=self._batch_size,
        ):
            await self._flush_one_round(reason="batch_or_timer", force=False)

        return item

    def _sync_retry_queue_tracker(self) -> None:
        from infrastructure.performance.resource_tracker import set_retryable_queue_size

        st = self._store_name or "unknown"
        set_retryable_queue_size(st, self._coordinator.retry_queue_len())

    async def _flush_one_round(self, *, reason: str, force: bool = False) -> None:
        if self._transport is None:
            return

        self._sync_retry_queue_tracker()
        st_gov = self._store_name or "unknown"
        if not force and getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
            import asyncio

            from application.performance.backpressure_policy import decide_backpressure, decide_throttle_adjustment
            from application.performance.concurrency_policy import decide_batch_admission
            from application.performance.graceful_degradation import explain_degradation_mode, suggest_degradation_mode
            from config.store_resource_budgets import get_store_budget
            from infrastructure.observability import message_codes as rg_mc
            from infrastructure.observability.event_logger import log_resource_governance_event
            from infrastructure.performance.resource_exporter import build_backpressure_payload
            from infrastructure.performance.resource_tracker import build_runtime_state

            budget = get_store_budget(st_gov)
            state = build_runtime_state(st_gov)
            badm = decide_batch_admission(st_gov, state, budget)
            if not badm.allowed:
                log_resource_governance_event(
                    rg_mc.BATCH_BACKPRESSURE_APPLIED,
                    store_name=st_gov,
                    reason=badm.reason,
                    selected_limit=badm.selected_limit,
                    inflight_batches=state.inflight_batches,
                    retryable_queue=state.queued_retryable_items,
                    details={"batch_admission": "deferred"},
                )
                await asyncio.sleep(0.05)
                return
            bp = decide_backpressure(st_gov, state, budget, settings)
            thr = decide_throttle_adjustment(st_gov, state, budget, settings)
            if thr.throttle:
                log_resource_governance_event(
                    rg_mc.RESOURCE_THROTTLE_ADJUSTED,
                    store_name=st_gov,
                    mode=thr.mode,
                    reason=thr.reason,
                    selected_limit=thr.new_limit,
                )
            if bp.apply_backpressure and getattr(settings, "ENABLE_BATCH_BACKPRESSURE", True):
                log_resource_governance_event(
                    rg_mc.BACKPRESSURE_APPLIED,
                    store_name=st_gov,
                    reason=bp.reason,
                    suggested_action=bp.suggested_action,
                    details=build_backpressure_payload(bp),
                )
                if bp.severity == "critical":
                    mode = suggest_degradation_mode(st_gov, state, bp)
                    log_resource_governance_event(
                        rg_mc.STORE_DEGRADATION_SUGGESTED,
                        store_name=st_gov,
                        reason=bp.reason,
                        suggested_action=mode,
                        details={"lines": explain_degradation_mode(st_gov, state, bp)},
                    )
                if bp.suggested_action == "pause_batches":
                    await asyncio.sleep(0.1)
                    return
                if bp.suggested_action == "slow_down":
                    await asyncio.sleep(0.05)
                elif bp.suggested_action in ("degrade_store", "reduce_browser", "reduce_proxy"):
                    await asyncio.sleep(0.08)

        flush_t0 = time.monotonic()
        batch, waits = self._coordinator.pop_flush_batch_with_waits()
        if not batch:
            return

        to_send: list[ParserSyncEvent] = []
        wait_for_send: list[float] = []
        dropped: list[ParserSyncEvent] = []
        for ev, w in zip(batch, waits):
            nxt = self._attempts.get(ev.event_id, 0) + 1
            if nxt > settings.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN:
                dropped.append(ev)
                continue
            self._attempts[ev.event_id] = nxt
            to_send.append(ev)
            wait_for_send.append(w)

        for ev in dropped:
            self._coordinator.release_fingerprints([ev])
            self._attempts.pop(ev.event_id, None)
            _slog(
                logging.WARNING,
                event="BATCH_ITEM_REJECTED",
                message="max_event_attempts_per_run_exceeded",
                store=ev.data.source_name,
                entity_key=ev.data.entity_key,
                event_id=ev.event_id,
                event_type=ev.event_type,
                payload_hash=ev.data.payload_hash,
                attempt=settings.PARSER_MAX_EVENT_ATTEMPTS_PER_RUN,
            )

        if not to_send:
            return

        from infrastructure.performance.perf_collector import increment_counter, record_duration
        from infrastructure.performance.resource_tracker import decrement_inflight_batch, increment_inflight_batch

        st_nm = to_send[0].data.source_name
        increment_inflight_batch(st_nm)
        try:
            await self._execute_batch_send(
                to_send=to_send,
                wait_for_send=wait_for_send,
                reason=reason,
                flush_t0=flush_t0,
            )
        finally:
            decrement_inflight_batch(st_nm)

    async def _execute_batch_send(
        self,
        *,
        to_send: list[ParserSyncEvent],
        wait_for_send: list[float],
        reason: str,
        flush_t0: float,
    ) -> None:
        from infrastructure.performance.perf_collector import increment_counter, record_duration

        st_nm = to_send[0].data.source_name
        if wait_for_send:
            record_duration(
                "batch_buffer",
                sum(wait_for_send) / float(len(wait_for_send)),
                store_name=st_nm,
            )
        increment_counter("batches", 1, store_name=st_nm)
        increment_counter("crm_roundtrips", 1, store_name=st_nm)

        self._batch_seq += 1
        batch_id = build_batch_id(self._run_id or "unknown", self._batch_seq)
        self._current_batch_id = batch_id

        self._metrics.batch_flushes_total += 1
        self._metrics.batch_requests_total += 1
        self._metrics.items_sent_total += len(to_send)
        self._metrics.batch_items_total += len(to_send)
        self._coordinator.mark_flushed(now_mono=time.monotonic())

        get_observability_metrics().inc(DELIVERY_ITEMS_TOTAL, float(len(to_send)))

        log_sync_event(
            "delivery_send",
            "info",
            obs_mc.DELIVERY_BATCH_STARTED,
            self._obs_corr(to_send[0], batch_id=batch_id),
            metrics={"batch_size": len(to_send), "items": len(to_send)},
            details={"reason": reason, "batch_id": batch_id},
        )

        _slog(
            logging.INFO,
            event="BATCH_FLUSH_STARTED",
            reason=reason,
            batch_size=len(to_send),
            store=to_send[0].data.source_name,
        )

        for ev in to_send:
            if ev.request_idempotency_key:
                self._replay_journal.remember_send_attempt(ev.request_idempotency_key, ev.event_type)
                if self._replay_journal.has_seen_idempotency_key(ev.request_idempotency_key):
                    _slog(
                        logging.INFO,
                        event="SAFE_RESEND_TRIGGERED",
                        store=ev.data.source_name,
                        entity_key=ev.data.entity_key,
                        event_type=ev.event_type,
                        selected_event_type=ev.event_type,
                        payload_hash=ev.data.payload_hash,
                        request_idempotency_key=ev.request_idempotency_key,
                        replay_mode=ev.replay_mode,
                        attempt=self._replay_journal.send_attempt_count(ev.request_idempotency_key),
                    )
                self._replay_journal.remember_entity_meta(
                    ev.data.entity_key,
                    ev.event_type,
                    ev.request_idempotency_key,
                )

        batch_res: CrmBatchApplyResult | None = None
        try:
            hint = getattr(self._transport, "set_obs_batch_hint", None)
            if callable(hint):
                maybe = hint(
                    run_id=self._run_id,
                    store_name=to_send[0].data.source_name,
                    batch_id=batch_id,
                    spider_name=self._spider_name,
                )
                if inspect.isawaitable(maybe):
                    await maybe
            batch_res = await self._transport.send_batch_events(to_send)
        except MalformedCrmBatchResponse as exc:
            self._metrics.malformed_batch_responses_total += 1
            fd, ft = classify_http_failure(exc.batch.http_status if exc.batch else None, str(exc))
            log_sync_event(
                "delivery_send",
                "error",
                "BATCH_RESPONSE_MALFORMED",
                self._obs_corr(to_send[0], batch_id=batch_id),
                metrics={"batch_size": len(to_send)},
                details={"error": str(exc)[:500]},
                failure_domain=fd,
                failure_type=ft,
            )
            log_batch_trace(
                BatchTraceRecord(
                    batch_id=batch_id,
                    run_id=self._run_id or "unknown",
                    store_name=to_send[0].data.source_name,
                    created_at=datetime.now(UTC),
                    flushed_at=datetime.now(UTC),
                    item_count=len(to_send),
                    success_count=0,
                    rejected_count=0,
                    retryable_count=0,
                    ignored_count=0,
                    transport_failed=True,
                    http_status=exc.batch.http_status if exc.batch else None,
                    notes=["malformed_batch_response"],
                )
            )
            _slog(
                logging.ERROR,
                event="BATCH_RESPONSE_MALFORMED",
                batch_size=len(to_send),
                http_status=exc.batch.http_status if exc.batch else None,
                error_code=exc.batch.batch_error_code if exc.batch else "malformed_batch_response",
                error_message=str(exc),
            )
            if settings.CRM_BATCH_STOP_ON_MALFORMED_RESPONSE:
                for ev in to_send:
                    self._coordinator.release_fingerprints([ev])
                raise
            batch_res = exc.batch
            if batch_res is None or len(batch_res.items) != len(to_send):
                for ev in to_send:
                    self._coordinator.release_fingerprints([ev])
                return
        except httpx.TransportError:
            self._metrics.batch_transport_failures_total += 1
            self._metrics.items_failed_total += len(to_send)
            for ev in to_send:
                self._coordinator.release_fingerprints([ev])
            log_sync_event(
                "delivery_send",
                "error",
                obs_mc.DELIVERY_BATCH_COMPLETED,
                self._obs_corr(to_send[0], batch_id=batch_id),
                metrics={"batch_size": len(to_send)},
                details={"result": "transport_error"},
                failure_domain="transport",
                failure_type="timeout",
            )
            log_batch_trace(
                BatchTraceRecord(
                    batch_id=batch_id,
                    run_id=self._run_id or "unknown",
                    store_name=to_send[0].data.source_name,
                    created_at=datetime.now(UTC),
                    flushed_at=datetime.now(UTC),
                    item_count=len(to_send),
                    success_count=0,
                    rejected_count=0,
                    retryable_count=0,
                    ignored_count=0,
                    transport_failed=True,
                    http_status=0,
                    notes=["batch_transport_failed"],
                )
            )
            _slog(
                logging.ERROR,
                event="BATCH_FLUSH_COMPLETED",
                result="transport_error",
                error_message="batch_transport_failed",
                batch_size=len(to_send),
                http_status=0,
            )
            if settings.TRANSPORT_FAIL_FAST:
                raise
            return
        except Exception:
            self._metrics.items_failed_total += len(to_send)
            for ev in to_send:
                self._coordinator.release_fingerprints([ev])
            log_sync_event(
                "delivery_send",
                "critical",
                obs_mc.DELIVERY_BATCH_COMPLETED,
                self._obs_corr(to_send[0], batch_id=batch_id),
                metrics={"batch_size": len(to_send)},
                details={"result": "unexpected_batch_error"},
                failure_domain="internal",
                failure_type="parse_failed",
            )
            logger.exception("sync_batch_unexpected_error")
            if settings.TRANSPORT_FAIL_FAST:
                raise
            return

        assert batch_res is not None
        await self._finalize_batch_results(to_send, batch_res, reason=reason, batch_id=batch_id)
        wall_ms = (time.monotonic() - flush_t0) * 1000.0
        self._coordinator.last_batch_flush_ms = wall_ms
        self._coordinator.last_batch_queue_wait_avg_ms = (
            sum(wait_for_send) / float(len(wait_for_send)) if wait_for_send else None
        )
        self._coordinator.last_items_per_flush = len(to_send)

    async def _finalize_batch_results(
        self,
        to_send: list[ParserSyncEvent],
        batch_res: CrmBatchApplyResult,
        *,
        reason: str,
        batch_id: str,
    ) -> None:
        if len(batch_res.items) != len(to_send):
            self._metrics.malformed_batch_responses_total += 1
            log_sync_event(
                "delivery_send",
                "error",
                "BATCH_RESPONSE_MALFORMED",
                self._obs_corr(to_send[0], batch_id=batch_id),
                metrics={"expected": len(to_send), "got": len(batch_res.items)},
                failure_domain="crm_apply",
                failure_type="malformed_response",
            )
            log_batch_trace(
                BatchTraceRecord(
                    batch_id=batch_id,
                    run_id=self._run_id or "unknown",
                    store_name=to_send[0].data.source_name,
                    created_at=datetime.now(UTC),
                    flushed_at=datetime.now(UTC),
                    item_count=len(to_send),
                    success_count=0,
                    rejected_count=0,
                    retryable_count=0,
                    ignored_count=0,
                    transport_failed=False,
                    http_status=batch_res.http_status,
                    notes=["item_count_mismatch"],
                )
            )
            _slog(
                logging.ERROR,
                event="BATCH_RESPONSE_MALFORMED",
                batch_size=len(to_send),
                error_message="item_count_mismatch",
                got=len(batch_res.items),
            )
            for ev in to_send:
                self._coordinator.release_fingerprints([ev])
            if settings.TRANSPORT_FAIL_FAST:
                raise RuntimeError("CRM batch item count mismatch")
            return

        summary = summarize_batch_result(batch_res)
        any_fail = summary.failed > 0
        any_ok = summary.succeeded > 0
        if any_fail and any_ok:
            self._metrics.batch_partial_failures_total += 1

        if not settings.SYNC_ALLOW_PARTIAL_BATCH_SUCCESS and any_fail:
            for ev in to_send:
                self._coordinator.release_fingerprints([ev])
            raise RuntimeError("batch had failures and SYNC_ALLOW_PARTIAL_BATCH_SUCCESS is false")

        _slog(
            logging.INFO,
            event="BATCH_FLUSH_COMPLETED",
            reason=reason,
            batch_size=len(to_send),
            http_status=batch_res.http_status,
            succeeded=summary.succeeded,
            failed=summary.failed,
            transport_ok=batch_res.transport_ok,
        )

        log_sync_event(
            "delivery_send",
            "info",
            obs_mc.DELIVERY_BATCH_COMPLETED,
            self._obs_corr(to_send[0], batch_id=batch_id),
            metrics={
                "batch_size": len(to_send),
                "succeeded": summary.succeeded,
                "failed": summary.failed,
                "http_status": batch_res.http_status,
            },
            details={"reason": reason, "transport_ok": batch_res.transport_ok, "batch_id": batch_id},
        )

        succ = summary.succeeded
        ign = summary.ignored
        rej = summary.rejected
        retry_n = summary.retryable_failed
        log_batch_trace(
            BatchTraceRecord(
                batch_id=batch_id,
                run_id=self._run_id or "unknown",
                store_name=to_send[0].data.source_name,
                created_at=datetime.now(UTC),
                flushed_at=datetime.now(UTC),
                item_count=len(to_send),
                success_count=int(succ),
                rejected_count=int(rej),
                retryable_count=int(retry_n),
                ignored_count=int(ign),
                transport_failed=not bool(batch_res.transport_ok),
                http_status=batch_res.http_status,
                notes=[reason],
            )
        )

        for ev, res in zip(to_send, batch_res.items):
            await self._apply_item_result(ev, res, batch_id=batch_id)

    async def _maybe_enqueue_product_found_resend(self, event: ParserSyncEvent, norm: dict[str, Any]) -> bool:
        ek = event.data.entity_key
        n = self._reconcile_resend_counts.get(ek, 0)
        if n >= settings.PARSER_RECONCILE_MAX_ATTEMPTS_PER_RUN:
            return False
        if not settings.PARSER_ALLOW_SAFE_RESEND_PRODUCT_FOUND:
            return False
        self._reconcile_resend_counts[ek] = n + 1
        rt = self._identity_bridge.get_runtime_ids(ek)
        ple, _ = build_lifecycle_event(norm, runtime_ids=rt, requested_event_type="product_found")
        ev2 = parser_sync_event_from_lifecycle(ple, normalized_for_reconcile=dict(norm))
        if ev2.request_idempotency_key:
            self._replay_journal.remember_send_attempt(ev2.request_idempotency_key, ev2.event_type)
        _slog(
            logging.INFO,
            event="SAFE_RESEND_TRIGGERED",
            store=ev2.data.source_name,
            entity_key=ek,
            event_type=ev2.event_type,
            selected_event_type=ev2.event_type,
            payload_hash=ev2.data.payload_hash,
            request_idempotency_key=ev2.request_idempotency_key,
            replay_mode=ev2.replay_mode,
            reason="reconciliation_resend_product_found",
            attempt=self._reconcile_resend_counts[ek],
        )
        self._coordinator.add_event(ev2)
        return True

    async def _reconcile_success_apply(
        self,
        event: ParserSyncEvent,
        res: CrmApplyResult,
        *,
        batch_id: str | None = None,
    ) -> CrmApplyResult | None:
        """Merge runtime/catalog into apply result, or enqueue resend and abort success path."""
        sig = res.parser_reconciliation_signal
        if not is_feature_enabled("replay_reconciliation", event.data.source_name, event.data.entity_key):
            if sig:
                return res.model_copy(update={"parser_reconciliation_signal": None})
            return res
        if not sig:
            return res
        from infrastructure.performance.timing_profiler import finish_stage, start_stage

        tok_rec = start_stage(
            "reconcile",
            store_name=event.data.source_name,
            entity_key=event.data.entity_key,
            batch_id=batch_id,
        )
        try:
            norm = dict(event.normalized_for_reconcile or {})
            ek = event.data.entity_key
            rt = self._identity_bridge.get_runtime_ids(ek)
            dec = decide_reconciliation(event.event_type, res, rt)
            log_sync_event(
                "reconcile",
                "info",
                obs_mc.RECONCILIATION_STARTED,
                self._obs_corr(event, batch_id=batch_id),
                metrics={"attempt": self._reconcile_resend_counts.get(ek, 0)},
                details={"reconcile_via": dec.reconcile_via, "reason": dec.reason, "signal": sig},
            )
            _slog(
                logging.INFO,
                event="RECONCILIATION_STARTED",
                store=event.data.source_name,
                entity_key=ek,
                event_type=event.event_type,
                selected_event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                request_idempotency_key=event.request_idempotency_key,
                replay_mode=event.replay_mode,
                reconcile_via=dec.reconcile_via,
                reason=dec.reason,
                attempt=self._reconcile_resend_counts.get(ek, 0),
            )
            if sig == "missing_ids":
                _slog(
                    logging.WARNING,
                    event="RESPONSE_IDS_MISSING",
                    store=event.data.source_name,
                    entity_key=ek,
                    event_type=event.event_type,
                    payload_hash=event.data.payload_hash,
                    request_idempotency_key=event.request_idempotency_key,
                    http_status=res.http_status,
                    action=res.action,
                )
            if sig == "ambiguous_action":
                _slog(
                    logging.WARNING,
                    event="AMBIGUOUS_SYNC_RESULT",
                    store=event.data.source_name,
                    entity_key=ek,
                    event_type=event.event_type,
                    payload_hash=event.data.payload_hash,
                    action=res.action,
                    http_status=res.http_status,
                )
            if sig == "ambiguous_action":
                rec = reconcile_after_ambiguous_response(event.identity, norm, runtime_ids=rt)
            else:
                rec = reconcile_missing_ids(event.identity, norm, runtime_ids=rt, apply_result=res)
            self._replay_journal.remember_reconciliation(ek, rec)
            if rec.resolved and (rec.crm_listing_id or rec.crm_product_id):
                log_sync_event(
                    "reconcile",
                    "info",
                    obs_mc.RECONCILIATION_RESOLVED,
                    self._obs_corr(event, batch_id=batch_id),
                    details={
                        "crm_listing_id": rec.crm_listing_id,
                        "crm_product_id": rec.crm_product_id,
                        "action": rec.action,
                    },
                )
                _slog(
                    logging.INFO,
                    event="RECONCILIATION_RESOLVED",
                    store=event.data.source_name,
                    entity_key=ek,
                    event_type=event.event_type,
                    crm_listing_id=rec.crm_listing_id,
                    crm_product_id=rec.crm_product_id,
                    action=rec.action,
                    reconcile_via=dec.reconcile_via,
                    reason=dec.reason,
                )
                lid = rec.crm_listing_id or res.crm_listing_id
                pid = rec.crm_product_id or res.crm_product_id
                return res.model_copy(
                    update={
                        "crm_listing_id": lid,
                        "crm_product_id": pid,
                        "parser_reconciliation_signal": None,
                    }
                )
            log_sync_event(
                "reconcile",
                "warning",
                obs_mc.RECONCILIATION_UNRESOLVED,
                self._obs_corr(event, batch_id=batch_id),
                details={"reason": dec.reason, "signal": sig},
                failure_domain="reconciliation",
                failure_type="reconciliation_failed",
            )
            _slog(
                logging.WARNING,
                event="RECONCILIATION_UNRESOLVED",
                store=event.data.source_name,
                entity_key=ek,
                event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                request_idempotency_key=event.request_idempotency_key,
                reason=dec.reason,
            )
            await self._maybe_enqueue_product_found_resend(event, norm)
            return None
        finally:
            finish_stage(tok_rec)

    async def _apply_item_result(
        self,
        event: ParserSyncEvent,
        res: CrmApplyResult,
        *,
        batch_id: str | None = None,
    ) -> None:
        attempt = self._attempts.get(event.event_id, 1)
        summ = summarize_apply_result(res) if settings.ENABLE_DIAGNOSTIC_PAYLOAD_SUMMARY else {}

        if res.success:
            merged = await self._reconcile_success_apply(event, res, batch_id=batch_id)
            if merged is None and res.parser_reconciliation_signal:
                self._coordinator.release_fingerprints([event])
                return
            if merged is not None:
                res = merged
            self._metrics.items_synced_total += 1
            self._metrics.batch_items_applied_total += 1
            from infrastructure.performance.perf_collector import increment_counter

            increment_counter("products_applied", 1, store_name=event.data.source_name)
            self._registry.remember_payload(event.data.entity_key, event.data.payload_hash)
            self._registry.remember_crm_ids(
                event.data.entity_key,
                res.crm_listing_id,
                res.crm_product_id,
                res.action,
            )
            self._identity_bridge.remember_apply_result(res)
            self._metrics.runtime_id_updates_total += 1
            self._coordinator.release_fingerprints([event])
            if res.status == "ignored":
                log_sync_event(
                    "crm_apply",
                    "info",
                    obs_mc.CRM_APPLY_IGNORED,
                    self._obs_corr(event, batch_id=batch_id),
                    metrics={"attempt": attempt},
                    details=summ,
                )
            else:
                log_sync_event(
                    "crm_apply",
                    "info",
                    obs_mc.CRM_APPLY_SUCCESS,
                    self._obs_corr(event, batch_id=batch_id),
                    metrics={"attempt": attempt, "http_status": res.http_status},
                    details=summ,
                )
            log_sync_event(
                "crm_apply",
                "info",
                obs_mc.CRM_IDS_PROPAGATED,
                self._obs_corr(event, batch_id=batch_id),
                details={
                    "crm_listing_id": res.crm_listing_id,
                    "crm_product_id": res.crm_product_id,
                    "action": res.action,
                },
            )
            _slog(
                logging.INFO,
                event="BATCH_ITEM_APPLIED",
                store=event.data.source_name,
                entity_key=event.data.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                http_status=res.http_status,
                status=res.status,
                action=res.action,
                crm_listing_id=res.crm_listing_id,
                crm_product_id=res.crm_product_id,
                retryable=res.retryable,
                attempt=attempt,
                error_code=res.error_code,
                error_message=res.error_message,
            )
            _slog(
                logging.INFO,
                event="RUNTIME_ID_PROPAGATED",
                store=event.data.source_name,
                entity_key=event.data.entity_key,
                event_id=event.event_id,
                crm_listing_id=res.crm_listing_id,
                crm_product_id=res.crm_product_id,
                action=res.action,
                payload_hash=event.data.payload_hash,
            )
            return

        self._metrics.items_failed_total += 1
        if res.retryable:
            self._metrics.batch_items_retryable_total += 1

        fd, ft = classify_apply_result(res)

        if res.status == "rejected" or (not res.retryable):
            self._metrics.batch_items_rejected_total += 1
            self._coordinator.release_fingerprints([event])
            log_sync_event(
                "crm_apply",
                "warning",
                obs_mc.CRM_APPLY_REJECTED,
                self._obs_corr(event, batch_id=batch_id),
                metrics={"attempt": attempt},
                details=summ,
                failure_domain=fd or "crm_apply",
                failure_type=ft or "rejected_item",
            )
            _slog(
                logging.WARNING,
                event="BATCH_ITEM_REJECTED",
                store=event.data.source_name,
                entity_key=event.data.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                http_status=res.http_status,
                status=res.status,
                action=res.action,
                crm_listing_id=res.crm_listing_id,
                crm_product_id=res.crm_product_id,
                retryable=res.retryable,
                attempt=attempt,
                error_code=res.error_code,
                error_message=res.error_message,
            )
            return

        if (
            res.retryable
            and settings.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS
            and settings.PARSER_REQUEUE_RETRYABLE_ONCE
            and event.event_id not in self._requeued_event_ids
        ):
            self._requeued_event_ids.add(event.event_id)
            self._metrics.batch_items_requeued_total += 1
            self._coordinator.requeue_retryable([event])
            log_sync_event(
                "crm_apply",
                "warning",
                obs_mc.CRM_APPLY_RETRYABLE,
                self._obs_corr(event, batch_id=batch_id),
                metrics={"attempt": attempt},
                details=summ,
                failure_domain=fd or "crm_apply",
                failure_type=ft or "retryable_item",
            )
            log_sync_event(
                "delivery_send",
                "info",
                obs_mc.DELIVERY_RETRY,
                self._obs_corr(event, batch_id=batch_id),
                details={"reason": "requeue_retryable_once"},
            )
            _slog(
                logging.INFO,
                event="BATCH_ITEM_REQUEUED",
                store=event.data.source_name,
                entity_key=event.data.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                http_status=res.http_status,
                status=res.status,
                retryable=True,
                attempt=attempt,
                error_code=res.error_code,
                error_message=res.error_message,
            )
            return

        if res.retryable and settings.CRM_BATCH_REQUEUE_RETRYABLE_ITEMS and not settings.PARSER_REQUEUE_RETRYABLE_ONCE:
            self._metrics.batch_items_requeued_total += 1
            self._coordinator.requeue_retryable([event])
            log_sync_event(
                "crm_apply",
                "warning",
                obs_mc.CRM_APPLY_RETRYABLE,
                self._obs_corr(event, batch_id=batch_id),
                metrics={"attempt": attempt},
                details=summ,
                failure_domain=fd or "crm_apply",
                failure_type=ft or "retryable_item",
            )
            log_sync_event(
                "delivery_send",
                "info",
                obs_mc.DELIVERY_RETRY,
                self._obs_corr(event, batch_id=batch_id),
                details={"reason": "requeue_retryable_multi"},
            )
            _slog(
                logging.INFO,
                event="BATCH_ITEM_REQUEUED",
                store=event.data.source_name,
                entity_key=event.data.entity_key,
                event_id=event.event_id,
                event_type=event.event_type,
                payload_hash=event.data.payload_hash,
                http_status=res.http_status,
                status=res.status,
                retryable=True,
                attempt=attempt,
                error_code=res.error_code,
                error_message=res.error_message,
            )
            return

        self._coordinator.release_fingerprints([event])
        log_sync_event(
            "crm_apply",
            "warning",
            obs_mc.CRM_APPLY_REJECTED,
            self._obs_corr(event, batch_id=batch_id),
            metrics={"attempt": attempt},
            details=summ,
            failure_domain=fd or "crm_apply",
            failure_type=ft or "rejected_item",
        )
        _slog(
            logging.WARNING,
            event="BATCH_ITEM_REJECTED",
            store=event.data.source_name,
            entity_key=event.data.entity_key,
            event_id=event.event_id,
            event_type=event.event_type,
            payload_hash=event.data.payload_hash,
            http_status=res.http_status,
            status=res.status,
            retryable=res.retryable,
            attempt=attempt,
            error_code=res.error_code,
            error_message=res.error_message,
        )
