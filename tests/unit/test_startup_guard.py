from __future__ import annotations

import pytest

from config.settings import Settings
from infrastructure.security.startup_guard import reset_startup_security_checks_for_tests, run_startup_security_checks


@pytest.fixture(autouse=True)
def _reset_guard() -> None:
    reset_startup_security_checks_for_tests()
    yield
    reset_startup_security_checks_for_tests()


def test_startup_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(
        _env_file=None,
        ENABLE_SECURITY_STARTUP_VALIDATION=False,
        CRM_PARSER_KEY="",
    )
    r = run_startup_security_checks(s, force=True)
    assert r.passed
    assert any("skipped" in w.lower() for w in r.warnings)


def test_startup_fail_fast_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(
        _env_file=None,
        ENABLE_SECURITY_STARTUP_VALIDATION=True,
        SECURITY_FAIL_FAST_ON_INVALID_CONFIG=True,
        CRM_PARSER_KEY="",
        CRM_PARSER_KEY_FILE="",
        ENABLE_SECRET_FILE_FALLBACK=True,
        TRANSPORT_TYPE="crm_http",
        CRM_BASE_URL="http://x",
    )
    with pytest.raises(RuntimeError, match="SECURITY"):
        run_startup_security_checks(s, force=True)
