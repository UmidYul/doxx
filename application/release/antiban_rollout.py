from __future__ import annotations

from config.feature_flags import get_feature_spec
from config.settings import settings

ANTIBAN_FEATURE_SEQUENCE: tuple[str, ...] = (
    "access_delay_jitter",
    "header_profile_rotation",
    "proxy_policy_hardening",
    "captcha_hooks",
    "honeypot_link_filter",
    "ban_signal_monitoring",
)

ANTIBAN_SETTING_GATES: dict[str, str] = {
    "access_delay_jitter": "SCRAPY_RANDOMIZED_DELAY_ENABLED",
    "header_profile_rotation": "SCRAPY_HEADER_PROFILE_ROTATION_ENABLED",
    "proxy_policy_hardening": "SCRAPY_PROXY_POLICY_HARDENING_ENABLED",
    "captcha_hooks": "SCRAPY_CAPTCHA_HOOKS_ENABLED",
    "honeypot_link_filter": "SCRAPY_HONEYPOT_FILTER_ENABLED",
    "ban_signal_monitoring": "SCRAPY_BAN_SIGNAL_MONITORING_ENABLED",
}


def anti_ban_feature_flags_registered() -> tuple[bool, list[str]]:
    """Return whether all anti-ban features exist in registry and missing names."""
    missing = [name for name in ANTIBAN_FEATURE_SEQUENCE if get_feature_spec(name) is None]
    return (len(missing) == 0, missing)


def is_antiban_runtime_enabled() -> bool:
    """Return True if any anti-ban runtime setting gate is enabled."""
    for setting_name in ANTIBAN_SETTING_GATES.values():
        if bool(getattr(settings, setting_name, False)):
            return True
    return False


def build_antiban_rollout_strategy(
    *,
    store_names: list[str] | None = None,
    pilot_store: str | None = None,
) -> dict[str, object]:
    """Build staged anti-ban rollout strategy for local→staging→pilot→10%→full."""
    stores = [str(s).strip() for s in (store_names or list(getattr(settings, "STORE_NAMES", []) or [])) if str(s).strip()]
    pilot = (pilot_store or (stores[0] if stores else "")).strip() or None
    ten_percent = int(getattr(settings, "ROLLOUT_CANARY_PERCENTAGE", 10) or 10)
    ten_percent = max(1, min(100, ten_percent))

    stages: list[dict[str, object]] = [
        {
            "name": "local",
            "scope": "single developer store",
            "target_stores": [pilot] if pilot else [],
            "target_percentage": 100,
            "feature_subset": [
                "access_delay_jitter",
                "header_profile_rotation",
                "honeypot_link_filter",
            ],
            "required_checks": [
                "unit_tests_passed",
                "short_crawl_no_parser_regressions",
            ],
        },
        {
            "name": "staging",
            "scope": "all staging stores",
            "target_stores": stores,
            "target_percentage": 100,
            "feature_subset": [
                "access_delay_jitter",
                "header_profile_rotation",
                "honeypot_link_filter",
                "proxy_policy_hardening",
                "captcha_hooks",
                "ban_signal_monitoring",
            ],
            "required_checks": [
                "smoke_crawl_passed",
                "no_critical_spikes_in_ban_metrics",
            ],
        },
        {
            "name": "pilot_1_store",
            "scope": "single production store",
            "target_stores": [pilot] if pilot else [],
            "target_percentage": 100,
            "feature_subset": list(ANTIBAN_FEATURE_SEQUENCE),
            "required_checks": [
                "pilot_store_slo_green",
                "rollback_drill_verified",
            ],
        },
        {
            "name": "pilot_10_percent_stores",
            "scope": "production canary stores",
            "target_stores": [],
            "target_percentage": ten_percent,
            "feature_subset": list(ANTIBAN_FEATURE_SEQUENCE),
            "required_checks": [
                "canary_alert_rate_within_threshold",
                "no_regression_vs_control_stores",
            ],
        },
        {
            "name": "full_rollout",
            "scope": "all production stores",
            "target_stores": stores,
            "target_percentage": 100,
            "feature_subset": list(ANTIBAN_FEATURE_SEQUENCE),
            "required_checks": [
                "release_owner_approval",
                "go_live_policy_green",
            ],
        },
    ]

    return {
        "feature_sequence": list(ANTIBAN_FEATURE_SEQUENCE),
        "setting_gates": dict(ANTIBAN_SETTING_GATES),
        "pilot_store": pilot,
        "stages": stages,
    }


def build_antiban_rollback_actions() -> list[str]:
    """Return ordered rollback actions for anti-ban rollout."""
    return [
        "Set SCRAPY_* anti-ban runtime gates to false for immediate stop.",
        "Set anti-ban feature flags to disabled or canary stage via rollout policy.",
        "Disable affected stores with ROLLOUT_DISABLED_STORES while investigating.",
        "Revert anti-ban rollout commit if runtime rollback is insufficient.",
        "Run focused smoke crawl before re-enabling any stage.",
    ]
