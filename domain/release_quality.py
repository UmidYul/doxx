from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReleaseAction = Literal["release", "release_with_caution", "block_release"]

CheckCategory = Literal[
    "unit",
    "contract",
    "acceptance",
    "integration_like",
    "regression",
    "compatibility",
]

GateSeverity = Literal["info", "warning", "high", "critical"]


class QualityGateResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    gate_name: str
    passed: bool
    severity: GateSeverity
    details: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)


class ReleaseCheckResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    check_name: str
    passed: bool
    category: CheckCategory
    notes: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class ReleaseReadinessSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    overall_passed: bool
    critical_failures: int = 0
    warnings: int = 0
    checks: list[ReleaseCheckResult] = Field(default_factory=list)
    gates: list[QualityGateResult] = Field(default_factory=list)
    recommended_action: ReleaseAction = "release"
