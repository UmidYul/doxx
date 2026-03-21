from __future__ import annotations

from domain.specs.base import BaseSpecs


class LaptopSpecs(BaseSpecs):
    display_size_inch: float | None = None
    processor: str | None = None
    ram_gb: int | None = None
    storage_gb: int | None = None
    storage_type: str | None = None
    gpu: str | None = None
    os: str | None = None
    battery_wh: float | None = None
    weight_kg: float | None = None
    hdmi: bool | None = None
    usb_c_count: int | None = None
