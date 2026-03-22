from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["none", "low", "medium", "high"]


class RequiredFieldPolicy(BaseModel):
    """Formal required vs recommended field groups for scraped dicts (spider output)."""

    model_config = {"frozen": True}

    required_keys: tuple[str, ...] = ("title", "url", "source", "identity")
    recommended_keys: tuple[str, ...] = (
        "price_str",
        "brand",
        "image_urls",
        "raw_specs",
        "category_hint",
    )
    optional_keys: tuple[str, ...] = ("description", "barcode", "model_name")


class StoreQualityGate(BaseModel):
    """Ratio/count thresholds; failing any can fail the store QA run."""

    model_config = {"frozen": True}

    field_presence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    parse_success_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    duplicate_ratio_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    partial_item_ratio_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    zero_result_category_threshold: int = Field(default=10, ge=0)
    pagination_loop_threshold: int = Field(default=5, ge=0)
    banned_response_threshold: float = Field(default=0.10, ge=0.0, le=1.0)


class StoreEdgeCaseScenario(BaseModel):
    """Named scenario → fixture path under ``tests/fixtures/stores/``."""

    model_config = {"frozen": True}

    name: str
    fixture_relative_path: str
    expected_edge_tags: tuple[str, ...] = ()
    must_not_fail_acceptance: bool = True


class StoreAcceptanceProfile(BaseModel):
    model_config = {"frozen": True}

    store_name: str
    required_listing_signals: tuple[str, ...] = ("product_links",)
    required_product_signals: tuple[str, ...] = ("title", "url", "source", "identity")
    required_fields: RequiredFieldPolicy = Field(default_factory=RequiredFieldPolicy)
    optional_fields: tuple[str, ...] = ("description", "barcode", "model_name")
    min_product_links_per_listing_page: int = 1
    max_duplicate_listing_repeats: int = 3
    supports_variants: bool = True
    supports_js_shell: RiskLevel = "medium"
    supports_mobile_redirect_risk: RiskLevel = "medium"
    browser_dependence: RiskLevel = "low"
    variant_risk: RiskLevel = "medium"
    empty_shell_risk: RiskLevel = "low"
    expected_category_hints: frozenset[str] = frozenset()
    quality_gates: StoreQualityGate = Field(default_factory=StoreQualityGate)
    edge_case_scenarios: tuple[StoreEdgeCaseScenario, ...] = ()


MEDIAPARK_ACCEPTANCE = StoreAcceptanceProfile(
    store_name="mediapark",
    required_listing_signals=("product_links", "pagination_hint_optional"),
    required_product_signals=("title", "url", "source", "identity"),
    required_fields=RequiredFieldPolicy(),
    optional_fields=("description", "barcode", "model_name"),
    min_product_links_per_listing_page=1,
    max_duplicate_listing_repeats=3,
    supports_variants=True,
    supports_js_shell="medium",
    supports_mobile_redirect_risk="medium",
    browser_dependence="low",
    variant_risk="medium",
    empty_shell_risk="low",
    expected_category_hints=frozenset(
        {"phone", "laptop", "tv", "tablet", "appliance", "accessory", "unknown"}
    ),
    quality_gates=StoreQualityGate(
        field_presence_threshold=0.72,
        parse_success_threshold=0.55,
        duplicate_ratio_threshold=0.40,
        partial_item_ratio_threshold=0.50,
        zero_result_category_threshold=12,
        pagination_loop_threshold=6,
        banned_response_threshold=0.12,
    ),
    edge_case_scenarios=(
        StoreEdgeCaseScenario(
            name="listing_good",
            fixture_relative_path="mediapark/listing_good.html",
        ),
        StoreEdgeCaseScenario(
            name="pdp_partial",
            fixture_relative_path="mediapark/pdp_partial.html",
        ),
    ),
)

UZUM_ACCEPTANCE = StoreAcceptanceProfile(
    store_name="uzum",
    required_listing_signals=("product_links",),
    required_product_signals=("title", "url", "source", "identity"),
    required_fields=RequiredFieldPolicy(),
    optional_fields=("description", "barcode", "model_name"),
    min_product_links_per_listing_page=1,
    max_duplicate_listing_repeats=2,
    supports_variants=True,
    supports_js_shell="high",
    supports_mobile_redirect_risk="medium",
    browser_dependence="high",
    variant_risk="high",
    empty_shell_risk="high",
    expected_category_hints=frozenset(
        {"phone", "laptop", "tv", "tablet", "appliance", "accessory", "unknown"}
    ),
    quality_gates=StoreQualityGate(
        field_presence_threshold=0.65,
        parse_success_threshold=0.50,
        duplicate_ratio_threshold=0.45,
        partial_item_ratio_threshold=0.55,
        zero_result_category_threshold=8,
        pagination_loop_threshold=4,
        banned_response_threshold=0.15,
    ),
    edge_case_scenarios=(
        StoreEdgeCaseScenario(
            name="empty_shell",
            fixture_relative_path="uzum/empty_shell.html",
            expected_edge_tags=("empty_listing_shell",),
        ),
    ),
)

_ACCEPTANCE_REGISTRY: dict[str, StoreAcceptanceProfile] = {
    "mediapark": MEDIAPARK_ACCEPTANCE,
    "uzum": UZUM_ACCEPTANCE,
}


def get_store_acceptance_profile(store_name: str) -> StoreAcceptanceProfile:
    key = (store_name or "").strip().lower()
    if key in _ACCEPTANCE_REGISTRY:
        return _ACCEPTANCE_REGISTRY[key]
    return StoreAcceptanceProfile(
        store_name=store_name or key or "unknown",
        expected_category_hints=MEDIAPARK_ACCEPTANCE.expected_category_hints,
        quality_gates=StoreQualityGate(),
    )
