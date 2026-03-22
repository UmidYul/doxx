from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class TypedPartialSpecs(BaseModel):
    """Partial typed extraction layer; does not replace :attr:`raw_specs` on the product."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ram_gb: int | None = None
    storage_gb: int | None = None
    display_size_inch: float | None = None
    display_resolution: str | None = None
    display_type: str | None = None
    display_tech: str | None = None
    refresh_rate_hz: int | None = None
    processor: str | None = None
    gpu: str | None = None
    battery_mah: int | None = None
    battery_wh: float | None = None
    weight_g: int | None = None
    weight_kg: float | None = None
    color: str | None = None
    sim_count: int | None = None
    main_camera_mp: int | None = None
    front_camera_mp: int | None = None
    volume_l: float | None = None
    power_w: int | None = None
    smart_tv: bool | None = None
    has_wifi: bool | None = None
    has_bluetooth: bool | None = None
    hdmi: bool | None = None
    hdmi_count: int | None = None
    usb_c_count: int | None = None
    os: str | None = None
    energy_class: str | None = None
    warranty_months: int | None = None

    def to_compact_dict(self) -> dict[str, Any]:
        """Return only fields that are not ``None`` (JSON-friendly)."""
        return {k: v for k, v in self.model_dump(mode="json").items() if v is not None}
