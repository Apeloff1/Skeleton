"""Cancellation-aware kernel supervisor regression coverage."""
from __future__ import annotations

from skeleton.kernel.supervisor import Health, Lifecycle, RestartPolicy, Supervisor
from skeleton.shells.cancellation import CancellationReason, CancellationToken


def test_cancelled_node_stops_without_restart() -> None:
    now = [0.0]
    token = CancellationToken(clock=lambda: now[0])
    supervisor = Supervisor(suspect_after=1.0, dead_after=2.0, clock=lambda: now[0])
    supervisor.supervise("worker", RestartPolicy(max_attempts=3), cancellation=token)
    token.cancel(CancellationReason.SHUTDOWN, detail="service shutdown")
    now[0] = 3.0
    transitions = supervisor.sweep()
    assert len(transitions) == 1
    assert transitions[0].action is Lifecycle.STOPPED
    assert transitions[0].backoff_s == 0.0
    status = supervisor.status("worker")
    assert status["state"] == Lifecycle.STOPPED.value
    assert status["attempts"] == 0


def test_cancellation_after_suspect_fences_later_dead_restart() -> None:
    now = [0.0]
    token = CancellationToken(clock=lambda: now[0])
    supervisor = Supervisor(suspect_after=1.0, dead_after=2.0, clock=lambda: now[0])
    supervisor.supervise("worker", cancellation=token)
    now[0] = 1.0
    suspect = supervisor.sweep()
    assert suspect[0].to_health is Health.SUSPECT
    token.cancel(CancellationReason.POLICY)
    now[0] = 3.0
    stopped = supervisor.sweep()
    assert stopped[0].action is Lifecycle.STOPPED
    assert supervisor.status("worker")["attempts"] == 0


def test_cancelled_supervisor_is_terminal_across_future_sweeps() -> None:
    now = [0.0]
    token = CancellationToken(clock=lambda: now[0])
    supervisor = Supervisor(suspect_after=1.0, dead_after=2.0, clock=lambda: now[0])
    supervisor.supervise("worker", cancellation=token)
    token.cancel(CancellationReason.SUPERSEDED)
    assert supervisor.sweep()[0].action is Lifecycle.STOPPED
    now[0] = 100.0
    assert supervisor.sweep() == ()
    assert supervisor.status("worker")["attempts"] == 0


def test_uncancelled_node_preserves_existing_restart_policy() -> None:
    now = [0.0]
    token = CancellationToken(clock=lambda: now[0])
    supervisor = Supervisor(suspect_after=1.0, dead_after=2.0, clock=lambda: now[0])
    supervisor.supervise("worker", RestartPolicy(max_attempts=1), cancellation=token)
    now[0] = 3.0
    transition = supervisor.sweep()[0]
    assert transition.action is Lifecycle.RESTARTING
    assert supervisor.status("worker")["attempts"] == 1
