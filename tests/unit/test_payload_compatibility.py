from __future__ import annotations

from application.release.payload_compatibility import (
    compare_lifecycle_shapes,
    compare_observability_shapes,
    compare_payload_shapes,
)


def test_breaking_payload_field_removal_blocks():
    baseline = {"a": 1, "b": {"c": 2}}
    current = {"a": 1, "b": {}}
    r = compare_payload_shapes(current, baseline)
    assert r.passed is False
    assert any("missing_required" in n for n in r.notes)


def test_optional_field_addition_does_not_block():
    baseline = {"schema": "v3", "run_id": "x"}
    current = {"schema": "v3", "run_id": "x", "extra_new_field": [1, 2]}
    r = compare_observability_shapes(current, baseline)
    assert r.passed is True


def test_lifecycle_default_event_field_required():
    baseline = {"event_type": "product_found", "replay_mode": "snapshot_upsert"}
    current = {"replay_mode": "snapshot_upsert"}
    r = compare_lifecycle_shapes(current, baseline)
    assert r.passed is False


def test_type_drift_detected():
    baseline = {"n": 1}
    current = {"n": "1"}
    r = compare_payload_shapes(current, baseline)
    assert r.passed is False
    assert any("type_drift" in n for n in r.notes)
