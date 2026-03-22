from __future__ import annotations

from config.settings import Settings
from infrastructure.security.outbound_policy import (
    classify_target_type,
    is_blocked_scheme,
    is_host_allowed,
    is_private_or_local_address,
    validate_outbound_url,
    validate_store_crawl_url,
)


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_allowed_store_host_passes() -> None:
    st = _s()
    d = validate_outbound_url("https://mediapark.uz/p/1", st)
    assert d.allowed and d.target_type == "store"


def test_unknown_host_blocked_in_restricted_mode() -> None:
    st = _s(NETWORK_SECURITY_MODE="restricted")
    d = validate_outbound_url("https://evil.example/phish", st)
    assert not d.allowed
    assert d.reason == "unknown_host_restricted_mode"


def test_unknown_host_allowed_in_open_mode() -> None:
    st = _s(NETWORK_SECURITY_MODE="open")
    d = validate_outbound_url("https://evil.example/ok", st)
    assert d.allowed and d.target_type == "unknown"


def test_localhost_blocked() -> None:
    st = _s()
    for u in ("http://localhost/x", "http://127.0.0.1/x", "http://0.0.0.0/x"):
        d = validate_outbound_url(u, st)
        assert not d.allowed
        assert d.reason == "localhost_blocked"


def test_private_ip_blocked() -> None:
    st = _s()
    d = validate_outbound_url("http://10.0.0.1/x", st)
    assert not d.allowed
    assert d.reason == "private_or_metadata_host"


def test_metadata_ip_blocked() -> None:
    st = _s()
    d = validate_outbound_url("http://169.254.169.254/latest/meta-data", st)
    assert not d.allowed


def test_unsafe_schemes_blocked() -> None:
    st = _s()
    for u in ("file:///etc/passwd", "javascript:alert(1)", "data:text/html,hi", "ftp://x/y"):
        assert is_blocked_scheme(u, st)


def test_http_https_allowed_scheme() -> None:
    st = _s()
    assert not is_blocked_scheme("https://mediapark.uz/", st)


def test_classify_crm_from_base_url() -> None:
    st = _s(CRM_BASE_URL="https://crm.internal/api", ALLOWED_CRM_HOSTS=[])
    assert classify_target_type("https://crm.internal/v1", st) == "crm"


def test_store_crawl_rejects_crm_host() -> None:
    st = _s(CRM_BASE_URL="https://crm.internal", NETWORK_SECURITY_MODE="open")
    d = validate_store_crawl_url("https://crm.internal/x", "mediapark", st)
    assert not d.allowed
    assert "store_crawl" in (d.reason or "")


def test_is_host_allowed_subdomain() -> None:
    assert is_host_allowed("m.mediapark.uz", ["mediapark.uz"])
    assert is_host_allowed("www.mediapark.uz", ["mediapark.uz"])


def test_is_private_or_local_for_hostname() -> None:
    st = _s()
    assert is_private_or_local_address("localhost", st)
    assert not is_private_or_local_address("mediapark.uz", st)
