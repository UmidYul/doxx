from __future__ import annotations

from collections import OrderedDict

from config.settings import settings
from domain.crm_apply_result import CrmApplyResult


def _should_update_crm_ids_from_result(result: CrmApplyResult) -> bool:
    if not result.success:
        return False
    if result.status == "ignored" and not settings.PARSER_MARK_IGNORED_AS_APPLIED:
        return False
    return result.status in ("applied", "matched", "created", "updated", "ignored")


def _should_mark_payload_applied(result: CrmApplyResult) -> bool:
    if not result.success:
        return False
    if result.status == "ignored":
        return settings.PARSER_MARK_IGNORED_AS_APPLIED
    return True


class RuntimeIdentityBridge:
    """In-run memory map entity_key → CRM ids + last successful payload (no disk/DB)."""

    def __init__(self) -> None:
        self._rows: OrderedDict[str, dict[str, object | None]] = OrderedDict()

    def remember_apply_result(self, result: CrmApplyResult) -> None:
        ek = result.entity_key
        prev = dict(self._rows.get(ek) or {})
        if _should_update_crm_ids_from_result(result):
            listing = result.crm_listing_id or prev.get("crm_listing_id")
            product = result.crm_product_id or prev.get("crm_product_id")
            prev["crm_listing_id"] = listing
            prev["crm_product_id"] = product
            prev["last_action"] = result.action or prev.get("last_action")
        if _should_mark_payload_applied(result):
            prev["last_successful_payload_hash"] = result.payload_hash
        self._rows[ek] = prev
        self._rows.move_to_end(ek)
        self._trim()

    def remember_sync_result(
        self,
        entity_key: str,
        crm_listing_id: str | None,
        crm_product_id: str | None,
        action: str | None,
        payload_hash: str,
    ) -> None:
        """Legacy helper — treated as a successful apply."""
        self.remember_apply_result(
            CrmApplyResult(
                event_id="",
                entity_key=entity_key,
                payload_hash=payload_hash,
                success=True,
                status="applied",
                http_status=200,
                action=action,
                crm_listing_id=crm_listing_id,
                crm_product_id=crm_product_id,
            )
        )

    def remember_sent_payload(self, entity_key: str, payload_hash: str) -> None:
        prev = dict(self._rows.get(entity_key) or {})
        prev["last_successful_payload_hash"] = payload_hash
        self._rows[entity_key] = prev
        self._rows.move_to_end(entity_key)
        self._trim()

    def should_skip_event(self, entity_key: str, payload_hash: str) -> bool:
        if not settings.CRM_RUNTIME_SKIP_SAME_ENTITY_SAME_PAYLOAD:
            return False
        return self.get_last_successful_payload(entity_key) == payload_hash

    def get_runtime_ids(self, entity_key: str) -> dict[str, str | None]:
        row = self._rows.get(entity_key) or {}
        return {
            "crm_listing_id": self._as_str_or_none(row.get("crm_listing_id")),
            "crm_product_id": self._as_str_or_none(row.get("crm_product_id")),
        }

    @staticmethod
    def _as_str_or_none(v: object | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def has_listing_id(self, entity_key: str) -> bool:
        return bool(self.get_runtime_ids(entity_key).get("crm_listing_id"))

    def has_product_id(self, entity_key: str) -> bool:
        return bool(self.get_runtime_ids(entity_key).get("crm_product_id"))

    def get_last_successful_payload(self, entity_key: str) -> str | None:
        row = self._rows.get(entity_key) or {}
        v = row.get("last_successful_payload_hash")
        return str(v) if v is not None else None

    def get_last_payload_hash(self, entity_key: str) -> str | None:
        """Alias for :meth:`get_last_successful_payload`."""
        return self.get_last_successful_payload(entity_key)

    def get_last_action(self, entity_key: str) -> str | None:
        row = self._rows.get(entity_key) or {}
        v = row.get("last_action")
        return str(v) if v is not None else None

    def _trim(self) -> None:
        max_n = settings.SYNC_MAX_IN_MEMORY_CACHE
        if max_n <= 0:
            return
        while len(self._rows) > max_n:
            self._rows.popitem(last=False)
