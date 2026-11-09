from skeleton.agents.swarm_drain import drain, plan_drain
from skeleton.agents.swarm_pressure import classify_pressure
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_pressure_is_critical_without_available_workers() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("q", {}))
    assert classify_pressure(runtime).level == "critical"


def test_pressure_tracks_resident_capacity() -> None:
    runtime = SwarmRuntime(max_tasks=2)
    runtime.submit(SwarmTask("a", {}))
    runtime.submit(SwarmTask("b", {}))
    assert classify_pressure(runtime).resident_ratio == 1.0


def test_drain_requeues_retryable_live_work() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=2))
    runtime.lease("w")
    plan = plan_drain(runtime, "w")
    assert plan.requeueable == ("a",)
    drain(runtime, "w")
    assert runtime.worker("w") is None
    assert runtime.task("a").state is TaskState.QUEUED


def test_drain_blocks_exhausted_attempt_without_force() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=1))
    runtime.lease("w")
    plan = drain(runtime, "w")
    assert plan.blocked == ("a",)
    assert runtime.worker("w") is not None
