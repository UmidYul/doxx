from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult

if TYPE_CHECKING:
    from domain.parser_event import ParserSyncEvent


class BaseTransport(ABC):
    """Abstract transport for parser sync events."""

    @abstractmethod
    async def send_one_event(self, event: ParserSyncEvent) -> CrmApplyResult:
        """Send one :class:`ParserSyncEvent`; returns item-level apply semantics."""

    async def send_batch_events(self, events: list[ParserSyncEvent]) -> CrmBatchApplyResult:
        """Send a batch; default builds a :class:`CrmBatchApplyResult` from per-item sends."""
        items = [await self.send_one_event(e) for e in events]
        transport_ok = all(i.success for i in items) if items else True
        last_http = items[-1].http_status if items else None
        return CrmBatchApplyResult(
            items=items,
            transport_ok=transport_ok,
            http_status=last_http,
        )

    async def close(self) -> None:
        """Release resources."""

    def attach_metrics(self, collector: object | None) -> None:
        """Optional hook for delivery metrics (e.g. CRM HTTP retries)."""
        return
