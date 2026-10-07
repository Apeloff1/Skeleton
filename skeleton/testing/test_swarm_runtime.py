from __future__ import annotations

import pytest

from skeleton.agents.swarm_runtime import (
    AdmissionError,
    LeaseError,
    SwarmRuntime,
    SwarmTask,
    TaskState,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_priority_and_fifo_order_are_stable() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capabilities={"cpu"}, capacity=3)
    runtime.submit(SwarmTask("a", {}, priority=20, required_capabilities=frozenset({"cpu"})))
    runtime.submit(SwarmTask("b", {}, priority=10, required_capabilities=frozenset({"cpu"})))
    runtime.submit(SwarmTask("c", {}, priority=10, required_capabilities=frozenset({"cpu"})))
    assert [task.id for task in runtime.lease("w")] == ["b", "c", "a"]
    assert runtime.snapshot().leased == 3


def test_capability_mismatch_does_not_starve_matching_work() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("cpu", capabilities={"cpu"}, capacity=2)
    runtime.submit(SwarmTask("gpu-first", {}, priority=1, required_capabilities=frozenset({"gpu"})))
    runtime.submit(SwarmTask("cpu-next", {}, priority=2, required_capabilities=frozenset({"cpu"})))
    assert [task.id for task in runtime.lease("cpu")] == ["cpu-next"]
    assert runtime.task("gpu-first").state is TaskState.QUEUED


def test_worker_capacity_is_enforced_and_released() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("a", {}))
    runtime.submit(SwarmTask("b", {}))
    first = runtime.lease("w")
    assert len(first) == 1
    assert runtime.lease("w") == []
    runtime.succeed("w", first[0].id)
    assert len(runtime.lease("w")) == 1


def test_failure_requeues_until_attempt_budget_is_exhausted() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=2))
    runtime.fail("w", runtime.lease("w")[0].id, "boom")
    dead = runtime.fail("w", runtime.lease("w")[0].id, "boom again")
    assert dead.state is TaskState.DEAD
    assert dead.attempts == 2
    assert runtime.snapshot().retries == 1


def test_lease_expiry_requeues_and_releases_worker() -> None:
    clock = Clock()
    runtime = SwarmRuntime(default_lease_seconds=5, clock=clock)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=3))
    runtime.lease("w")
    clock.advance(5)
    assert runtime.reap_expired() == 1
    assert worker.active == set()
    assert runtime.task("a").state is TaskState.QUEUED
    assert runtime.snapshot().expired_leases == 1


def test_expired_final_attempt_becomes_dead() -> None:
    clock = Clock()
    runtime = SwarmRuntime(default_lease_seconds=1, clock=clock)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=1))
    runtime.lease("w")
    clock.advance(2)
    runtime.reap_expired()
    assert runtime.task("a").state is TaskState.DEAD


def test_unregister_requeues_live_work() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("a", {}))
    runtime.submit(SwarmTask("b", {}))
    runtime.lease("w")
    assert runtime.unregister_worker("w") == 2
    assert runtime.snapshot().queued == 2


def test_wrong_worker_cannot_complete_foreign_lease() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("a")
    runtime.register_worker("b")
    runtime.submit(SwarmTask("job", {}))
    runtime.lease("a")
    with pytest.raises(LeaseError):
        runtime.succeed("b", "job")


def test_admission_is_fail_closed() -> None:
    runtime = SwarmRuntime(max_tasks=1)
    runtime.submit(SwarmTask("a", {}))
    with pytest.raises(AdmissionError):
        runtime.submit(SwarmTask("b", {}))
    with pytest.raises(AdmissionError):
        SwarmRuntime().submit(SwarmTask("", {}))


def test_duplicate_task_ids_are_rejected() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("same", {}))
    with pytest.raises(AdmissionError):
        runtime.submit(SwarmTask("same", {}))


def test_error_messages_are_bounded() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    runtime.lease("w")
    task = runtime.fail("w", "a", "x" * 10_000)
    assert len(task.last_error) == 2_000


def test_event_log_records_lifecycle() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}))
    runtime.lease("w")
    runtime.succeed("w", "a")
    assert [kind for _, kind, _ in runtime.events()] == [
        "worker.registered",
        "task.submitted",
        "task.leased",
        "task.succeeded",
    ]
