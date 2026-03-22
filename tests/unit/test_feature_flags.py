from __future__ import annotations

from config.feature_flags import FEATURE_FLAG_REGISTRY, get_feature_spec


def test_registry_has_required_groups():
    for name in (
        "crm_http_transport",
        "lifecycle_delta_events",
        "typed_specs_mapping",
        "normalization_quality_metadata",
        "spec_coverage_export",
        "observability_export",
        "store_acceptance_enforced",
        "replay_reconciliation",
        "browser_escalation_policy",
        "store_profile_runtime_control",
    ):
        assert name in FEATURE_FLAG_REGISTRY
        assert get_feature_spec(name) is not None
