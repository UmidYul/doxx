from __future__ import annotations

from infrastructure.sync.runtime_identity_bridge import RuntimeIdentityBridge


def test_remember_and_get_runtime_ids():
    b = RuntimeIdentityBridge()
    b.remember_sync_result("s:1", "L1", "P1", "created", "sha256:abc")
    assert b.get_runtime_ids("s:1") == {"crm_listing_id": "L1", "crm_product_id": "P1"}
    assert b.has_listing_id("s:1") is True
    assert b.has_product_id("s:1") is True
    assert b.get_last_payload_hash("s:1") == "sha256:abc"


def test_partial_crm_response_preserves_previous_ids():
    b = RuntimeIdentityBridge()
    b.remember_sync_result("s:1", "L1", "P1", "created", "h1")
    b.remember_sync_result("s:1", None, None, "updated", "h2")
    ids = b.get_runtime_ids("s:1")
    assert ids["crm_listing_id"] == "L1"
    assert ids["crm_product_id"] == "P1"
