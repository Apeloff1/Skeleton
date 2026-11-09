"""Focused lifecycle regressions for the bounded shell core slice."""

from __future__ import annotations

import pytest

from skeleton.shells.cancellation import CancellationReason, CancellationRegistry, CancellationToken
from skeleton.shells.runner import ShellCommand
from skeleton.shells.service_state import ShellServicePhase, ShellServiceState
from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistry
from skeleton.shells.worker_schedule import WorkerSchedule
from skeleton.shells.worker_supervisor import SupervisionState, SupervisorPolicy, WorkerFault, WorkerSupervisor


@pytest.mark.parametrize("timeout", [-1, True, float("nan"), float("inf"), "1"])
def test_cancellation_wait_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        CancellationToken().wait(timeout)


@pytest.mark.parametrize("detail", ["bad\x00detail", 123])
def test_cancellation_rejects_invalid_detail(detail):
    with pytest.raises(ValueError):
        CancellationToken().cancel(detail=detail)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_cancellation_registry_rejects_invalid_capacity(value):
    with pytest.raises(ValueError):
        CancellationRegistry(max_tokens=value)


@pytest.mark.parametrize("key", ["", "   ", "bad\x00key", 123])
def test_cancellation_registry_rejects_invalid_key(key):
    with pytest.raises(ValueError):
        CancellationRegistry().create(key)


def test_cancellation_is_idempotent():
    token = CancellationToken()
    assert token.cancel(CancellationReason.SHUTDOWN)
    assert not token.cancel(CancellationReason.USER)
    assert token.snapshot().reason is CancellationReason.SHUTDOWN


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_service_state_rejects_invalid_history_bound(value):
    with pytest.raises(ValueError):
        ShellServiceState(max_history=value)


@pytest.mark.parametrize("reason", ["bad\x00reason", 123])
def test_service_state_rejects_invalid_transition_reason(reason):
    state = ShellServiceState()
    with pytest.raises(ValueError):
        state.transition(ShellServicePhase.STARTING, reason=reason)


def test_service_state_valid_lifecycle():
    state = ShellServiceState()
    state.transition(ShellServicePhase.STARTING)
    state.transition(ShellServicePhase.READY)
    state.transition(ShellServicePhase.STOPPING)
    state.transition(ShellServicePhase.STOPPED)
    assert state.phase is ShellServicePhase.STOPPED


def _supervisor(policy=None):
    now = [0.0]
    workers = WorkerRegistry(clock=lambda: now[0])
    identity = WorkerIdentity("worker-a", 1)
    workers.register(identity)
    supervisor = WorkerSupervisor(workers, policy=policy, clock=lambda: now[0])
    supervisor.attach(identity)
    return now, workers, identity, supervisor


@pytest.mark.parametrize("field", ["max_faults", "max_restarts"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_supervisor_policy_rejects_invalid_integer_limits(field, value):
    with pytest.raises(ValueError):
        SupervisorPolicy(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["fault_window_seconds", "quarantine_seconds", "restart_window_seconds"],
)
@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_supervisor_policy_rejects_invalid_time_windows(field, value):
    with pytest.raises(ValueError):
        SupervisorPolicy(**{field: value})


@pytest.mark.parametrize("observed_at", [-1, True, float("nan"), float("inf")])
def test_worker_fault_rejects_invalid_timestamp(observed_at):
    with pytest.raises(ValueError):
        WorkerFault(observed_at, "failure")


def test_supervisor_cannot_restart_quarantined_worker():
    now, workers, identity, supervisor = _supervisor(
        SupervisorPolicy(max_faults=1, quarantine_seconds=10)
    )
    state = supervisor.fault(identity, "failure")
    assert state.state is SupervisionState.QUARANTINED
    assert workers.get(identity.worker_id).enabled is False

    with pytest.raises(RuntimeError, match="cannot restart"):
        supervisor.restart(identity)

    assert supervisor.require(identity).state is SupervisionState.QUARANTINED
    assert workers.get(identity.worker_id).enabled is False


def test_supervisor_cannot_restart_stopped_worker():
    _, _, identity, supervisor = _supervisor()
    supervisor.begin_stop(identity)
    supervisor.stopped(identity)

    with pytest.raises(RuntimeError, match="cannot restart"):
        supervisor.restart(identity)

    assert supervisor.require(identity).state is SupervisionState.STOPPED


def test_supervisor_release_quarantine_reenables_after_expiry():
    now, workers, identity, supervisor = _supervisor(
        SupervisorPolicy(max_faults=1, quarantine_seconds=5)
    )
    supervisor.fault(identity, "failure")
    now[0] = 5
    state = supervisor.release_quarantine(identity)
    assert state.state is SupervisionState.STARTING
    assert workers.get(identity.worker_id).enabled is True


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_schedule_rejects_invalid_capacity(value):
    with pytest.raises(ValueError):
        WorkerSchedule(max_items=value)


@pytest.mark.parametrize("delay", [-1, True, float("nan"), float("inf"), "1"])
def test_schedule_rejects_invalid_delay(delay):
    schedule = WorkerSchedule()
    with pytest.raises(ValueError):
        schedule.schedule("x", ShellCommand("python"), delay_seconds=delay)


@pytest.mark.parametrize("priority", [True, 1.5, "1"])
def test_schedule_rejects_invalid_priority(priority):
    schedule = WorkerSchedule()
    with pytest.raises(ValueError):
        schedule.schedule("x", ShellCommand("python"), priority=priority)


def test_schedule_release_is_deterministic():
    now = [0.0]
    schedule = WorkerSchedule(clock=lambda: now[0])
    schedule.schedule("later", ShellCommand("python"), delay_seconds=5, priority=20)
    schedule.schedule("first", ShellCommand("python"), delay_seconds=5, priority=10)
    now[0] = 5
    ready = schedule.pop_ready(limit=10)
    assert [item.schedule_id for item in ready] == ["first", "later"]
