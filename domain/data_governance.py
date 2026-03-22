from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DataSensitivity = Literal["public", "internal", "sensitive", "restricted"]

DataUsagePurpose = Literal[
    "crawl",
    "normalize",
    "delivery",
    "observability",
    "support",
    "replay",
]


class DataFieldPolicy(BaseModel):
    model_config = {"frozen": True}

    field_name: str
    sensitivity: DataSensitivity
    allowed_purposes: list[DataUsagePurpose] = Field(default_factory=list)
    loggable: bool = True
    exportable: bool = True
    redact_required: bool = False


class DataRetentionPolicy(BaseModel):
    model_config = {"frozen": True}

    artifact_name: str
    keep_in_memory: bool = True
    max_records: int | None = None
    max_age_seconds: int | None = None
    purpose: DataUsagePurpose = "observability"


class ReplayAbuseDecision(BaseModel):
    model_config = {"frozen": True}

    allowed: bool
    reason: str
    max_items: int = 0
    max_batches: int = 0
    safe_event_types: list[str] = Field(default_factory=list)


class DiagnosticScopeDecision(BaseModel):
    model_config = {"frozen": True}

    allowed: bool
    purpose: DataUsagePurpose
    included_sections: list[str] = Field(default_factory=list)
    excluded_fields: list[str] = Field(default_factory=list)
    reason: str | None = None
