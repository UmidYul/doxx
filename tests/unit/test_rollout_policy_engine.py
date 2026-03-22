from __future__ import annotations

from config import settings as settings_mod

from application.release.rollout_policy_engine import decide_feature_rollout, is_feature_enabled


def test_master_switch_off_enables_all(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", False)
    assert is_feature_enabled("typed_specs_mapping", "mediapark", "m:1") is True


def test_disabled_store_blocks_feature(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_PROGRESSIVE_STORE_ENABLEMENT", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_DISABLED_STORES", ["mediapark"])
    assert is_feature_enabled("typed_specs_mapping", "mediapark", "m:1") is False


def test_full_stage_enables_typed_mapping(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", False)
    assert is_feature_enabled("typed_specs_mapping", "mediapark", "m:1") is True


def test_canary_subset_deterministic(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "ENABLE_FEATURE_FLAGS", True)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_STORE_ROLLOUT_POLICY", False)
    monkeypatch.setattr(settings_mod.settings, "ENABLE_CANARY_ROLLOUT", True)
    monkeypatch.setattr(settings_mod.settings, "ROLLOUT_HASH_BASED_SELECTION", True)
    from config import feature_flags as ff_mod

    orig = ff_mod.get_feature_spec

    def _gs(n: str):
        if n == "typed_specs_mapping":
            return ff_mod.FeatureFlagSpec(
                feature_name="typed_specs_mapping",
                default_stage="canary",
                default_enabled=True,
                supports_canary=True,
                notes=("t",),
            )
        return orig(n)

    monkeypatch.setattr("application.release.rollout_policy_engine.get_feature_spec", _gs)
    d1 = decide_feature_rollout("typed_specs_mapping", "mediapark", "stable-key-123")
    d2 = decide_feature_rollout("typed_specs_mapping", "mediapark", "stable-key-123")
    assert d1.enabled == d2.enabled
    assert d1.canary_selected == d2.canary_selected
