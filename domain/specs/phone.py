from __future__ import annotations

from domain.specs.base import BaseSpecs


class PhoneSpecs(BaseSpecs):
    display_size_inch: float | None = None
    display_resolution: str | None = None
    display_type: str | None = None
    ram_gb: int | None = None
    storage_gb: int | None = None
    battery_mah: int | None = None
    processor: str | None = None
    main_camera_mp: int | None = None
    front_camera_mp: int | None = None
    os: str | None = None
    sim_count: int | None = None
    nfc: bool | None = None
    weight_g: int | None = None
