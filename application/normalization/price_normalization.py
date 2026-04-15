from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NEGOTIABLE_RE = re.compile(
    r"(?:\u043f\u043e\s*\u0434\u043e\u0433\u043e\u0432\u043e\u0440[\u0451\u0435]\u043d\u043d\u043e\u0441\u0442\u0438"
    r"|\u043f\u043e\s*\u0437\u0430\u043f\u0440\u043e\u0441\u0443"
    r"|narxi\s*kelishiladi"
    r"|\u0446\u0435\u043d\u0430\s*\u043d\u0435\s*\u0443\u043a\u0430\u0437\u0430\u043d\u0430"
    r"|bepul"
    r"|\u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e)",
    re.IGNORECASE,
)
_PRICE_CURRENCY_RE = re.compile(
    r"(?:\u0441\u0443\u043c|\u0441\u045e\u043c|sum|uzs|\u0440\u0443\u0431\w*|₽|\$|€|£|¥)",
    re.IGNORECASE,
)
_INSTALLMENT_RE = re.compile(
    r"(?:/\s*(?:\u043c\u0435\u0441|month|mo)\b"
    r"|\b(?:\u0432\s+\u043c\u0435\u0441\u044f\u0446|\u0435\u0436\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u043e|monthly|installment)\b"
    r"|\b(?:\u0440\u0430\u0441\u0441\u0440\u043e\u0447\w*)\b)",
    re.IGNORECASE,
)
_MULTI_PRICE_CONTEXT_RE = re.compile(
    r"\b(?:\u0431\u044b\u043b\u043e|\u0441\u0442\u0430\u043b\u043e|old\s+price|new\s+price)\b",
    re.IGNORECASE,
)
_PRICE_RANGE_RE = re.compile(r"\d[\d\s\xa0.,]*\s*[-\u2013\u2014]\s*\d")
_STARTING_FROM_RE = re.compile(r"^\s*(?:\u043e\u0442|from)\b", re.IGNORECASE)
_PRICE_TOKEN_RE = re.compile(r"\d[\d\s\xa0.,]*")


def _normalize_price_token(raw: str) -> str | None:
    token = raw.replace("\xa0", " ").strip()
    token = re.sub(r"\s+", "", token)
    if not token:
        return None

    token = token.replace(",", ".")
    if token.count(".") > 1:
        parts = token.split(".")
        if len(parts[-1]) <= 2:
            token = "".join(parts[:-1]) + "." + parts[-1]
        else:
            token = "".join(parts)
    elif token.count(".") == 1:
        after_dot = token.split(".")[-1].strip()
        digits_after = re.sub(r"\D", "", after_dot)
        if len(digits_after) == 3:
            token = token.replace(".", "")

    token = re.sub(r"[^\d.]", "", token)
    return token or None


def normalize_price(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text or text == "0":
        return None
    if _NEGOTIABLE_RE.search(text):
        return None
    if _INSTALLMENT_RE.search(text):
        return None
    if _MULTI_PRICE_CONTEXT_RE.search(text):
        return None
    if _PRICE_RANGE_RE.search(text):
        return None
    if _STARTING_FROM_RE.search(text):
        return None

    cleaned = _PRICE_CURRENCY_RE.sub(" ", text)
    tokens = [_normalize_price_token(match) for match in _PRICE_TOKEN_RE.findall(cleaned)]
    normalized_tokens = [token for token in tokens if token and not all(char in ".0" for char in token)]
    if len(normalized_tokens) != 1:
        return None

    try:
        result = Decimal(normalized_tokens[0])
    except InvalidOperation:
        return None
    if result <= 0:
        return None
    return result
