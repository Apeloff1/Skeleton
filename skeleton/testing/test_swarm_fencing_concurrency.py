from concurrent.futures import ThreadPoolExecutor

from skeleton.agents.swarm_fencing import LeaseFence, fenced_succeed
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import LeaseError, SwarmTask


def test_only_one_parallel_fenced_completion_wins() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    task = runtime.lease("w")[0]
    fence = LeaseFence("t", "w", task.attempts, task.lease_deadline)

    def complete(_: int) -> str:
        try:
            fenced_succeed(runtime, fence)
            return "won"
        except LeaseError:
            return "lost"

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(complete, range(32)))
    assert outcomes.count("won") == 1
    assert outcomes.count("lost") == 31
    assert runtime.task("t").state.value == "succeeded"
