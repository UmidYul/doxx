from __future__ import annotations

from domain.specs.base import BaseSpecs


class TVSpecs(BaseSpecs):
    display_size_inch: float | None = None
    resolution: str | None = None
    display_tech: str | None = None
    smart_tv: bool | None = None
    os: str | None = None
    hdmi_count: int | None = None
    refresh_rate_hz: int | None = None
    has_wifi: bool | None = None
    has_bluetooth: bool | None = None
