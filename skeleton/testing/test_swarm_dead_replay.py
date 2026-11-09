import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask


def _dead_runtime() -> HardenedSwarmRuntime:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}, max_attempts=1))
    runtime.lease("w")
    runtime.fail("w", "t", "boom")
    return runtime


def test_dead_task_cannot_bypass_exhausted_retry_budget() -> None:
    runtime = _dead_runtime()
    with pytest.raises(AdmissionError, match="reset_attempts is required"):
        runtime.revive("t")
    assert runtime.task("t").state.value == "dead"


def test_operator_can_explicitly_reset_retry_budget() -> None:
    runtime = _dead_runtime()
    revived = runtime.revive("t", reset_attempts=True)
    assert revived.state.value == "queued"
    assert revived.attempts == 0
    assert runtime.lease("w")[0].attempts == 1
