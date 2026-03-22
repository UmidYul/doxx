from __future__ import annotations

from infrastructure.security.data_policy_registry import FIELD_POLICIES, get_field_policy


def test_known_sensitive_fields_not_loggable_or_restricted() -> None:
    h = get_field_policy("headers")
    assert h is not None
    assert h.loggable is False
    p = get_field_policy("parser_key")
    assert p is not None
    assert p.redact_required is True


def test_source_url_policy() -> None:
    s = get_field_policy("source_url")
    assert s is not None
    assert s.sensitivity == "sensitive"
    assert "observability" in s.allowed_purposes


def test_registry_covers_listed_fields() -> None:
    for name in (
        "entity_key",
        "payload_hash",
        "raw_specs",
        "typed_specs",
        "field_confidence",
        "image_urls",
        "proxy_url",
    ):
        assert name in FIELD_POLICIES
