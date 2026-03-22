from __future__ import annotations

from datetime import UTC, datetime

from domain.crm_lifecycle import CrmIdentityContext, LifecycleDecision, ParserLifecycleEvent

REQUIRED_LIFECYCLE_EVENT_KEYS = frozenset(
    {
        "event_id",
        "event_type",
        "sent_at",
        "identity",
        "payload_hash",
        "data",
        "request_idempotency_key",
        "replay_mode",
        "original_intent_event_type",
    }
)

REQUIRED_DECISION_KEYS = frozenset(
    {
        "selected_event_type",
        "allowed",
        "fallback_applied",
        "fallback_reason",
        "required_ids",
        "notes",
    }
)


def test_parser_lifecycle_event_shape():
    ident = CrmIdentityContext(
        entity_key="s:1",
        source_name="s",
        source_url="https://x",
    )
    ev = ParserLifecycleEvent(
        event_id="00000000-0000-4000-8000-000000000002",
        event_type="product_found",
        sent_at=datetime.now(UTC),
        identity=ident,
        payload_hash="sha256:" + "c" * 64,
        data={"entity_key": "s:1"},
    )
    d = ev.model_dump(mode="json")
    assert REQUIRED_LIFECYCLE_EVENT_KEYS <= set(d)


def test_lifecycle_decision_fixture_matches_contract():
    d = LifecycleDecision(
        selected_event_type="product_found",
        allowed=True,
        fallback_applied=False,
    ).model_dump(mode="json")
    assert REQUIRED_DECISION_KEYS <= set(d)
