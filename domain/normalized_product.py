from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from domain.typed_specs import TypedPartialSpecs


def _strip_none_values(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _strip_none_values(x) for k, x in obj.items() if x is not None and x != []}
    if isinstance(obj, list):
        return [_strip_none_values(x) for x in obj if x is not None]
    return obj


class NormalizedProduct(BaseModel):
    """Light normalization for CRM sync — match keys, partial typed specs, UZS integer price."""

    model_config = ConfigDict(str_strip_whitespace=True)

    store: str
    url: str
    title: str
    title_clean: str
    source_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    barcode: str | None = None
    model_name: str | None = None
    category_hint: str | None = None

    price_raw: str | None = None
    price_value: int | None = None
    currency: str = "UZS"
    in_stock: bool | None = None

    brand: str | None = None
    raw_specs: dict[str, str] = Field(
        default_factory=dict,
        description="Original key→value specs from the store; always preserved.",
    )
    typed_specs: TypedPartialSpecs = Field(
        default_factory=TypedPartialSpecs,
        description="Best-effort typed layer; partial. Does not replace raw_specs.",
    )
    normalization_warnings: list[str] = Field(
        default_factory=list,
        description="Codes for conflicts, implausible values, ambiguous mappings.",
    )
    spec_coverage: dict[str, object] = Field(
        default_factory=dict,
        description="Operational mapping coverage (optional CRM inclusion via settings).",
    )
    field_confidence: dict[str, object] = Field(
        default_factory=dict,
        description="Per-field normalization confidence (compact dicts); operational metadata.",
    )
    suppressed_typed_fields: list[dict[str, object]] = Field(
        default_factory=list,
        description="Typed fields dropped with machine-readable reason codes.",
    )
    normalization_quality: dict[str, object] = Field(
        default_factory=dict,
        description="Aggregate normalization quality summary for observability.",
    )

    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)

    @field_serializer("typed_specs")
    def _serialize_typed_specs(self, v: TypedPartialSpecs) -> dict[str, object]:
        return v.to_compact_dict()

    @field_serializer("field_confidence")
    def _serialize_field_confidence(self, v: dict[str, object]) -> dict[str, object]:
        return {k: _strip_none_values(val) for k, val in v.items() if val is not None}

    @field_serializer("normalization_quality")
    def _serialize_normalization_quality(self, v: dict[str, object]) -> dict[str, object]:
        out = _strip_none_values(v)
        return out if isinstance(out, dict) else {}

    @field_serializer("suppressed_typed_fields")
    def _serialize_suppressed(self, v: list[dict[str, object]]) -> list[dict[str, object]]:
        return [x for x in (_strip_none_values(d) for d in v) if isinstance(x, dict)]
