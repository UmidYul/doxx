from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from config.settings import Settings
from infrastructure.access import proxy_policy


def test_proxy_unavailable_empty_path():
    s = Settings(PROXY_LIST_PATH="", SCRAPY_ROTATING_PROXY_ENABLED=False, _env_file=None)
    assert proxy_policy.is_proxy_available(s) is False
    assert proxy_policy.should_install_rotating_proxy_middleware(s) is False


def test_proxy_missing_file_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    s = Settings(PROXY_LIST_PATH=str(tmp_path / "nope.txt"), _env_file=None)
    caplog.set_level("WARNING")
    assert proxy_policy.is_proxy_available(s) is False


def test_build_proxy_meta_graceful_when_no_file():
    s = Settings(PROXY_LIST_PATH="", _env_file=None)
    assert proxy_policy.build_proxy_meta("mediapark", "listing", settings=s) == {}


def test_build_proxy_meta_first_line(tmp_path: Path):
    # Use a non-reserved global unicast IP (TEST-NET / doc ranges are is_reserved and blocked by policy).
    p = tmp_path / "proxies.txt"
    p.write_text("# c\nhttp://8.8.8.8:8888\n", encoding="utf-8")
    s = Settings(PROXY_LIST_PATH=str(p), _env_file=None)
    meta = proxy_policy.build_proxy_meta("mediapark", "listing", settings=s)
    assert meta.get("proxy") == "http://8.8.8.8:8888"


def test_rotating_install_only_when_flag_and_file(tmp_path: Path):
    p = tmp_path / "p.txt"
    p.write_text("http://a:1\n", encoding="utf-8")
    off = Settings(PROXY_LIST_PATH=str(p), SCRAPY_ROTATING_PROXY_ENABLED=False, _env_file=None)
    assert proxy_policy.should_install_rotating_proxy_middleware(off) is False
    on = Settings(PROXY_LIST_PATH=str(p), SCRAPY_ROTATING_PROXY_ENABLED=True, _env_file=None)
    assert proxy_policy.should_install_rotating_proxy_middleware(on) is True
