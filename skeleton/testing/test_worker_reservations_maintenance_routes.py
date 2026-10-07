"""Reservations, maintenance, routing, failure, and lifecycle tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_capacity import CapacityDemand,WorkerCapacity,WorkerCapacityCatalog
from skeleton.shells.worker_failure import WorkerFailureKind,WorkerFailureLog
from skeleton.shells.worker_heartbeat import HeartbeatRegistry
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry,WorkerRole
from skeleton.shells.worker_lifecycle import LifecycleState,WorkerLifecycle
from skeleton.shells.worker_maintenance import WorkerMaintenance
from skeleton.shells.worker_reservations import ReservationConflict,WorkerReservations
from skeleton.shells.worker_routing import WorkerRoute,WorkerRoutes


def setup_reservations(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    beats.beat(worker,sequence=1)
    capacities=WorkerCapacityCatalog()
    capacities.set("w",WorkerCapacity(max_inflight=2,max_weight=4))
    return worker,WorkerReservations(workers,beats,capacities,clock=lambda:now[0])


def test_reservation_consumes_capacity():
    now=[0.0]
    worker,reservations=setup_reservations(now)
    reservations.reserve(worker,CapacityDemand(1,2))
    reservations.reserve(worker,CapacityDemand(1,2))
    with pytest.raises(ReservationConflict):
        reservations.reserve(worker,CapacityDemand(1,1))


def test_reservation_weight_bound():
    now=[0.0]
    worker,reservations=setup_reservations(now)
    reservations.reserve(worker,CapacityDemand(1,4))
    with pytest.raises(ReservationConflict):
        reservations.reserve(worker,CapacityDemand(1,1))


def test_reservation_expiry_releases_capacity():
    now=[0.0]
    worker,reservations=setup_reservations(now)
    first=reservations.reserve(worker,CapacityDemand(2,4),ttl_seconds=5)
    now[0]=5
    second=reservations.reserve(worker,CapacityDemand(2,4))
    assert second!=first


def test_reservation_release_is_token_safe():
    now=[0.0]
    worker,reservations=setup_reservations(now)
    item=reservations.reserve(worker)
    assert reservations.release(item)
    assert not reservations.release(item)


def test_reservation_requires_healthy_worker():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    reservations=WorkerReservations(workers,beats,WorkerCapacityCatalog(),clock=lambda:now[0])
    with pytest.raises(ReservationConflict):
        reservations.reserve(worker)


def test_maintenance_active_and_prune():
    now=[0.0]
    windows=WorkerMaintenance(clock=lambda:now[0])
    windows.add("w",delay_seconds=5,duration_seconds=10)
    assert windows.available("w")
    now[0]=5
    assert not windows.available("w")
    now[0]=15
    assert windows.available("w")
    assert windows.prune()==1


def test_maintenance_capacity_bound():
    windows=WorkerMaintenance(max_windows=1)
    windows.add("a",duration_seconds=1)
    with pytest.raises(RuntimeError):
        windows.add("b",duration_seconds=1)


def test_routes_defaults():
    routes=WorkerRoutes.defaults()
    assert routes.resolve("build").required_role is WorkerRole.BUILDER
    assert routes.resolve("test").required_role is WorkerRole.TESTER


def test_routes_principal_prefix():
    routes=WorkerRoutes()
    routes.set(WorkerRoute("secure",requirements=routes.defaults().resolve("build"),principal_prefix="team:"))
    assert routes.resolve("secure",principal="team:a")
    with pytest.raises(RuntimeError):
        routes.resolve("secure",principal="other:a")


def test_routes_disabled():
    routes=WorkerRoutes()
    routes.set(WorkerRoute("x",requirements=WorkerRoutes.defaults().resolve("build"),enabled=False))
    with pytest.raises(RuntimeError):
        routes.resolve("x")


def test_failure_log_filtering():
    now=[0.0]
    log=WorkerFailureLog(clock=lambda:now[0])
    log.record("w",1,WorkerFailureKind.COMMAND)
    now[0]=5
    log.record("w",1,WorkerFailureKind.TIMEOUT,retryable=True)
    assert log.count(worker_id="w")==2
    assert log.count(kind=WorkerFailureKind.TIMEOUT)==1
    assert log.count(since=1)==1


def test_failure_log_is_bounded():
    log=WorkerFailureLog(max_items=2)
    log.record("w",1,WorkerFailureKind.COMMAND)
    log.record("w",1,WorkerFailureKind.COMMAND)
    log.record("w",1,WorkerFailureKind.TIMEOUT)
    assert len(log.recent())==2


def test_lifecycle_happy_path():
    life=WorkerLifecycle()
    life.transition(LifecycleState.REGISTERED)
    life.transition(LifecycleState.STARTING)
    life.transition(LifecycleState.READY)
    life.transition(LifecycleState.DRAINING)
    life.transition(LifecycleState.STOPPING)
    life.transition(LifecycleState.STOPPED)
    assert life.state is LifecycleState.STOPPED


def test_lifecycle_rejects_invalid_jump():
    life=WorkerLifecycle()
    with pytest.raises(RuntimeError):
        life.transition(LifecycleState.READY)


def test_lifecycle_failure_path():
    life=WorkerLifecycle()
    transition=life.fail("bootstrap")
    assert transition.current is LifecycleState.FAILED
    life.request_stop()
    assert life.state is LifecycleState.STOPPING


def test_lifecycle_history_bound():
    life=WorkerLifecycle(max_history=2)
    life.transition(LifecycleState.REGISTERED)
    life.transition(LifecycleState.STARTING)
    life.transition(LifecycleState.READY)
    assert len(life.history())==2
