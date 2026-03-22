from __future__ import annotations

from config.settings import Settings
from infrastructure.security.proxy_security import (
    mask_proxy_url,
    should_allow_proxy_for_target,
    validate_proxy_url,
)


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_mask_proxy_url_strips_credentials() -> None:
    m = mask_proxy_url("http://user:secret@8.8.8.8:8888")
    assert "secret" not in m
    assert "user" not in m
    assert "*:*" in m or "8.8.8.8" in m


def test_validate_proxy_rejects_private_host() -> None:
    st = _s()
    d = validate_proxy_url("http://127.0.0.1:8888", st)
    assert not d.allowed


def test_validate_proxy_allows_public_when_allowlist_empty() -> None:
    st = _s(ALLOWED_PROXY_HOSTS=[])
    d = validate_proxy_url("http://8.8.8.8:9000", st)
    assert d.allowed
    assert d.proxy_url_masked


def test_proxy_allowlist_enforced() -> None:
    st = _s(ALLOWED_PROXY_HOSTS=["proxy.example.org"])
    assert validate_proxy_url("http://proxy.example.org:8080", st).allowed
    assert not validate_proxy_url("http://other.org:8080", st).allowed


def test_should_allow_proxy_for_target_rejects_crm_url() -> None:
    st = _s(CRM_BASE_URL="http://crm.test")
    ok = should_allow_proxy_for_target(
        "http://8.8.8.8:1",
        "http://crm.test/api",
        st,
    )
    assert not ok
