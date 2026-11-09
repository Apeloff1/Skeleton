import pytest

from skeleton.agents.swarm_exact_lease import lease_exact
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_exact_lease_clock_failure_leaves_runtime_untouched() -> None:
    runtime = SwarmRuntime(clock=lambda: 10.0)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    worker = runtime.worker("w")
    before_events = runtime.events()

    def broken_clock() -> float:
        raise RuntimeError("clock unavailable")

    runtime._clock = broken_clock
    with pytest.raises(RuntimeError, match="clock unavailable"):
        lease_exact(runtime, "w", "task")

    resident = runtime.task("task")
    assert resident is not None and resident.state is TaskState.QUEUED
    assert resident.attempts == 0
    assert resident.leased_to is None
    assert worker is not None and worker.active == set()
    assert worker.accepted == 0
    assert runtime.events() == before_events


def test_exact_lease_uses_one_clock_sample_for_commit() -> None:
    runtime = SwarmRuntime(clock=lambda: 1.0)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    calls = 0

    def single_sample_clock() -> float:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("clock sampled twice")
        return 42.0

    runtime._clock = single_sample_clock
    leased = lease_exact(runtime, "w", "task")

    assert calls == 1
    assert leased.state is TaskState.LEASED
    assert leased.attempts == 1
    assert leased.lease_deadline == 72.0
    worker = runtime.worker("w")
    assert worker is not None
    assert worker.active == {"task"}
    assert worker.accepted == 1
    assert worker.last_seen == 42.0
    assert runtime.events()[-1] == (42.0, "task.leased", "task")
