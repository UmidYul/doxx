from __future__ import annotations

from infrastructure.security.redaction import minimize_url_for_support, redact_url


def test_minimize_url_strips_query_by_default() -> None:
    u = "https://shop.example/path?token=secret&page=1"
    m = minimize_url_for_support(u, full_query_allowed=False)
    assert "token" not in m
    assert "?" not in m or m.endswith("/path")


def test_full_query_allowed_uses_redact() -> None:
    u = "https://x/y?token=abc&ok=1"
    m = minimize_url_for_support(u, full_query_allowed=True)
    assert "ok=1" in m
    assert "abc" not in m or "[REDACTED]" in m


def test_redact_url_still_redacts_sensitive_params() -> None:
    u = "https://x/y?token=secret"
    r = redact_url(u)
    assert "REDACTED" in r
