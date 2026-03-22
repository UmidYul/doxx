from __future__ import annotations

from application.readiness.readiness_registry import (
    get_default_readiness_checklist,
    get_domain_checklist,
    get_required_items_only,
)


def test_default_checklist_covers_all_domains() -> None:
    items = get_default_readiness_checklist()
    domains = {i.domain for i in items}
    assert "crawl" in domains
    assert "documentation" in domains
    assert "security" in domains
    assert len(items) >= 30


def test_get_required_items_subset() -> None:
    req = get_required_items_only()
    assert all(i.required for i in req)
    assert len(req) == len(get_default_readiness_checklist())


def test_get_domain_checklist_filter() -> None:
    c = get_domain_checklist("crawl")
    assert c and all(i.domain == "crawl" for i in c)
