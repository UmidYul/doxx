from __future__ import annotations

from application.extractors.spec_label_normalizer import (
    collapse_whitespace,
    normalize_spec_label,
    normalize_unicode_variants,
)


def test_normalize_unicode_yo_to_e():
    assert "е" in normalize_unicode_variants("ёлка")


def test_collapse_whitespace():
    assert collapse_whitespace("  a   b  ") == "a b"


def test_normalize_spec_label_colon_and_case():
    assert normalize_spec_label("Цвет:") == normalize_spec_label("цвет")


def test_normalize_spec_label_casefold_and_spaces():
    a = normalize_spec_label("  Оперативная   память  ")
    b = normalize_spec_label("оперативная память")
    assert a == b
