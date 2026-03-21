from __future__ import annotations

import logging

from domain.specs.base import BaseSpecs

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Category detection keywords
# ═══════════════════════════════════════════════════════════════════════════

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "phone": [
        "смартфон", "телефон", "smartphone", "phone", "telefon",
        "iphone", "galaxy", "redmi", "poco", "мобильный",
        "mobil telefon", "сотовый",
    ],
    "laptop": [
        "ноутбук", "laptop", "noutbuk", "macbook", "thinkpad",
        "ultrabook", "ультрабук", "notebook",
    ],
    "tv": [
        "телевизор", "televizor", "tv", "smart tv", "телик",
        "теледидор",
    ],
    "appliance": [
        "холодильник", "стиральная", "посудомоечная", "кондиционер",
        "пылесос", "muzlatgich", "kir yuvish", "konditsioner",
        "changyutgich", "микроволновка", "духовка", "чайник",
        "мультиварка", "обогреватель", "вентилятор",
    ],
}


def detect_category(raw_specs: dict, title: str = "") -> str:
    combined = f"{title} {' '.join(str(v) for v in raw_specs.values())}".lower()
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[category] = score
    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]
    return "phone"


def get_schema_class(category: str) -> type[BaseSpecs]:
    from domain.specs.appliance import ApplianceSpecs
    from domain.specs.laptop import LaptopSpecs
    from domain.specs.phone import PhoneSpecs
    from domain.specs.tv import TVSpecs

    mapping: dict[str, type[BaseSpecs]] = {
        "phone": PhoneSpecs,
        "laptop": LaptopSpecs,
        "tv": TVSpecs,
        "appliance": ApplianceSpecs,
    }
    return mapping.get(category, PhoneSpecs)


# ═══════════════════════════════════════════════════════════════════════════
# Cascade: structured (≥ 0.7) → regex (≥ 0.4) → LLM
# ═══════════════════════════════════════════════════════════════════════════


async def extract_specs(
    raw_specs: dict,
    description: str = "",
    category: str | None = None,
    title: str = "",
) -> BaseSpecs:
    from config.settings import settings

    from application.extractors.llm_extractor import LLMExtractor
    from application.extractors.regex_extractor import RegexExtractor
    from application.extractors.structured_extractor import StructuredExtractor

    if not category:
        category = detect_category(raw_specs, title)

    schema_class = get_schema_class(category)

    structured_ext = StructuredExtractor()
    specs = structured_ext.extract(raw_specs, schema_class)
    logger.debug(
        "Structured extraction score: %.2f (threshold %.2f)",
        specs.completeness_score,
        settings.SPEC_SCORE_THRESHOLD_STRUCTURED,
    )
    if specs.completeness_score >= settings.SPEC_SCORE_THRESHOLD_STRUCTURED:
        return specs

    regex_ext = RegexExtractor()
    specs = regex_ext.enrich(specs, description, category)
    logger.debug(
        "Regex enrichment score: %.2f (threshold %.2f)",
        specs.completeness_score,
        settings.SPEC_SCORE_THRESHOLD_REGEX,
    )
    if specs.completeness_score >= settings.SPEC_SCORE_THRESHOLD_REGEX:
        return specs

    llm_ext = LLMExtractor()
    specs = await llm_ext.enrich(specs, description, schema_class)
    logger.debug("LLM enrichment score: %.2f", specs.completeness_score)
    return specs
