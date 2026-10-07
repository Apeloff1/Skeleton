from __future__ import annotations

import pytest

from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask, TaskState


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_heartbeat_updates_worker_liveness_and_metrics() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock)
    worker = runtime.register_worker("w")
    first_seen = worker.last_seen
    clock.advance(5)

    updated = runtime.heartbeat("w")

    assert updated.last_seen == 1_005.0
    assert updated.last_seen > first_seen
    assert updated.heartbeats == 1
    assert runtime.snapshot().heartbeats == 1


def test_unknown_worker_heartbeat_fails_closed() -> None:
    runtime = SwarmRuntime()
    with pytest.raises(LeaseError):
        runtime.heartbeat("missing")


def test_lease_renewal_extends_deadline() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock, default_lease_seconds=10)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("job", {}))
    leased = runtime.lease("w")[0]
    original = leased.lease_deadline
    clock.advance(3)

    renewed = runtime.renew("w", "job", seconds=20)

    assert renewed.lease_deadline == 1_023.0
    assert renewed.lease_deadline > original
    assert runtime.snapshot().lease_renewals == 1
    assert runtime.worker("w").renewals == 1


def test_renewal_prevents_reap_until_new_deadline() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock, default_lease_seconds=5)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("job", {}))
    runtime.lease("w")
    clock.advance(4)
    runtime.renew("w", "job", seconds=10)
    clock.advance(5)

    assert runtime.reap_expired() == 0
    assert runtime.task("job").state is TaskState.LEASED


def test_cancel_releases_worker_capacity() -> None:
    runtime = SwarmRuntime()
    worker = runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("job", {}))
    runtime.lease("w")

    cancelled = runtime.cancel("job", reason="operator stop")

    assert cancelled.state is TaskState.CANCELLED
    assert cancelled.last_error == "operator stop"
    assert worker.available == 1
    assert runtime.snapshot().cancelled == 1


def test_dead_task_can_be_revived_with_attempt_reset() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("job", {}, max_attempts=1))
    runtime.lease("w")
    runtime.fail("w", "job", "fatal")

    revived = runtime.revive("job", reset_attempts=True)

    assert revived.state is TaskState.QUEUED
    assert revived.attempts == 0
    assert revived.last_error is None
    assert runtime.snapshot().revived == 1
    assert runtime.lease("w")[0].id == "job"


def test_live_task_cannot_be_revived() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("job", {}))
    with pytest.raises(AdmissionError):
        runtime.revive("job")


def test_runtime_rejects_duplicate_worker_without_orphaning_original() -> None:
    runtime = SwarmRuntime()
    original = runtime.register_worker("w", capacity=2)

    with pytest.raises(AdmissionError):
        runtime.register_worker("w", capacity=99)

    assert runtime.worker("w") is original
    assert runtime.worker("w").capacity == 2
