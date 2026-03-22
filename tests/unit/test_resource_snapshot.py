from __future__ import annotations

from infrastructure.performance.resource_snapshot import build_resource_snapshot, get_process_memory_mb


def test_build_resource_snapshot_shape() -> None:
    snap = build_resource_snapshot()
    assert "process_memory_mb" in snap
    assert "limited_mode" in snap
    assert "platform" in snap


def test_get_process_memory_mb_no_crash() -> None:
    mb = get_process_memory_mb()
    assert mb is None or mb >= 0.0
