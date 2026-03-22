from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SyncMetricsCollector:
    """In-process counters for sync delivery (no Prometheus in 1C — hook for later)."""

    items_seen_total: int = 0
    items_deduped_total: int = 0
    items_sent_total: int = 0
    items_synced_total: int = 0
    items_failed_total: int = 0
    batch_requests_total: int = 0
    batch_partial_failures_total: int = 0
    transport_retries_total: int = 0
    # --- 4B batch / apply ---
    batch_flushes_total: int = 0
    batch_items_total: int = 0
    batch_items_applied_total: int = 0
    batch_items_rejected_total: int = 0
    batch_items_retryable_total: int = 0
    batch_items_requeued_total: int = 0
    batch_transport_failures_total: int = 0
    malformed_batch_responses_total: int = 0
    duplicate_payload_skips_total: int = 0
    runtime_id_updates_total: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "items_seen_total": self.items_seen_total,
            "items_deduped_total": self.items_deduped_total,
            "items_sent_total": self.items_sent_total,
            "items_synced_total": self.items_synced_total,
            "items_failed_total": self.items_failed_total,
            "batch_requests_total": self.batch_requests_total,
            "batch_partial_failures_total": self.batch_partial_failures_total,
            "transport_retries_total": self.transport_retries_total,
            "batch_flushes_total": self.batch_flushes_total,
            "batch_items_total": self.batch_items_total,
            "batch_items_applied_total": self.batch_items_applied_total,
            "batch_items_rejected_total": self.batch_items_rejected_total,
            "batch_items_retryable_total": self.batch_items_retryable_total,
            "batch_items_requeued_total": self.batch_items_requeued_total,
            "batch_transport_failures_total": self.batch_transport_failures_total,
            "malformed_batch_responses_total": self.malformed_batch_responses_total,
            "duplicate_payload_skips_total": self.duplicate_payload_skips_total,
            "runtime_id_updates_total": self.runtime_id_updates_total,
        }

    def log_summary(self) -> None:
        d = {k: v for k, v in self.to_dict().items() if not k.startswith(".")}
        logger.info("sync_metrics_summary %s", d)


# Optional global hook for tests / future Prometheus adapter
_metrics_hooks: list = []


def register_metrics_hook(fn) -> None:
    _metrics_hooks.append(fn)


def emit_metrics_snapshot(collector: SyncMetricsCollector) -> None:
    for fn in _metrics_hooks:
        try:
            fn(collector)
        except Exception:
            logger.exception("metrics hook failed")
