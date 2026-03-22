from __future__ import annotations

from config.store_resource_budgets import get_default_budget, get_store_budget


def test_get_default_budget_is_conservative() -> None:
    d = get_default_budget()
    assert d.store_name == "*"
    assert d.max_concurrent_requests <= 8
    assert d.max_browser_pages <= 1
    assert d.max_batch_inflight <= 2


def test_mediapark_higher_http_concurrency_than_uzum() -> None:
    mp = get_store_budget("mediapark")
    uz = get_store_budget("uzum")
    assert mp.max_concurrent_requests > uz.max_concurrent_requests
    assert mp.max_browser_pages <= uz.max_browser_pages


def test_unknown_store_gets_conservative_clone() -> None:
    u = get_store_budget("unknown_store_xyz")
    d = get_default_budget()
    assert u.max_concurrent_requests == d.max_concurrent_requests
    assert u.store_name == "unknown_store_xyz"
