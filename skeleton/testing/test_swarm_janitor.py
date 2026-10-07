from skeleton.agents.swarm_janitor import reap_stale_workers
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_janitor_requeues_leases_from_stale_workers() -> None:
    now=[0.0]
    runtime=SwarmRuntime(clock=lambda: now[0], default_lease_seconds=100)
    runtime.register_worker("w"); runtime.submit(SwarmTask("t", {})); runtime.lease("w")
    now[0]=50
    result=reap_stale_workers(runtime, stale_after=10)
    assert result.stale_workers == ("w",)
    assert result.released_leases == 1
    assert runtime.task("t").state is TaskState.QUEUED


def test_janitor_respects_limit() -> None:
    now=[0.0]; runtime=SwarmRuntime(clock=lambda: now[0])
    runtime.register_worker("a"); runtime.register_worker("b"); now[0]=100
    result=reap_stale_workers(runtime, stale_after=1, limit=1)
    assert len(result.stale_workers)==1
    assert len(runtime.workers())==1
