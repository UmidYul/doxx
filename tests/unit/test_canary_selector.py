from __future__ import annotations

from application.release.canary_selector import build_rollout_key, select_canary_bucket


def test_same_key_same_bucket():
    a = select_canary_bucket("mediapark|ek1|typed_specs_mapping", 50)
    b = select_canary_bucket("mediapark|ek1|typed_specs_mapping", 50)
    assert a == b


def test_build_rollout_key_stable():
    k1 = build_rollout_key("st", "e1", "f")
    assert "st" in k1 and "e1" in k1 and "f" in k1


def test_percentage_zero_never():
    assert select_canary_bucket("any", 0) is False


def test_percentage_hundred_always():
    assert select_canary_bucket("any", 100) is True
