from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


def status_bucket_for_http(status: int) -> str | None:
    """Map HTTP status to anti-ban monitoring bucket."""
    s = int(status)
    if s == 403:
        return "403"
    if s == 429:
        return "429"
    if 500 <= s <= 599:
        return "5xx"
    return None


class BanSignalSpikeMonitor:
    """In-memory spike detector for status buckets per store/domain."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)
        self._armed: dict[tuple[str, str, str], bool] = defaultdict(lambda: True)

    def record_http_status(
        self,
        *,
        store: str,
        domain: str,
        status_bucket: str,
        threshold: int,
        window_seconds: float,
        now_monotonic: float | None = None,
    ) -> tuple[bool, int]:
        """Record bucket event and return ``(spike_triggered, count_in_window)``."""
        st = (store or "unknown").strip().lower() or "unknown"
        dm = (domain or "unknown").strip().lower() or "unknown"
        bucket = (status_bucket or "").strip().lower()
        if not bucket:
            return False, 0
        th = max(1, int(threshold))
        win = max(1.0, float(window_seconds))
        now = float(now_monotonic if now_monotonic is not None else time.monotonic())
        cutoff = now - win
        key = (st, dm, bucket)

        with self._lock:
            q = self._events[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) < th:
                self._armed[key] = True
            q.append(now)
            count = len(q)
            if count >= th and self._armed.get(key, True):
                self._armed[key] = False
                return True, count
            return False, count

    def reset(self) -> None:
        """Clear monitor state (unit tests / local diagnostics)."""
        with self._lock:
            self._events.clear()
            self._armed.clear()


ban_signal_spike_monitor = BanSignalSpikeMonitor()
