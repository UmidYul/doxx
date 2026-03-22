from __future__ import annotations

import uuid

from domain.observability import SyncCorrelationContext


def build_run_id(spider_name: str) -> str:
    """Unique id for one spider process run (not deterministic across runs)."""
    return f"{spider_name}:{uuid.uuid4().hex}"


def build_batch_id(run_id: str, seq: int) -> str:
    """Deterministic batch id for a flush within a run."""
    return f"{run_id}:batch:{int(seq)}"


def build_correlation_context(
    spider_name: str,
    store_name: str,
    *,
    run_id: str | None = None,
    category_url: str | None = None,
    source_url: str | None = None,
    source_id: str | None = None,
    entity_key: str | None = None,
    event_id: str | None = None,
    payload_hash: str | None = None,
    request_idempotency_key: str | None = None,
    batch_id: str | None = None,
) -> SyncCorrelationContext:
    """Build correlation context for end-to-end tracing (crawl → CRM apply)."""
    from infrastructure.observability.trace_collector import get_trace_collector

    rid = run_id or get_trace_collector().current_run_id
    return SyncCorrelationContext(
        run_id=rid,
        spider_name=spider_name,
        store_name=store_name,
        category_url=category_url,
        source_url=source_url,
        source_id=source_id,
        entity_key=entity_key,
        event_id=event_id,
        payload_hash=payload_hash,
        request_idempotency_key=request_idempotency_key,
        batch_id=batch_id,
    )
