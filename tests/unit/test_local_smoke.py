from __future__ import annotations

from application.dev.local_smoke import run_local_smoke


def test_local_smoke_passes() -> None:
    r = run_local_smoke()
    assert "pass" in r and "steps" in r
    assert isinstance(r["pass"], bool)
    failed = [s for s in r["steps"] if not s.get("pass")]
    assert not failed, failed
