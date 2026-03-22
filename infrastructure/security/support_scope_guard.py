from __future__ import annotations

from typing import Any

from config.settings import Settings, settings as app_settings
from domain.data_governance import DataUsagePurpose, DiagnosticScopeDecision

_PURPOSE_ALIASES: dict[str, DataUsagePurpose] = {
    "etl": "observability",
    "export": "observability",
    "dashboard": "observability",
    "operator": "support",
    "triage": "support",
    "diagnostic": "support",
}
_VALID_PURPOSES: frozenset[str] = frozenset(
    {"crawl", "normalize", "delivery", "observability", "support", "replay"}
)


def _norm_purpose(purpose: str) -> DataUsagePurpose:
    p = (purpose or "support").strip().lower()
    p = _PURPOSE_ALIASES.get(p, p)  # type: ignore[assignment]
    if p not in _VALID_PURPOSES:
        return "support"
    return p  # type: ignore[return-value]


def decide_support_export_scope(purpose: str, settings: Settings | None = None) -> DiagnosticScopeDecision:
    s = settings or app_settings
    p = _norm_purpose(purpose)
    if not getattr(s, "ENABLE_SUPPORT_SCOPE_RESTRICTIONS", True):
        return DiagnosticScopeDecision(
            allowed=True,
            purpose=p,
            included_sections=list(_all_sections(s)),
            excluded_fields=[],
            reason=None,
        )

    sections = _sections_for_purpose(p, s)
    excluded: list[str] = []
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_RAW_SPECS", True):
        excluded.append("raw_specs")
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_TYPED_SPECS", True):
        excluded.append("typed_specs")
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_FIELD_CONFIDENCE", False):
        excluded.append("field_confidence")
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_SUPPRESSED_FIELDS", False):
        excluded.append("suppressed_typed_fields")
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_RAW_HEADERS", False):
        excluded.append("headers")
    if not getattr(s, "SUPPORT_EXPORT_INCLUDE_FULL_URL_QUERY", False):
        excluded.append("full_url_query")

    return DiagnosticScopeDecision(
        allowed=True,
        purpose=p,
        included_sections=sections,
        excluded_fields=excluded,
        reason=None,
    )


def _all_sections(settings: Settings) -> list[str]:
    base = ["summary", "errors", "counters", "alerts", "replay_hints"]
    if getattr(settings, "SUPPORT_EXPORT_INCLUDE_RAW_SPECS", True):
        base.append("raw_specs")
    if getattr(settings, "SUPPORT_EXPORT_INCLUDE_TYPED_SPECS", True):
        base.append("typed_specs")
    return base


def _sections_for_purpose(purpose: DataUsagePurpose, settings: Settings) -> list[str]:
    if purpose == "observability":
        return _all_sections(settings) + ["traces", "batches", "thresholds"]
    if purpose == "support":
        return ["summary", "errors", "alerts", "diagnostic", "runbook", "replay_hints"]
    if purpose == "replay":
        return ["replay", "summary"]
    if purpose in ("crawl", "normalize", "delivery"):
        return ["summary"]
    return ["summary"]


def should_include_field(field_name: str, purpose: str, settings: Settings | None = None) -> bool:
    s = settings or app_settings
    if not getattr(s, "ENABLE_SUPPORT_SCOPE_RESTRICTIONS", True):
        return True
    fn = (field_name or "").strip()
    scope = decide_support_export_scope(purpose, s)
    if fn in scope.excluded_fields:
        return False
    from infrastructure.security.data_policy_registry import get_field_policy

    pol = get_field_policy(fn)
    if pol is None:
        return True
    p = _norm_purpose(purpose)
    return p in pol.allowed_purposes


def should_include_section(section_name: str, purpose: str, settings: Settings | None = None) -> bool:
    s = settings or app_settings
    scope = decide_support_export_scope(purpose, s)
    return section_name in scope.included_sections


def cap_error_list(errors: list[Any], settings: Settings | None = None) -> list[Any]:
    s = settings or app_settings
    n = int(getattr(s, "SUPPORT_EXPORT_MAX_ERRORS", 20) or 20)
    return errors[: max(0, n)]
