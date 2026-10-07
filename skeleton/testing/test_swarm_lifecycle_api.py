from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_lifecycle_routes import drain_preview, execute_drain, pressure


def test_pressure_endpoint_reports_capacity() -> None:
    runtime = SwarmRuntime(max_tasks=10)
    runtime.submit(SwarmTask("q", {}))
    result = pressure(runtime=runtime)
    assert result["capacity"]["resident"] == 1
    assert result["pressure"]["level"] == "critical"


def test_drain_preview_reports_active_work() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=2))
    runtime.lease("w")
    result = drain_preview("w", runtime=runtime)
    assert result["active_tasks"] == ("a",)
    assert result["requeueable"] == ("a",)


def test_execute_drain_requeues_and_unregisters_worker() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("a", {}, max_attempts=2))
    runtime.lease("w")
    result = execute_drain("w", force=False, runtime=runtime)
    assert result["executed"] is True
    assert runtime.worker("w") is None
    assert runtime.task("a").state.value == "queued"
