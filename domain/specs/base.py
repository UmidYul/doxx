from __future__ import annotations

from pydantic import BaseModel, Field


class BaseSpecs(BaseModel):
    extraction_method: str = "unknown"
    completeness_score: float = 0.0
    raw_fields: dict = Field(default_factory=dict)

    def compute_score(self) -> float:
        excluded = frozenset({"extraction_method", "completeness_score", "raw_fields"})
        field_names = [name for name in self.model_fields if name not in excluded]
        if not field_names:
            self.completeness_score = 0.0
            return 0.0
        filled = sum(1 for name in field_names if getattr(self, name) is not None)
        ratio = filled / len(field_names)
        self.completeness_score = ratio
        return ratio

    model_config = {"from_attributes": True}
