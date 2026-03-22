from __future__ import annotations

from unittest.mock import patch

from application.dev.dev_run import (
    build_dev_run_command,
    explain_dev_run_modes,
    resolve_single_store_target,
)
from infrastructure.transports.dry_run import DryRunTransport
from infrastructure.transports.factory import get_transport


def test_explain_dev_run_modes_non_empty() -> None:
    assert "dry_run" in explain_dev_run_modes().lower()


def test_resolve_single_store_target_ok() -> None:
    r = resolve_single_store_target("mediapark", store_names=["mediapark", "uzum"])
    assert r["ok"] is True
    assert "scrapy_argv" in r


def test_resolve_single_store_target_unknown() -> None:
    r = resolve_single_store_target("unknown_store_xyz", store_names=["mediapark"])
    assert r["ok"] is False


def test_build_dev_run_command_fixture_replay() -> None:
    cmd = build_dev_run_command("fixture_replay", fixture_path="tests/fixtures/x.json")
    assert "replay_normalization_fixture" in " ".join(cmd)


def test_dry_run_factory_selects_dry_run_transport() -> None:
    with patch.multiple(
        "infrastructure.transports.factory.settings",
        MOSCRAPER_DISABLE_PUBLISH=False,
        TRANSPORT_TYPE="crm_http",
        DEV_MODE=True,
        DEV_DRY_RUN_DISABLE_CRM_SEND=True,
    ):
        t = get_transport()
    assert isinstance(t, DryRunTransport)
