from __future__ import annotations

from domain.specs.base import BaseSpecs


class ApplianceSpecs(BaseSpecs):
    power_w: int | None = None
    volume_l: float | None = None
    energy_class: str | None = None
    color: str | None = None
    weight_kg: float | None = None
    warranty_months: int | None = None
