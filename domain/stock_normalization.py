from __future__ import annotations


_FALSE_STOCK_VALUES = frozenset(
    {
        "false",
        "0",
        "no",
        "n",
        "off",
        "out of stock",
        "out-of-stock",
        "\u043d\u0435\u0442",
        "\u043d\u0435\u0442 \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
        "\u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e",
    }
)

_TRUE_STOCK_VALUES = frozenset(
    {
        "true",
        "1",
        "yes",
        "y",
        "on",
        "available",
        "in stock",
        "in-stock",
        "\u0434\u0430",
        "\u0435\u0441\u0442\u044c",
        "\u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
        "\u0435\u0441\u0442\u044c \u0432 \u043d\u0430\u043b\u0438\u0447\u0438\u0438",
    }
)


def normalize_stock_signal(raw: object) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 0:
            return False
        if raw == 1:
            return True
        return None
    if isinstance(raw, str):
        text = raw.strip().lower()
        if not text:
            return None
        if text in _FALSE_STOCK_VALUES:
            return False
        if text in _TRUE_STOCK_VALUES:
            return True
        return None
    return None
