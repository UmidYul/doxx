from __future__ import annotations

from domain.crm_replay import ReconciliationResult
from infrastructure.sync.runtime_replay_journal import RuntimeReplayJournal


def test_send_attempt_count_and_seen() -> None:
    j = RuntimeReplayJournal()
    j.remember_send_attempt("k1", "product_found")
    assert j.send_attempt_count("k1") == 1
    assert j.has_seen_idempotency_key("k1") is False
    j.remember_send_attempt("k1", "product_found")
    assert j.send_attempt_count("k1") == 2
    assert j.has_seen_idempotency_key("k1") is True


def test_entity_meta_and_reconciliation() -> None:
    j = RuntimeReplayJournal()
    j.remember_entity_meta("e:1", "product_found", "key-a")
    assert j.get_last_request_idempotency_key("e:1") == "key-a"
    r = ReconciliationResult(resolved=True, crm_listing_id="L1", source="runtime")
    j.remember_reconciliation("e:1", r)
    assert j.get_reconciliation("e:1") == r
