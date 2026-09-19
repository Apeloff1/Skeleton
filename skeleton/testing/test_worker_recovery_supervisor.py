"""Stale ownership recovery and supervision tests."""

from __future__ import annotations

import pytest

from skeleton.shells.queue import QueueState,ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_heartbeat import HeartbeatPolicy,HeartbeatRegistry
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_recovery import RecoveryPolicy,WorkerRecoveryCoordinator
from skeleton.shells.worker_supervisor import SupervisionState,SupervisorPolicy,WorkerFault,WorkerSupervisor


def ident(worker="w",generation=1):
    return WorkerIdentity(worker,generation)


def test_queue_requeue_invalidates_old_claim():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    queue.enqueue(ShellCommand("python"),item_id="job")
    old=queue.claim("w")
    now[0]=10
    recovered=queue.requeue_stale_claims(max_age_seconds=5)
    assert [item.item_id for item in recovered]==["job"]
    assert queue.get("job").state is QueueState.QUEUED
    with pytest.raises(RuntimeError):
        queue.complete(old)
    new=queue.claim("w2")
    queue.complete(new)
    assert queue.get("job").state is QueueState.COMPLETED


def test_queue_recovery_exact_age_boundary():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    queue.enqueue(ShellCommand("python"),item_id="job")
    queue.claim("w")
    now[0]=5
    assert len(queue.requeue_stale_claims(max_age_seconds=5))==1


def test_queue_recovery_owner_filter():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    for value in ("a","b"):
        queue.enqueue(ShellCommand("python"),item_id=value)
    queue.claim("w1");queue.claim("w2")
    now[0]=10
    recovered=queue.requeue_stale_claims(max_age_seconds=5,owner="w1")
    assert [item.item_id for item in recovered]==["a"]
    assert queue.get("b").state is QueueState.CLAIMED


def test_queue_recovery_priority_delta():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    queue.enqueue(ShellCommand("python"),item_id="job",priority=10)
    queue.claim("w")
    now[0]=10
    recovered=queue.requeue_stale_claims(max_age_seconds=5,priority_delta=7)
    assert recovered[0].priority==17


def test_queue_recovery_not_duplicate():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    queue.enqueue(ShellCommand("python"),item_id="job")
    queue.claim("w")
    now[0]=10
    assert len(queue.requeue_stale_claims(max_age_seconds=5))==1
    assert queue.requeue_stale_claims(max_age_seconds=5)==()


def make_recovery(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=ident()
    workers.register(worker)
    beats=HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(late_after_seconds=1,stale_after_seconds=2),
        clock=lambda:now[0],
    )
    beats.beat(worker,sequence=1)
    queue=ShellWorkQueue(clock=lambda:now[0])
    return workers,worker,beats,queue


def test_recovery_coordinator_disables_stale_worker_and_requeues():
    now=[0.0]
    workers,worker,beats,queue=make_recovery(now)
    queue.enqueue(ShellCommand("python"),item_id="job")
    queue.claim(worker.worker_id)
    now[0]=5
    coordinator=WorkerRecoveryCoordinator(
        workers=workers,heartbeats=beats,queue=queue,
        policy=RecoveryPolicy(stale_claim_after_seconds=2),
        clock=lambda:now[0],
    )
    report=coordinator.recover()
    assert report.worker_count==1
    assert report.item_count==1
    assert workers.get("w").enabled is False
    assert queue.get("job").state is QueueState.QUEUED


def test_recovery_does_not_touch_healthy_worker():
    now=[0.0]
    workers,worker,beats,queue=make_recovery(now)
    coordinator=WorkerRecoveryCoordinator(workers=workers,heartbeats=beats,queue=queue,clock=lambda:now[0])
    assert coordinator.recover().worker_count==0
    assert workers.get("w").enabled is True


def test_recover_worker_requires_stale_liveness():
    now=[0.0]
    workers,worker,beats,queue=make_recovery(now)
    coordinator=WorkerRecoveryCoordinator(workers=workers,heartbeats=beats,queue=queue,clock=lambda:now[0])
    with pytest.raises(RuntimeError):
        coordinator.recover_worker(worker)


def test_recovery_can_unregister():
    now=[0.0]
    workers,worker,beats,queue=make_recovery(now)
    now[0]=5
    coordinator=WorkerRecoveryCoordinator(
        workers=workers,heartbeats=beats,queue=queue,
        policy=RecoveryPolicy(disable_stale_workers=False,unregister_stale_workers=True),
        clock=lambda:now[0],
    )
    recovery=coordinator.recover_worker(worker)
    assert recovery.unregistered
    assert workers.find("w") is None
    assert beats.latest("w") is None


def test_recovery_policy_rejects_conflicting_actions():
    with pytest.raises(ValueError):
        RecoveryPolicy(disable_stale_workers=True,unregister_stale_workers=True)


