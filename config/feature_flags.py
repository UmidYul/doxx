from __future__ import annotations

from dataclasses import dataclass, field

from domain.rollout_policy import RolloutStage


@dataclass(frozen=True)
class FeatureFlagSpec:
    """Static registry entry: parser behavior groups (6B)."""

    feature_name: str
    default_stage: RolloutStage
    default_enabled: bool
    allowed_stores: tuple[str, ...] = ()
    supports_canary: bool = True
    notes: tuple[str, ...] = ()


FEATURE_FLAG_REGISTRY: dict[str, FeatureFlagSpec] = {
    "crm_http_transport": FeatureFlagSpec(
        feature_name="crm_http_transport",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Core CRM HTTP delivery; keep full unless dry-run transport is introduced.",),
    ),
    "lifecycle_delta_events": FeatureFlagSpec(
        feature_name="lifecycle_delta_events",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Delta lifecycle types beyond product_found; gated by settings + rollout.",),
    ),
    "typed_specs_mapping": FeatureFlagSpec(
        feature_name="typed_specs_mapping",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Registry-driven typed_specs; off => raw_specs + base normalization only.",),
    ),
    "normalization_quality_metadata": FeatureFlagSpec(
        feature_name="normalization_quality_metadata",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("normalization_quality dict on payload.",),
    ),
    "spec_coverage_export": FeatureFlagSpec(
        feature_name="spec_coverage_export",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Full spec_coverage report vs compact stub.",),
    ),
    "observability_export": FeatureFlagSpec(
        feature_name="observability_export",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Health snapshot / ETL-oriented export on spider close.",),
    ),
    "store_acceptance_enforced": FeatureFlagSpec(
        feature_name="store_acceptance_enforced",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=False,
        notes=("When on, store enablement can block runs if acceptance failed.",),
    ),
    "replay_reconciliation": FeatureFlagSpec(
        feature_name="replay_reconciliation",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Advanced reconciliation + resend paths after CRM apply.",),
    ),
    "browser_escalation_policy": FeatureFlagSpec(
        feature_name="browser_escalation_policy",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Escalate to Playwright/browser from HTTP shell signals.",),
    ),
    "store_profile_runtime_control": FeatureFlagSpec(
        feature_name="store_profile_runtime_control",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Honor store profile proxy/browser modes at runtime.",),
    ),
    "access_delay_jitter": FeatureFlagSpec(
        feature_name="access_delay_jitter",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Downloader-slot randomized delay jitter; gated by SCRAPY_RANDOMIZED_DELAY_ENABLED.",),
    ),
    "header_profile_rotation": FeatureFlagSpec(
        feature_name="header_profile_rotation",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Desktop User-Agent/header profile rotation for Scrapy HTTP requests.",),
    ),
    "proxy_policy_hardening": FeatureFlagSpec(
        feature_name="proxy_policy_hardening",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Per-store proxy pools, sticky/rotating selection, health scoring, cooldown.",),
    ),
    "captcha_hooks": FeatureFlagSpec(
        feature_name="captcha_hooks",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Captcha signal hooks + solver abstraction (noop by default).",),
    ),
    "honeypot_link_filter": FeatureFlagSpec(
        feature_name="honeypot_link_filter",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Filter hidden/honeypot listing links before scheduling requests.",),
    ),
    "ban_signal_monitoring": FeatureFlagSpec(
        feature_name="ban_signal_monitoring",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Access-layer anti-ban monitoring counters, reason breakdown, and status spike alerts.",),
    ),
    "explicit_backoff_engine": FeatureFlagSpec(
        feature_name="explicit_backoff_engine",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Header-aware explicit backoff decision engine (log-only until enforcement rollout).",),
    ),
    "explicit_backoff_enforcement": FeatureFlagSpec(
        feature_name="explicit_backoff_enforcement",
        default_stage="full",
        default_enabled=True,
        allowed_stores=(),
        supports_canary=True,
        notes=("Apply explicit backoff decisions (wait/cooldown) in retry + rate-limit middleware.",),
    ),
}


def get_feature_spec(feature_name: str) -> FeatureFlagSpec | None:
    return FEATURE_FLAG_REGISTRY.get((feature_name or "").strip())
