from __future__ import annotations

from application.release.store_gate_runner import build_store_acceptance_check, run_store_acceptance_gates


def test_build_store_acceptance_check_shape():
    r = build_store_acceptance_check("mediapark", True, [])
    assert r.passed and r.category == "acceptance"
    assert r.check_name == "store_acceptance:mediapark"


def test_run_store_acceptance_mediapark_fixture_passes(monkeypatch):
    monkeypatch.setattr("application.release.store_gate_runner.settings.STORE_NAMES", ["mediapark"])
    results = run_store_acceptance_gates(["mediapark"])
    assert len(results) == 1
    assert results[0].passed, results[0].notes


def test_run_store_acceptance_texnomart_fixture_passes(monkeypatch):
    monkeypatch.setattr("application.release.store_gate_runner.settings.STORE_NAMES", ["texnomart"])
    results = run_store_acceptance_gates(["texnomart"])
    assert len(results) == 1
    assert results[0].passed, results[0].notes


def test_run_store_acceptance_alifshop_fixture_passes(monkeypatch):
    monkeypatch.setattr("application.release.store_gate_runner.settings.STORE_NAMES", ["alifshop"])
    results = run_store_acceptance_gates(["alifshop"])
    assert len(results) == 1
    assert results[0].passed, results[0].notes
