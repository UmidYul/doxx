from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from config.settings import settings
from domain.parser_event import ParserSyncEvent


@dataclass(frozen=True)
class _Queued:
    event: ParserSyncEvent
    enqueue_mono: float


class BatchCoordinator:
    """Ordered pending + retry queues with in-flight dedupe fingerprints."""

    def __init__(self) -> None:
        self._pending: deque[_Queued] = deque()
        self._retry: deque[_Queued] = deque()
        self._outstanding_fp: set[tuple[str, str]] = set()
        self._last_flush_mono: float = time.monotonic()
        self.requeue_count: int = 0
        self.last_batch_flush_ms: float | None = None
        self.last_batch_queue_wait_avg_ms: float | None = None
        self.last_items_per_flush: int = 0

    def _fp(self, event: ParserSyncEvent) -> tuple[str, str]:
        return (event.data.entity_key, event.data.payload_hash)

    def add_event(self, event: ParserSyncEvent) -> bool:
        """Return ``False`` if the same entity+payload is already queued or in-flight."""
        fp = self._fp(event)
        if fp in self._outstanding_fp:
            return False
        self._outstanding_fp.add(fp)
        self._pending.append(_Queued(event=event, enqueue_mono=time.monotonic()))
        return True

    def mark_flushed(self, *, now_mono: float | None = None) -> None:
        self._last_flush_mono = now_mono if now_mono is not None else time.monotonic()

    def should_flush(
        self,
        *,
        now_mono: float,
        interval_seconds: float,
        batch_size: int,
    ) -> bool:
        n = len(self._pending) + len(self._retry)
        if n == 0:
            return False
        if n >= batch_size:
            return True
        return (now_mono - self._last_flush_mono) >= interval_seconds

    def pending_len(self) -> int:
        return len(self._pending) + len(self._retry)

    def retry_queue_len(self) -> int:
        return len(self._retry)

    def pop_flush_batch(self) -> list[ParserSyncEvent]:
        """Pop up to ``CRM_BATCH_SIZE``, prioritizing retry queue (capped by max retryable slot)."""
        evs, _ = self.pop_flush_batch_with_waits()
        return evs

    def pop_flush_batch_with_waits(self) -> tuple[list[ParserSyncEvent], list[float]]:
        now = time.monotonic()
        out: list[ParserSyncEvent] = []
        waits: list[float] = []
        max_r = settings.CRM_BATCH_MAX_RETRYABLE_ITEMS_PER_FLUSH
        retry_used = 0
        while (
            len(out) < settings.CRM_BATCH_SIZE
            and self._retry
            and retry_used < max_r
        ):
            q = self._retry.popleft()
            waits.append(max(0.0, (now - q.enqueue_mono) * 1000.0))
            out.append(q.event)
            retry_used += 1
        while len(out) < settings.CRM_BATCH_SIZE and self._pending:
            q = self._pending.popleft()
            waits.append(max(0.0, (now - q.enqueue_mono) * 1000.0))
            out.append(q.event)
        return out, waits

    def requeue_retryable(self, events: list[ParserSyncEvent]) -> None:
        self.requeue_count += len(events)
        now = time.monotonic()
        for ev in events:
            self._retry.append(_Queued(event=ev, enqueue_mono=now))

    def release_fingerprints(self, events: list[ParserSyncEvent]) -> None:
        """Call when events reach a terminal state (success, rejected, or dropped)."""
        for ev in events:
            self._outstanding_fp.discard(self._fp(ev))

    def flush_remaining(self) -> list[ParserSyncEvent]:
        """Drain retry then pending (fingerprints stay until :meth:`release_fingerprints`)."""
        r = [q.event for q in list(self._retry) + list(self._pending)]
        self._retry.clear()
        self._pending.clear()
        return r

    def has_work(self) -> bool:
        return bool(self._pending or self._retry)
