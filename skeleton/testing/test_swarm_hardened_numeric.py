import math

import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask, TaskState


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"max_tasks": True}, "max_tasks"),
        ({"max_tasks": 1.5}, "max_tasks"),
        ({"max_workers": True}, "max_workers"),
        ({"max_workers": 2.5}, "max_workers"),
        ({"default_lease_seconds": math.nan}, "default_lease_seconds"),
        ({"default_lease_seconds": math.inf}, "default_lease_seconds"),
        ({"max_lease_seconds": math.nan}, "max_lease_seconds"),
        ({"max_lease_seconds": math.inf}, "max_lease_seconds"),
    ],
)
def test_hardened_runtime_rejects_invalid_numeric_configuration(kwargs, match) -> None:
    with pytest.raises(ValueError, match=match):
        HardenedSwarmRuntime(**kwargs)


def test_worker_capacity_and_task_attempts_require_real_integers() -> None:
    runtime = HardenedSwarmRuntime()

    with pytest.raises(ValueError, match="capacity"):
        runtime.register_worker("bad", capacity=True)
    assert runtime.worker("bad") is None

    with pytest.raises(ValueError, match="max_attempts"):
        runtime.submit(SwarmTask("bad-task", {}, max_attempts=True))
    assert runtime.task("bad-task") is None


def test_lease_limit_rejects_boolean_without_mutating_queue() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("task", {}))

    with pytest.raises(ValueError, match="limit"):
        runtime.lease("w", limit=True)

    assert runtime.task("task").state is TaskState.QUEUED
    assert runtime.worker("w").active == set()


@pytest.mark.parametrize("seconds", [math.nan, math.inf, -math.inf, 0.0, -1.0])
def test_renew_rejects_nonfinite_or_nonpositive_duration_without_mutation(seconds) -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("task", {}))
    leased = runtime.lease("w", limit=1)[0]

    with pytest.raises(ValueError, match="lease renewal duration"):
        runtime.renew("w", "task", seconds=seconds)

    assert runtime.task("task") == leased


@pytest.mark.parametrize("stale_after", [math.nan, math.inf, -math.inf, 0.0, -1.0])
def test_health_rejects_invalid_staleness_window(stale_after) -> None:
    runtime = HardenedSwarmRuntime()
    with pytest.raises(ValueError, match="stale_after"):
        runtime.health(stale_after=stale_after)


def test_nonfinite_clock_fails_before_worker_state_is_published() -> None:
    runtime = HardenedSwarmRuntime(clock=lambda: math.nan)

    with pytest.raises(RuntimeError, match="clock must return a finite number"):
        runtime.register_worker("w")

    assert runtime.worker("w") is None
    assert runtime.events() == ()
