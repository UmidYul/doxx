from __future__ import annotations

from domain.release_quality import ReleaseCheckResult, ReleaseReadinessSummary

from application.release.release_summary import build_human_release_report, build_release_report


def test_build_release_report_lists_failures():
    summary = ReleaseReadinessSummary(
        overall_passed=False,
        critical_failures=2,
        warnings=0,
        checks=[
            ReleaseCheckResult(
                check_name="store_acceptance:mediapark",
                passed=False,
                category="acceptance",
                notes=["gate"],
            ),
            ReleaseCheckResult(
                check_name="contract:payload",
                passed=False,
                category="contract",
                notes=["drift"],
            ),
        ],
        gates=[],
        recommended_action="block_release",
    )
    rep = build_release_report(summary)
    assert rep["overall_passed"] is False
    assert "mediapark" in rep["stores_failing_acceptance"]
    assert "contract:payload" in rep["failed_contract_checks"]
    text = build_human_release_report(summary)
    assert "block_release" in text or "Do not ship" in text


def test_human_report_release_with_caution():
    summary = ReleaseReadinessSummary(
        overall_passed=True,
        critical_failures=0,
        warnings=2,
        checks=[],
        gates=[],
        recommended_action="release_with_caution",
    )
    text = build_human_release_report(summary)
    assert "caution" in text.lower()
