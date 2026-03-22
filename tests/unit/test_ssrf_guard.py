from __future__ import annotations

from config.settings import Settings
from infrastructure.security.ssrf_guard import (
    normalize_and_validate_url,
    reject_if_internal_target,
    reject_if_suspicious_url,
)


def _s(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_reject_protocol_relative() -> None:
    assert reject_if_suspicious_url("//evil.com//path")


def test_reject_embedded_credentials() -> None:
    assert reject_if_suspicious_url("https://user:pass@mediapark.uz/")


def test_reject_null_byte() -> None:
    assert reject_if_suspicious_url("https://mediapark.uz/%00")


def test_normal_https_not_suspicious() -> None:
    assert not reject_if_suspicious_url("https://mediapark.uz/path//segment")


def test_reject_internal_target() -> None:
    st = _s()
    assert reject_if_internal_target("http://127.0.0.1:8080", st)


def test_normalize_and_validate_rejects_control_chars() -> None:
    st = _s()
    d = normalize_and_validate_url("https://mediapark.uz/\x01bad", st)
    assert not d.allowed
