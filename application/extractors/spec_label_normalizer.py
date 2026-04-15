from __future__ import annotations

import re
import unicodedata

_COLON_END = re.compile(r"\s*:\s*$")
_MULTI_SPACE = re.compile(r"\s+")
_ESCAPED_WS = re.compile(r"(?:\\[trn])+")
_TRAIL_UNIT_JUNK = re.compile(
    r"\s*[,;]\s*(гб|gb|тб|tb|мah|mah|мач|гц|hz|кг|kg|г\b|mm|мм)\s*$",
    re.IGNORECASE,
)
_NOISE_TOKENS = re.compile(
    r"\s*[\[\(]?(?:новинка|sale|акция|хит)[\]\)]?\s*$",
    re.IGNORECASE,
)


def normalize_unicode_variants(label: str) -> str:
    """Normalize compatibility forms; map Cyrillic ё→е."""
    s = unicodedata.normalize("NFKC", label or "")
    return s.replace("ё", "е").replace("Ё", "е")


def collapse_whitespace(label: str) -> str:
    return _MULTI_SPACE.sub(" ", (label or "").strip())


def strip_noise_tokens(label: str) -> str:
    s = collapse_whitespace(label)
    s = _NOISE_TOKENS.sub("", s)
    s = _TRAIL_UNIT_JUNK.sub("", s)
    s = _COLON_END.sub("", s)
    return collapse_whitespace(s)


def normalize_spec_label(label: str) -> str:
    """Stable key for alias matching: unicode, spacing, case, light noise strip."""
    if not label:
        return ""
    s = normalize_unicode_variants(str(label))
    s = _ESCAPED_WS.sub(" ", s)
    s = s.replace("\t", " ").replace("\xa0", " ")
    s = re.sub(r"[^\w\s\-+/.,%°\"″'а-яa-z]", " ", s, flags=re.IGNORECASE)
    s = strip_noise_tokens(s)
    return s.casefold()
