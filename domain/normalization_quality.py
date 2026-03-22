from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None and v != []}


class FieldConfidence(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    field_name: str
    confidence: float
    source_labels: list[str] = Field(default_factory=list)
    source_values: list[str] = Field(default_factory=list)
    resolution_reason: str | None = None
    warning_codes: list[str] = Field(default_factory=list)

    def to_compact_dict(self) -> dict[str, Any]:
        return _compact(self.model_dump(mode="json"))


class SuppressedTypedField(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    field_name: str
    raw_values: list[str] = Field(default_factory=list)
    reason_code: str
    details: str | None = None

    def to_compact_dict(self) -> dict[str, Any]:
        return _compact(self.model_dump(mode="json"))


class NormalizationQualitySummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mapping_ratio: float | None = None
    confident_fields_count: int = 0
    low_confidence_fields_count: int = 0
    suppressed_fields_count: int = 0
    conflict_count: int = 0
    warning_count: int = 0

    def to_compact_dict(self) -> dict[str, Any]:
        return _compact(self.model_dump(mode="json"))
