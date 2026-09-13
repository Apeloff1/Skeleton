from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.api.swarm_lifecycle_routes import reap_stale


def test_reap_stale_api_evicts_stale_workers() -> None:
    now=[0.0]
    runtime=SwarmRuntime(clock=lambda: now[0])
    runtime.register_worker("w")
    now[0]=100
    result=reap_stale(stale_after=10, requeue=True, limit=100, runtime=runtime)
    assert result["result"]["stale_workers"] == ("w",)
    assert result["snapshot"]["workers"] == 0
