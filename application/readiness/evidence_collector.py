from __future__ import annotations

from pathlib import Path

from domain.production_readiness import EvidenceType, ReadinessDomain, ReadinessEvidence


def _exists(root: Path, *parts: str) -> bool:
    return (root.joinpath(*parts)).is_file()


def find_test_evidence(project_root: str) -> list[ReadinessEvidence]:
    """Pragmatic presence of test trees and representative modules."""
    root = Path(project_root)
    out: list[ReadinessEvidence] = []
    domains: list[tuple[ReadinessDomain, Path, EvidenceType, str]] = [
        ("crawl", root / "tests" / "unit", "unit_tests", "tests/unit"),
        ("normalization", root / "tests" / "unit", "unit_tests", "tests/unit normalize tests"),
        ("crm_integration", root / "tests" / "unit", "unit_tests", "tests/unit crm transport"),
        ("lifecycle", root / "tests" / "unit", "unit_tests", "tests/unit lifecycle"),
        ("batch_apply", root / "tests" / "unit", "unit_tests", "tests/unit batch sync"),
        ("replay_reconciliation", root / "tests" / "unit", "unit_tests", "tests/unit replay"),
        ("observability", root / "tests" / "unit", "unit_tests", "tests/unit observability"),
        ("security", root / "tests" / "unit", "unit_tests", "tests/unit security"),
        ("performance", root / "tests" / "unit", "unit_tests", "tests/unit performance"),
        ("release_governance", root / "tests" / "unit", "unit_tests", "tests/unit release"),
    ]
    for domain, p, et, name in domains:
        out.append(
            ReadinessEvidence(
                domain=domain,
                evidence_type=et,
                artifact_name=name,
                artifact_path=str(p) if p.is_dir() else None,
                valid=p.is_dir() and any(p.glob("test_*.py")),
            )
        )

    ct = root / "tests" / "contracts"
    out.append(
        ReadinessEvidence(
            domain="crm_integration",
            evidence_type="contract_tests",
            artifact_name="tests/contracts",
            artifact_path=str(ct),
            valid=ct.is_dir() and any(ct.rglob("test_*.py")),
        )
    )
    out.append(
        ReadinessEvidence(
            domain="normalization",
            evidence_type="contract_tests",
            artifact_name="tests/contracts lifecycle",
            artifact_path=str(ct),
            valid=ct.is_dir(),
        )
    )

    reg = root / "tests" / "regression"
    out.append(
        ReadinessEvidence(
            domain="crawl",
            evidence_type="acceptance_tests",
            artifact_name="tests/regression",
            artifact_path=str(reg),
            valid=reg.is_dir() and any(reg.rglob("test_*.py")),
        )
    )
    fx = root / "tests" / "fixtures"
    out.append(
        ReadinessEvidence(
            domain="normalization",
            evidence_type="fixtures",
            artifact_name="tests/fixtures/regression",
            artifact_path=str(fx / "regression"),
            valid=(fx / "regression").is_dir(),
        )
    )
    return out


def find_docs_evidence(project_root: str) -> list[ReadinessEvidence]:
    root = Path(project_root)
    pairs: list[tuple[ReadinessDomain, str]] = [
        ("documentation", "docs/README.md"),
        ("documentation", "docs/onboarding.md"),
        ("documentation", "OWNERSHIP_MAP.md"),
        ("supportability", "docs/support_triage.md"),
        ("crm_integration", "docs/crm_integration.md"),
        ("release_governance", "docs/release_process.md"),
        ("lifecycle", "docs/adr/0002-product-found-default-lifecycle.md"),
        ("replay_reconciliation", "docs/adr/0005-replay-safe-fallbacks.md"),
        ("documentation", "docs/production_readiness.md"),
    ]
    out: list[ReadinessEvidence] = []
    for domain, rel in pairs:
        p = root / rel
        out.append(
            ReadinessEvidence(
                domain=domain,
                evidence_type="docs",
                artifact_name=rel,
                artifact_path=str(p) if p.is_file() else None,
                valid=p.is_file(),
            )
        )
    return out


def find_config_evidence(project_root: str) -> list[ReadinessEvidence]:
    root = Path(project_root)
    out: list[ReadinessEvidence] = []
    configs = [
        ("crawl", "config/scrapy_settings.py"),
        ("crawl", "config/settings.py"),
        ("crm_integration", "config/settings.py"),
        ("security", "config/settings.py"),
        ("release_governance", "config/settings.py"),
        ("performance", "config/settings.py"),
    ]
    for domain, rel in configs:
        p = root / rel
        out.append(
            ReadinessEvidence(
                domain=domain,
                evidence_type="config",
                artifact_name=rel,
                artifact_path=str(p) if p.is_file() else None,
                valid=p.is_file(),
            )
        )
    return out


def collect_readiness_evidence(project_root: str) -> list[ReadinessEvidence]:
    """Aggregate pragmatic file/directory evidence for readiness reporting."""
    seen: set[tuple[str, str | None, str]] = set()
    merged: list[ReadinessEvidence] = []
    for ev in find_test_evidence(project_root) + find_docs_evidence(project_root) + find_config_evidence(project_root):
        key = (ev.domain, ev.artifact_path, ev.evidence_type)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ev)
    return merged
