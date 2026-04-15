from __future__ import annotations

from domain.resource_governance import StoreResourceBudget

_DEFAULT: StoreResourceBudget | None = None

_STORES: dict[str, StoreResourceBudget] = {}


def get_default_budget() -> StoreResourceBudget:
    """Conservative defaults for unknown stores."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = StoreResourceBudget(
            store_name="*",
            max_concurrent_requests=8,
            max_listing_requests=5,
            max_product_requests=6,
            max_batch_inflight=2,
            max_retryable_queue=80,
            max_browser_pages=1,
            max_proxy_requests=4,
            max_memory_mb=384,
            notes=["default_unknown_store_conservative"],
        )
    return _DEFAULT.model_copy(update={"store_name": "*"})


def _mediapark() -> StoreResourceBudget:
    return StoreResourceBudget(
        store_name="mediapark",
        max_concurrent_requests=14,
        max_listing_requests=8,
        max_product_requests=10,
        max_batch_inflight=3,
        max_retryable_queue=150,
        max_browser_pages=3,
        max_proxy_requests=8,
        max_memory_mb=480,
        notes=["plain_http_heavier_listing", "browser_fallback_needs_headroom"],
    )


def _uzum() -> StoreResourceBudget:
    return StoreResourceBudget(
        store_name="uzum",
        max_concurrent_requests=12,
        max_listing_requests=4,
        max_product_requests=12,
        max_batch_inflight=2,
        max_retryable_queue=80,
        max_browser_pages=3,
        max_proxy_requests=4,
        max_memory_mb=448,
        notes=["browser_listing_plain_pdp_mix", "homepage_graph_needs_more_http_headroom"],
    )


def _texnomart() -> StoreResourceBudget:
    return StoreResourceBudget(
        store_name="texnomart",
        max_concurrent_requests=20,
        max_listing_requests=4,
        max_product_requests=16,
        max_batch_inflight=3,
        max_retryable_queue=140,
        max_browser_pages=2,
        max_proxy_requests=4,
        max_memory_mb=448,
        notes=["sitemap_seeded_http_first", "higher_plain_product_budget"],
    )


def _alifshop() -> StoreResourceBudget:
    return StoreResourceBudget(
        store_name="alifshop",
        max_concurrent_requests=24,
        max_listing_requests=12,
        max_product_requests=20,
        max_batch_inflight=2,
        max_retryable_queue=120,
        max_browser_pages=0,
        max_proxy_requests=4,
        max_memory_mb=384,
        notes=["catalog_heavy_http_only", "higher_listing_fanout_budget"],
    )


def _load() -> None:
    global _STORES
    if _STORES:
        return
    _STORES = {
        "mediapark": _mediapark(),
        "uzum": _uzum(),
        "texnomart": _texnomart(),
        "alifshop": _alifshop(),
    }


def get_store_budget(store_name: str) -> StoreResourceBudget:
    """Return store-specific budget or a conservative clone of the default."""
    _load()
    key = (store_name or "").strip().lower()
    if key in _STORES:
        return _STORES[key].model_copy(update={"store_name": store_name.strip() or key})
    d = get_default_budget()
    return d.model_copy(update={"store_name": store_name.strip() or "unknown"})
