from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunbookAction = Literal[
    "continue",
    "retry_batch_once",
    "replay_product_found",
    "reconcile_ids",
    "downgrade_to_product_found",
    "disable_store_temporarily",
    "fail_run",
    "investigate_manually",
]

TriageDomain = Literal[
    "store_access",
    "crawl_quality",
    "normalization_quality",
    "delivery_transport",
    "crm_apply",
    "reconciliation",
    "internal",
]


class TriageSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    run_id: str
    store_name: str | None
    domain: TriageDomain
    severity: str
    suspected_root_cause: str
    evidence: list[dict[str, object]] = Field(default_factory=list)
    recommended_action: RunbookAction
    confidence: float = Field(ge=0.0, le=1.0)


class RunbookStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    step_order: int
    title: str
    instruction: str
    expected_outcome: str | None = None
    safe_action: bool = True


class RunbookPlan(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: TriageDomain
    severity: str
    steps: list[RunbookStep] = Field(default_factory=list)
    final_recommendation: RunbookAction


class ReplaySupportDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    allowed: bool
    action: RunbookAction
    reason: str
    safe_scope: Literal["single_item", "single_batch", "store_run", "none"]
