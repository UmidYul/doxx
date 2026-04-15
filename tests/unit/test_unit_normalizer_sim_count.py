from __future__ import annotations

from application.extractors.unit_normalizer import normalize_sim_count


def test_normalize_sim_count_dual_slot_phrase() -> None:
    assert normalize_sim_count("2 nano SIM") == 2


def test_normalize_sim_count_esim_combo() -> None:
    assert normalize_sim_count("nano-SIM + eSIM") == 2


def test_normalize_sim_count_does_not_use_unrelated_digits() -> None:
    assert normalize_sim_count("SIM 12") is None
    assert normalize_sim_count("version 2.0") is None


def test_normalize_sim_count_single_token() -> None:
    assert normalize_sim_count("nano-SIM") == 1
