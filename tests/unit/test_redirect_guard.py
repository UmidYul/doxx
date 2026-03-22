from __future__ import annotations

from config.settings import Settings
from infrastructure.security.redirect_guard import (
    can_follow_redirect,
    count_redirect_hops,
    validate_redirect_chain,
)


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_crm_redirect_to_external_host_blocked() -> None:
    st = _s(CRM_BASE_URL="http://crm.test", ALLOWED_CRM_HOSTS=[])
    d = can_follow_redirect("http://crm.test/a", "http://evil.com/b", st)
    assert not d.allowed
    # Target is rejected by outbound policy (restricted unknown) before CRM-specific rule.
    assert d.reason in ("unknown_host_restricted_mode", "crm_redirect_to_non_crm_host")


def test_store_mobile_redirect_to_allowed_subdomain_ok() -> None:
    st = _s()
    d = can_follow_redirect(
        "https://www.mediapark.uz/list",
        "https://m.mediapark.uz/list",
        st,
    )
    assert d.allowed


def test_store_redirect_to_unknown_blocked_in_restricted() -> None:
    st = _s(NETWORK_SECURITY_MODE="restricted")
    d = can_follow_redirect(
        "https://mediapark.uz/a",
        "https://evil.com/b",
        st,
    )
    assert not d.allowed


def test_redirect_chain_hop_limit() -> None:
    st = _s(MAX_REDIRECT_HOPS=2)
    urls = ["http://a/1", "http://a/2", "http://a/3", "http://a/4"]
    assert count_redirect_hops(urls) == 3
    out = validate_redirect_chain(urls, st)
    assert out and not out[0].allowed
    assert "too_many_redirects" in (out[0].reason or "")


def test_same_crm_host_redirect_allowed() -> None:
    st = _s(CRM_BASE_URL="http://crm.test", ALLOWED_CRM_HOSTS=[])
    d = can_follow_redirect("http://crm.test/old", "http://crm.test/new", st)
    assert d.allowed
