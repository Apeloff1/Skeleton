import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_fencing import LeaseFence, fenced_succeed
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import LeaseError, SwarmTask
from skeleton.api.swarm_fence_routes import FencedCompletion, succeed


def test_stale_attempt_cannot_complete_reissued_task() -> None:
    clock = [0.0]
    runtime = HardenedSwarmRuntime(default_lease_seconds=1.0, clock=lambda: clock[0])
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}, max_attempts=3))
    first = runtime.lease("w")[0]
    stale = LeaseFence("t", "w", first.attempts, first.lease_deadline)
    clock[0] = 2.0
    runtime.reap_expired()
    second = runtime.lease("w")[0]
    assert second.attempts == first.attempts + 1
    with pytest.raises(LeaseError, match="stale lease attempt"):
        fenced_succeed(runtime, stale)
    assert runtime.task("t").state.value == "leased"


def test_current_attempt_can_complete() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    task = runtime.lease("w")[0]
    result = fenced_succeed(runtime, LeaseFence("t", "w", task.attempts, task.lease_deadline))
    assert result.state.value == "succeeded"


def test_fenced_api_rejects_stale_attempt() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    task = runtime.lease("w")[0]
    try:
        succeed("w", "t", FencedCompletion(attempt=task.attempts + 1), runtime=runtime)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "stale lease attempt" in exc.detail
    else:
        raise AssertionError("stale fenced completion was accepted")
