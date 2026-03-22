from __future__ import annotations

from unittest.mock import MagicMock

from application.dev.debug_summary import (
    build_apply_debug_view,
    build_lifecycle_debug_view,
    build_normalized_debug_view,
    build_store_debug_summary,
)
from config.settings import Settings


def test_build_normalized_debug_view_respects_flags() -> None:
    st = MagicMock()
    st.DEV_DEBUG_MAX_ITEMS = 5
    st.DEV_DEBUG_INCLUDE_RAW_SPECS = True
    st.DEV_DEBUG_INCLUDE_TYPED_SPECS = False
    st.DEV_MODE = False
    norm = {
        "store": "s",
        "raw_specs": {"a": "1", "b": "2"},
        "typed_specs": {"ram_gb": 8},
    }
    v = build_normalized_debug_view(norm, st)
    assert v.get("kind") == "normalized_debug_v1"
    assert "raw_specs_sample" in v
    assert "typed_specs_sample" not in v


def test_build_lifecycle_debug_view_shape() -> None:
    v = build_lifecycle_debug_view(
        {"event_type": "product_found", "payload_hash": "h" * 66},
        {"selected_event_type": "product_found", "allowed": True},
    )
    assert v.get("kind") == "lifecycle_debug_v1"
    assert "event_preview" in v and "decision_preview" in v


def test_build_apply_debug_view_from_dict() -> None:
    v = build_apply_debug_view(
        {
            "event_id": "e",
            "entity_key": "k",
            "payload_hash": "h",
            "success": True,
            "status": "applied",
            "http_status": 200,
            "retryable": False,
            "action": "dry_run",
        }
    )
    assert v.get("kind") == "apply_debug_v1"
    summ = v.get("summary")
    assert isinstance(summ, dict) and summ.get("action") == "dry_run"


def test_build_store_debug_summary_sections() -> None:
    s = Settings(
        _env_file=None,
        DEV_DEBUG_INCLUDE_LIFECYCLE=True,
        DEV_DEBUG_INCLUDE_RAW_SPECS=True,
        DEV_DEBUG_INCLUDE_APPLY_RESULTS=True,
    )
    st = build_store_debug_summary(
        store_name="mediapark",
        normalized={"store": "mediapark", "raw_specs": {}},
        lifecycle_event={"event_type": "product_found"},
        apply_summary={"recognized": True, "success": True},
        settings=s,
    )
    assert st.get("kind") == "store_debug_summary_v1"
    assert "normalized" in st and "lifecycle" in st and "apply" in st
    assert "sections_included" in st
