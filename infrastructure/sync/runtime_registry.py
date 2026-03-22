from __future__ import annotations

from collections import OrderedDict

from config.settings import settings


class RuntimeSyncRegistry:
    """In-memory dedupe and CRM id hints for a single spider process (no disk/DB)."""

    def __init__(self) -> None:
        self._payload_hashes_by_entity_key: OrderedDict[str, str] = OrderedDict()
        self._sent_pairs: OrderedDict[tuple[str, str], bool] = OrderedDict()
        self._crm_ids_by_entity_key: OrderedDict[str, tuple[str | None, str | None]] = OrderedDict()
        self._actions_by_entity_key: OrderedDict[str, str | None] = OrderedDict()

    def should_skip(self, entity_key: str, payload_hash: str) -> bool:
        if not settings.SYNC_DEDUPE_IN_MEMORY:
            return False
        return (entity_key, payload_hash) in self._sent_pairs

    def remember_payload(self, entity_key: str, payload_hash: str) -> None:
        """Record a successfully delivered (entity_key, payload_hash) pair."""
        pair = (entity_key, payload_hash)
        if pair in self._sent_pairs:
            self._sent_pairs.move_to_end(pair)
        else:
            self._sent_pairs[pair] = True
        self._payload_hashes_by_entity_key[entity_key] = payload_hash
        self._payload_hashes_by_entity_key.move_to_end(entity_key)
        self.trim_if_needed()

    def remember_crm_ids(
        self,
        entity_key: str,
        crm_listing_id: str | None,
        crm_product_id: str | None,
        action: str | None,
    ) -> None:
        self._crm_ids_by_entity_key[entity_key] = (crm_listing_id, crm_product_id)
        self._crm_ids_by_entity_key.move_to_end(entity_key)
        self._actions_by_entity_key[entity_key] = action
        self._actions_by_entity_key.move_to_end(entity_key)
        self.trim_if_needed()

    def get_crm_ids(self, entity_key: str) -> tuple[str | None, str | None]:
        return self._crm_ids_by_entity_key.get(entity_key, (None, None))

    def trim_if_needed(self) -> None:
        max_n = settings.SYNC_MAX_IN_MEMORY_CACHE
        if max_n <= 0:
            return
        while len(self._sent_pairs) > max_n:
            self._sent_pairs.popitem(last=False)
        while len(self._crm_ids_by_entity_key) > max_n:
            k, _ = self._crm_ids_by_entity_key.popitem(last=False)
            self._actions_by_entity_key.pop(k, None)
        while len(self._payload_hashes_by_entity_key) > max_n:
            self._payload_hashes_by_entity_key.popitem(last=False)
