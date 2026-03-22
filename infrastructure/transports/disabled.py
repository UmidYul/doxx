from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.crm_apply_result import CrmApplyResult
from infrastructure.transports.base import BaseTransport

if TYPE_CHECKING:
    from domain.parser_event import ParserSyncEvent

logger = logging.getLogger(__name__)


class DisabledTransport(BaseTransport):
    """No-op transport for tests and local development."""

    async def send_one_event(self, event: ParserSyncEvent) -> CrmApplyResult:
        logger.debug("Transport disabled: skip sync entity_key=%s", event.data.entity_key)
        return CrmApplyResult(
            event_id=event.event_id,
            entity_key=event.data.entity_key,
            payload_hash=event.data.payload_hash,
            success=True,
            status="applied",
            http_status=200,
            action="disabled",
        )
