from __future__ import annotations

import threading
from collections import defaultdict

from config.settings import settings
from domain.resource_governance import RuntimeResourceState
from infrastructure.performance.resource_snapshot import get_process_memory_mb

_lock = threading.Lock()

# Per-store counters (non-negative).
_inflight_total: dict[str, int] = defaultdict(int)
_inflight_listing: dict[str, int] = defaultdict(int)
_inflight_product: dict[str, int] = defaultdict(int)
_inflight_batches: dict[str, int] = defaultdict(int)
_retryable_queue: dict[str, int] = defaultdict(int)
_browser_pages: dict[str, int] = defaultdict(int)
_proxy_requests: dict[str, int] = defaultdict(int)


def reset_resource_tracker_for_tests() -> None:
    global _inflight_total, _inflight_listing, _inflight_product, _inflight_batches
    global _retryable_queue, _browser_pages, _proxy_requests
    with _lock:
        _inflight_total.clear()
        _inflight_listing.clear()
        _inflight_product.clear()
        _inflight_batches.clear()
        _retryable_queue.clear()
        _browser_pages.clear()
        _proxy_requests.clear()


def _clamp(n: int) -> int:
    return max(0, int(n))


def increment_inflight_request(store_name: str, purpose: str) -> None:
    """Count a request as in-flight (call when a request is scheduled)."""
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _inflight_total[st] += 1
        p = (purpose or "").lower()
        if p == "listing" or p == "api":
            _inflight_listing[st] += 1
        elif p == "product":
            _inflight_product[st] += 1
        else:
            _inflight_listing[st] += 1


def decrement_inflight_request(store_name: str, purpose: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _inflight_total[st] = _clamp(_inflight_total[st] - 1)
        p = (purpose or "").lower()
        if p == "listing" or p == "api":
            _inflight_listing[st] = _clamp(_inflight_listing[st] - 1)
        elif p == "product":
            _inflight_product[st] = _clamp(_inflight_product[st] - 1)
        else:
            _inflight_listing[st] = _clamp(_inflight_listing[st] - 1)


def increment_inflight_batch(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _inflight_batches[st] += 1


def decrement_inflight_batch(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _inflight_batches[st] = _clamp(_inflight_batches[st] - 1)


def increment_browser_pages(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _browser_pages[st] += 1


def decrement_browser_pages(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _browser_pages[st] = _clamp(_browser_pages[st] - 1)


def increment_proxy_requests(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _proxy_requests[st] += 1


def decrement_proxy_requests(store_name: str) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _proxy_requests[st] = _clamp(_proxy_requests[st] - 1)


def set_retryable_queue_size(store_name: str, size: int) -> None:
    if not getattr(settings, "ENABLE_RESOURCE_GOVERNANCE", True):
        return
    st = (store_name or "").strip() or "unknown"
    with _lock:
        _retryable_queue[st] = max(0, int(size))


def get_global_inflight_requests_total() -> int:
    with _lock:
        return int(sum(_inflight_total.values()))


def get_global_browser_pages_total() -> int:
    with _lock:
        return int(sum(_browser_pages.values()))


def get_global_proxy_requests_total() -> int:
    with _lock:
        return int(sum(_proxy_requests.values()))


def get_global_inflight_batches_total() -> int:
    with _lock:
        return int(sum(_inflight_batches.values()))


def build_runtime_state(store_name: str) -> RuntimeResourceState:
    st = (store_name or "").strip() or "unknown"
    mem = get_process_memory_mb() if getattr(settings, "ENABLE_MEMORY_GUARD", True) else None
    with _lock:
        return RuntimeResourceState(
            store_name=st,
            inflight_requests=_inflight_total.get(st, 0),
            inflight_listing_requests=_inflight_listing.get(st, 0),
            inflight_product_requests=_inflight_product.get(st, 0),
            inflight_batches=_inflight_batches.get(st, 0),
            queued_retryable_items=_retryable_queue.get(st, 0),
            active_browser_pages=_browser_pages.get(st, 0),
            active_proxy_requests=_proxy_requests.get(st, 0),
            memory_mb=mem,
        )
