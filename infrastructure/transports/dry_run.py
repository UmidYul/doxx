from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.crm_apply_result import CrmApplyResult
from infrastructure.observability import message_codes as dx_mc
from infrastructure.observability.event_logger import log_developer_experience_event
from infrastructure.security.redaction import redact_mapping_for_logs
from infrastructure.transports.base import BaseTransport

if TYPE_CHECKING:
    from domain.parser_event import ParserSyncEvent

logger = logging.getLogger(__name__)


class DryRunTransport(BaseTransport):
    """Skips real CRM HTTP while keeping pipeline semantics (9B)."""

    async def send_one_event(self, event: ParserSyncEvent) -> CrmApplyResult:
        safe = redact_mapping_for_logs(
            {
                "entity_key": event.data.entity_key,
                "event_type": event.event_type,
                "payload_hash": event.data.payload_hash,
            }
        )
        logger.info("dry_run: would send event entity_key=%s", event.data.entity_key)
        log_developer_experience_event(
            dx_mc.DEV_DRY_RUN_ACTIVE,
            dev_run_mode="dry_run",
            store_name=event.data.source_name,
            dry_run=True,
            items_count=1,
            pass_ok=True,
            details={"preview": safe},
        )
        return CrmApplyResult(
            event_id=event.event_id,
            entity_key=event.data.entity_key,
            payload_hash=event.data.payload_hash,
            success=True,
            status="applied",
            http_status=200,
            action="dry_run",
        )
