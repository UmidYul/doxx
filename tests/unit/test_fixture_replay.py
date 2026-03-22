from __future__ import annotations

from pathlib import Path

import pytest

from application.dev.fixture_replay import (
    replay_lifecycle_fixture,
    replay_listing_fixture,
    replay_normalization_fixture,
    replay_product_fixture,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regression" / "normalization" / "laptop.json"


def test_replay_normalization_fixture_output() -> None:
    out = replay_normalization_fixture(str(FIXTURE))
    assert out["kind"] == "normalization_replay_v1"
    n = out.get("normalized")
    assert isinstance(n, dict) and n.get("store") == "mediapark"
    assert "debug" in out


def test_replay_listing_and_product_match() -> None:
    a = replay_listing_fixture(str(FIXTURE), "mediapark")
    b = replay_product_fixture(str(FIXTURE), "mediapark")
    assert a["normalized"] == b["normalized"]


def test_replay_lifecycle_fixture_usable() -> None:
    out = replay_lifecycle_fixture(str(FIXTURE))
    assert out["kind"] == "lifecycle_replay_v1"
    assert "lifecycle_event" in out and "parser_sync_event" in out
    assert "debug" in out


def test_replay_lifecycle_requires_shape(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="normalized|raw_item"):
        replay_lifecycle_fixture(str(p))
