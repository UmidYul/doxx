from __future__ import annotations

from datetime import UTC, datetime

from domain.observability import SyncCorrelationContext, SyncTraceRecord

from infrastructure.observability.health_policy import compute_parser_health
from infrastructure.observability.metrics_collector import BLOCK_PAGES_TOTAL, CRM_REJECTED_TOTAL


def _fail(**kwargs) -> SyncTraceRecord:
    base = dict(
        timestamp=datetime.now(UTC),
        stage="delivery_send",
        severity="error",
        message_code="X",
        correlation=SyncCorrelationContext(run_id="r", spider_name="s", store_name="st"),
    )
    base.update(kwargs)
    return SyncTraceRecord(**base)


def test_health_degraded_from_block_pages_and_rejections():
    c = {BLOCK_PAGES_TOTAL: 5.0, CRM_REJECTED_TOTAL: 12.0}
    fails = [_fail(severity="error") for _ in range(6)]
    assert compute_parser_health(c, fails) == "degraded"


def test_health_failing_on_critical_trace():
    c = {}
    fails = [_fail(severity="critical", message_code="CRM_APPLY_REJECTED")]
    assert compute_parser_health(c, fails) == "failing"
