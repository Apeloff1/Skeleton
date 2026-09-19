"""Additional worker-plane edge cases and safety regressions."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_events import WorkerEvent,WorkerEvents
from skeleton.shells.worker_failure import WorkerFailureKind,WorkerFailureLog
from skeleton.shells.worker_maintenance import WorkerMaintenance
from skeleton.shells.worker_policy import WorkerPlanePolicy
from skeleton.shells.worker_routing import WorkerRoute,WorkerRoutes
from skeleton.shells.worker_affinity import JobRequirements
from skeleton.shells.worker_identity import WorkerRole


@pytest.mark.parametrize("max_workers",[0,-1,True])
def test_policy_rejects_bad_worker_capacity(max_workers):
    with pytest.raises(ValueError):
        WorkerPlanePolicy(max_workers=max_workers)


def test_policy_narrow_rejects_journal_widening():
    parent=WorkerPlanePolicy(max_journal_events=10)
    with pytest.raises(ValueError):
        parent.narrow(max_journal_events=11)


def test_event_payload_is_copied():
    payload={"x":1}
    event=WorkerEvent(1,"x","w",1,0,payload)
    payload["x"]=2
    assert event.data["x"]==1


def test_events_after_sequence():
    events=WorkerEvents()
    for kind in ("a","b","c"):events.emit(kind)
    assert [item.kind for item in events.events(after_sequence=1)]==["b","c"]


def test_events_worker_filter():
    events=WorkerEvents()
    events.emit("x",worker_id="a")
    events.emit("x",worker_id="b")
    assert [item.worker_id for item in events.events(worker_id="a")]==["a"]


def test_maintenance_snapshot_sorted():
    now=[0.0]
    maintenance=WorkerMaintenance(clock=lambda:now[0])
    maintenance.add("b",delay_seconds=10,duration_seconds=1)
    maintenance.add("a",delay_seconds=5,duration_seconds=1)
    assert [item.worker_id for item in maintenance.snapshot()]==["a","b"]


def test_maintenance_rejects_negative_delay():
    with pytest.raises(ValueError):
        WorkerMaintenance().add("w",delay_seconds=-1,duration_seconds=1)


def test_failure_log_detail_bound():
    log=WorkerFailureLog()
    with pytest.raises(ValueError):
        log.record("w",1,WorkerFailureKind.INTERNAL,detail="x"*513)


def test_routes_replace_existing_without_capacity_growth():
    routes=WorkerRoutes(max_routes=1)
    routes.set(WorkerRoute("x",JobRequirements(required_role=WorkerRole.BUILDER)))
    routes.set(WorkerRoute("x",JobRequirements(required_role=WorkerRole.TESTER)))
    assert routes.resolve("x").required_role is WorkerRole.TESTER


def test_routes_capacity_bound():
    routes=WorkerRoutes(max_routes=1)
    routes.set(WorkerRoute("x",JobRequirements()))
    with pytest.raises(RuntimeError):
        routes.set(WorkerRoute("y",JobRequirements()))
