from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from domain.crm_lifecycle import CrmIdentityContext
from domain.crm_sync import CrmSyncItem
from domain.parser_event import ParserSyncEvent
from infrastructure.sync.batch_coordinator import BatchCoordinator


def _ev(ek: str = "s:1", ph: str = "h1") -> ParserSyncItem:
    return CrmSyncItem(
        schema_version=1,
        entity_key=ek,
        payload_hash=ph,
        source_name="s",
        source_id="1",
        external_ids={"s": "1"},
        source_url="https://x/1",
        title="t",
        price_value=1,
        price_raw="1",
        currency="UZS",
        in_stock=True,
        raw_specs={},
        image_urls=[],
        scraped_at=datetime(2026, 1, 1, tzinfo=UTC),
        sync_mode="snapshot",
    )


def _wrap(data: CrmSyncItem) -> ParserSyncEvent:
    ident = CrmIdentityContext(
        entity_key=data.entity_key,
        external_ids=dict(data.external_ids or {}),
        barcode=data.barcode,
        source_name=data.source_name,
        source_url=data.source_url,
        source_id=data.source_id,
    )
    return ParserSyncEvent(
        event_id=str(uuid.uuid4()),
        event_type="product_found",
        identity=ident,
        payload_hash=data.payload_hash,
        data=data,
    )


def test_add_event_rejects_duplicate_fingerprint() -> None:
    c = BatchCoordinator()
    d = _ev()
    e1 = _wrap(d)
    e2 = ParserSyncEvent(
        event_id=str(uuid.uuid4()),
        event_type=e1.event_type,
        sent_at=e1.sent_at,
        identity=e1.identity,
        payload_hash=e1.payload_hash,
        data=e1.data,
    )
    assert c.add_event(e1) is True
    assert c.add_event(e2) is False


def test_pop_prioritizes_retry_capped() -> None:
    with patch("infrastructure.sync.batch_coordinator.settings") as s:
        s.CRM_BATCH_SIZE = 2
        s.CRM_BATCH_MAX_RETRYABLE_ITEMS_PER_FLUSH = 1
        c = BatchCoordinator()
        e1 = _wrap(_ev("s:1", "h1"))
        e2 = _wrap(_ev("s:2", "h2"))
        e3 = _wrap(_ev("s:3", "h3"))
        assert c.add_event(e1)
        assert c.add_event(e2)
        assert c.add_event(e3)
        first = c.pop_flush_batch()
        assert first == [e1, e2]
        c.requeue_retryable([e1])
        second = c.pop_flush_batch()
        assert second[0] is e1
        assert e3 in second


def test_release_fingerprints_allows_re_add() -> None:
    c = BatchCoordinator()
    d = _ev()
    e = _wrap(d)
    assert c.add_event(e) is True
    c.release_fingerprints([e])
    assert c.add_event(e) is True


def test_flush_remaining_drains_queues() -> None:
    c = BatchCoordinator()
    e1 = _wrap(_ev("a:1", "h1"))
    e2 = _wrap(_ev("b:1", "h2"))
    c.add_event(e1)
    c.add_event(e2)
    rest = c.flush_remaining()
    assert len(rest) == 2
    assert not c.has_work()


def test_retry_queue_len_tracks_retry_buffer() -> None:
    with patch("infrastructure.sync.batch_coordinator.settings") as s:
        s.CRM_BATCH_SIZE = 10
        s.CRM_BATCH_MAX_RETRYABLE_ITEMS_PER_FLUSH = 5
        c = BatchCoordinator()
        assert c.retry_queue_len() == 0
        e1 = _wrap(_ev("a:1", "h1"))
        c.add_event(e1)
        c.requeue_retryable([e1])
        assert c.retry_queue_len() == 1
