from __future__ import annotations

from domain.operational_policy import RunOperationalStatus, StoreOperationalStatus

from infrastructure.observability.status_snapshot import serialize_run_status, serialize_store_status


def test_serialize_store_excludes_non_json_safe_types():
    st = StoreOperationalStatus(
        store_name="s",
        status="degraded",
        alerts=[],
        breached_thresholds=[],
        counters={"a": 1.0},
        notes=["n"],
    )
    d = serialize_store_status(st)
    assert d["store_name"] == "s"
    assert "raw_traces" not in d
    assert isinstance(d["alerts"], list)


def test_serialize_run_compact():
    run = RunOperationalStatus(
        run_id="r",
        status="healthy",
        store_statuses=[
            StoreOperationalStatus(store_name="s1", status="healthy"),
        ],
        global_alerts=[],
    )
    d = serialize_run_status(run)
    assert d["run_id"] == "r"
    assert len(d["store_statuses"]) == 1
    assert "traces" not in d
