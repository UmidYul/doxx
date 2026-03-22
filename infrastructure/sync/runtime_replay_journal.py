from __future__ import annotations

from collections import OrderedDict

from config.settings import settings
from domain.crm_replay import ReconciliationResult


class RuntimeReplayJournal:
    """In-memory per-spider-run replay bookkeeping (no disk)."""

    def __init__(self) -> None:
        self._idempotency_attempts: OrderedDict[str, int] = OrderedDict()
        self._last_event_type_by_entity: OrderedDict[str, str] = OrderedDict()
        self._last_idempotency_by_entity: OrderedDict[str, str] = OrderedDict()
        self._last_reconciliation_by_entity: OrderedDict[str, ReconciliationResult] = OrderedDict()

    def remember_send_attempt(self, idempotency_key: str, event_type: str) -> None:
        k = (idempotency_key or "").strip()
        if not k:
            return
        self._idempotency_attempts[k] = self._idempotency_attempts.get(k, 0) + 1
        self._idempotency_attempts.move_to_end(k)
        self._trim_idempotency()

    def has_seen_idempotency_key(self, idempotency_key: str) -> bool:
        k = (idempotency_key or "").strip()
        if not k:
            return False
        return self._idempotency_attempts.get(k, 0) > 1

    def send_attempt_count(self, idempotency_key: str) -> int:
        k = (idempotency_key or "").strip()
        if not k:
            return 0
        return self._idempotency_attempts.get(k, 0)

    def remember_entity_meta(self, entity_key: str, event_type: str, idempotency_key: str) -> None:
        ek = (entity_key or "").strip()
        if not ek:
            return
        self._last_event_type_by_entity[ek] = event_type
        self._last_idempotency_by_entity[ek] = idempotency_key
        self._last_event_type_by_entity.move_to_end(ek)
        self._last_idempotency_by_entity.move_to_end(ek)
        self._trim_entity_maps()

    def remember_reconciliation(self, entity_key: str, result: ReconciliationResult) -> None:
        ek = (entity_key or "").strip()
        if not ek:
            return
        self._last_reconciliation_by_entity[ek] = result
        self._last_reconciliation_by_entity.move_to_end(ek)
        self._trim_entity_maps()

    def get_reconciliation(self, entity_key: str) -> ReconciliationResult | None:
        return self._last_reconciliation_by_entity.get(entity_key)

    def get_last_selected_event_type(self, entity_key: str) -> str | None:
        return self._last_event_type_by_entity.get(entity_key)

    def get_last_request_idempotency_key(self, entity_key: str) -> str | None:
        return self._last_idempotency_by_entity.get(entity_key)

    def _trim_idempotency(self) -> None:
        max_n = settings.SYNC_MAX_IN_MEMORY_CACHE
        if max_n <= 0 or len(self._idempotency_attempts) <= max_n:
            return
        while len(self._idempotency_attempts) > max_n:
            self._idempotency_attempts.popitem(last=False)

    def _trim_entity_maps(self) -> None:
        max_n = settings.SYNC_MAX_IN_MEMORY_CACHE
        if max_n <= 0:
            return
        while len(self._last_event_type_by_entity) > max_n:
            k, _ = self._last_event_type_by_entity.popitem(last=False)
            self._last_idempotency_by_entity.pop(k, None)
            self._last_reconciliation_by_entity.pop(k, None)
