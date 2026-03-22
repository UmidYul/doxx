from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ContractSurface = Literal[
    "crm_payload",
    "lifecycle_event",
    "apply_result",
    "replay_metadata",
    "etl_status",
    "diagnostic_snapshot",
    "operator_summary",
]

ChangeType = Literal[
    "additive",
    "behavioral",
    "deprecation",
    "breaking",
]

CompatibilityLevel = Literal[
    "backward_compatible",
    "conditionally_compatible",
    "breaking",
]

DeprecationStatus = Literal[
    "active",
    "deprecated",
    "shadow",
    "removed",
]


class ContractChange(BaseModel):
    surface: ContractSurface
    change_name: str
    change_type: ChangeType
    compatibility_level: CompatibilityLevel
    affected_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompatibilityReport(BaseModel):
    surface: ContractSurface
    compatible: bool
    compatibility_level: CompatibilityLevel
    breaking_changes: list[ContractChange] = Field(default_factory=list)
    conditional_changes: list[ContractChange] = Field(default_factory=list)
    additive_changes: list[ContractChange] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MigrationPlan(BaseModel):
    surface: ContractSurface
    from_version: str
    to_version: str
    required_steps: list[str] = Field(default_factory=list)
    can_dual_write: bool = False
    can_shadow_mode: bool = False
    rollback_possible: bool = True
    notes: list[str] = Field(default_factory=list)


class DeprecationNotice(BaseModel):
    surface: ContractSurface
    field_name: str
    status: DeprecationStatus
    replacement_field: str | None = None
    deprecation_reason: str = ""
    removal_stage: str | None = None
