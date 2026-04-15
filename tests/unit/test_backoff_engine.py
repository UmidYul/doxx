from __future__ import annotations

from infrastructure.access.backoff_engine import ExplicitBackoffEngine


def test_parse_rate_limit_headers_extracts_retry_after_and_reset() -> None:
    engine = ExplicitBackoffEngine(base_seconds=1.0, max_seconds=90.0, cooldown_max_seconds=300.0)
    snapshot = engine.parse_headers(
        {
            b"Retry-After": b"12",
            b"X-RateLimit-Remaining": b"0",
            b"X-RateLimit-Reset": b"1700000010",
            b"X-RateLimit-Limit": b"100",
        },
        now_epoch=1700000000.0,
    )

    assert snapshot.limit == 100
    assert snapshot.remaining == 0
    assert snapshot.retry_after_seconds == 12.0
    assert snapshot.reset_wait_seconds == 10.0
    assert snapshot.has_hints is True


def test_classify_429_prefers_retry_after_hint() -> None:
    engine = ExplicitBackoffEngine(base_seconds=1.0, max_seconds=90.0, cooldown_max_seconds=300.0)
    snapshot = engine.parse_headers({b"Retry-After": b"7"}, now_epoch=1700000000.0)

    decision = engine.classify(
        status=429,
        prior_failures=0,
        headers_snapshot=snapshot,
    )

    assert decision.retry_allowed is True
    assert decision.reason == "http_429_retry_after"
    assert decision.wait_seconds == 7.0
    assert decision.cooldown_seconds == 7.0
    assert decision.actions == ("domain_cooldown",)


def test_classify_403_is_non_retryable_with_rotation_actions() -> None:
    engine = ExplicitBackoffEngine(base_seconds=1.0, max_seconds=90.0, cooldown_max_seconds=300.0)
    decision = engine.classify(status=403, prior_failures=1)

    assert decision.retry_allowed is False
    assert decision.reason == "http_403_forbidden"
    assert decision.actions == ("rotate_proxy", "rotate_session")
    assert decision.cooldown_seconds >= 5.0


def test_classify_503_keeps_exponential_wait() -> None:
    engine = ExplicitBackoffEngine(base_seconds=1.0, max_seconds=90.0, cooldown_max_seconds=300.0)
    decision = engine.classify(status=503, prior_failures=2)

    assert decision.retry_allowed is True
    assert decision.reason == "http_503_upstream_error"
    assert decision.wait_seconds == 4.0
    assert decision.cooldown_seconds == 4.0