@pytest.mark.parametrize("field", ["max_faults", "max_restarts"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_supervisor_policy_rejects_invalid_integer_limits(field,value):
    kwargs={field:value}
    with pytest.raises(ValueError):
        SupervisorPolicy(**kwargs)


@pytest.mark.parametrize(
    "field",
    ["fault_window_seconds", "quarantine_seconds", "restart_window_seconds"],
)
@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_supervisor_policy_rejects_invalid_time_windows(field,value):
    kwargs={field:value}
    with pytest.raises(ValueError):
        SupervisorPolicy(**kwargs)


@pytest.mark.parametrize("observed_at", [-1, True, float("nan"), float("inf")])
def test_worker_fault_rejects_invalid_timestamp(observed_at):
    with pytest.raises(ValueError):
        WorkerFault(observed_at,"failure")


@pytest.mark.parametrize("kind", ["", "   ", "bad\x00kind", 123])
def test_worker_fault_rejects_invalid_kind(kind):
    with pytest.raises(ValueError):
        WorkerFault(0.0,kind)


@pytest.mark.parametrize("detail", ["bad\x00detail", 123])
def test_worker_fault_rejects_invalid_detail(detail):
    with pytest.raises(ValueError):
        WorkerFault(0.0,"failure",detail)


def setup_supervisor(now,policy=None):
    workers=WorkerRegistry(clock=lambda:now[0])
    item=ident()
    workers.register(item)
    supervisor=WorkerSupervisor(workers,policy=policy,clock=lambda:now[0])
    supervisor.attach(item)
    return workers,item,supervisor


def test_supervisor_attach_and_running():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    assert supervisor.mark_running(item).state is SupervisionState.RUNNING


def test_supervisor_rejects_invalid_running_transition():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    supervisor.mark_running(item)
    with pytest.raises(RuntimeError):
        supervisor.mark_running(item)


def test_supervisor_fault_degrades():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    supervisor.mark_running(item)
    state=supervisor.fault(item,"command")
    assert state.state is SupervisionState.DEGRADED


def test_supervisor_fault_budget_quarantines_and_disables():
    now=[0.0]
    policy=SupervisorPolicy(max_faults=2,quarantine_seconds=10)
    workers,item,supervisor=setup_supervisor(now,policy)
    supervisor.mark_running(item)
    supervisor.fault(item,"x")
    state=supervisor.fault(item,"x")
    assert state.state is SupervisionState.QUARANTINED
    assert workers.get("w").enabled is False


def test_supervisor_fault_window_forgets_old_faults():
    now=[0.0]
    policy=SupervisorPolicy(max_faults=2,fault_window_seconds=5)
    _,item,supervisor=setup_supervisor(now,policy)
    supervisor.mark_running(item)
    supervisor.fault(item,"x")
    now[0]=6
    state=supervisor.fault(item,"x")
    assert state.state is SupervisionState.DEGRADED
    assert len(state.faults)==1


def test_supervisor_release_quarantine_requires_expiry():
    now=[0.0]
    policy=SupervisorPolicy(max_faults=1,quarantine_seconds=5)
    workers,item,supervisor=setup_supervisor(now,policy)
    supervisor.fault(item,"x")
    with pytest.raises(RuntimeError):
        supervisor.release_quarantine(item)
    now[0]=5
    state=supervisor.release_quarantine(item)
    assert state.state is SupervisionState.STARTING
    assert workers.get("w").enabled is True


def test_supervisor_restart_budget_quarantines():
    now=[0.0]
    policy=SupervisorPolicy(max_restarts=1)
    workers,item,supervisor=setup_supervisor(now,policy)
    supervisor.restart(item)
    state=supervisor.restart(item)
    assert state.state is SupervisionState.QUARANTINED
    assert not workers.get("w").enabled


def test_supervisor_cannot_restart_quarantined_worker():
    now=[0.0]
    policy=SupervisorPolicy(max_faults=1,quarantine_seconds=10)
    workers,item,supervisor=setup_supervisor(now,policy)
    state=supervisor.fault(item,"x")
    assert state.state is SupervisionState.QUARANTINED
    assert workers.get("w").enabled is False

    with pytest.raises(RuntimeError,match="cannot restart"):
        supervisor.restart(item)

    assert supervisor.require(item).state is SupervisionState.QUARANTINED
    assert workers.get("w").enabled is False


def test_supervisor_cannot_restart_stopped_worker():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    supervisor.begin_stop(item)
    supervisor.stopped(item)

    with pytest.raises(RuntimeError,match="cannot restart"):
        supervisor.restart(item)

    assert supervisor.require(item).state is SupervisionState.STOPPED


def test_supervisor_cannot_fault_stopped_worker():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    supervisor.begin_stop(item)
    supervisor.stopped(item)

    with pytest.raises(RuntimeError,match="cannot record faults"):
        supervisor.fault(item,"late-fault")

    assert supervisor.require(item).state is SupervisionState.STOPPED


def test_supervisor_stop_path():
    now=[0.0]
    _,item,supervisor=setup_supervisor(now)
    supervisor.mark_running(item)
    assert supervisor.begin_stop(item).state is SupervisionState.STOPPING
    assert supervisor.stopped(item).state is SupervisionState.STOPPED


def test_supervisor_generation_guard():
    now=[0.0]
    workers,item,supervisor=setup_supervisor(now)
    newer=ident(generation=2)
    workers.replace(newer)
    supervisor.attach(newer)
    with pytest.raises(RuntimeError):
        supervisor.require(item)
