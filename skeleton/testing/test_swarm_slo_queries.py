from skeleton.agents.swarm_queries import query_tasks
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.agents.swarm_slo import SLOPolicy


def test_slo_is_met_for_idle_healthy_runtime() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    result = SLOPolicy().evaluate(runtime)
    assert result["met"] is True


def test_slo_fails_when_queue_has_no_capacity() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {}))
    result = SLOPolicy(min_available_slots=1).evaluate(runtime)
    assert result["met"] is False
    assert result["checks"]["available_slots"] is False


def test_query_tasks_filters_state_capability_and_pages() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("gpu", capabilities=["gpu"], capacity=2)
    runtime.submit(SwarmTask("b", {}, priority=20, required_capabilities=frozenset({"gpu"})))
    runtime.submit(SwarmTask("a", {}, priority=10, required_capabilities=frozenset({"gpu"})))
    runtime.submit(SwarmTask("cpu", {}, priority=1, required_capabilities=frozenset({"cpu"})))
    page = query_tasks(runtime, states=[TaskState.QUEUED], capability="gpu", limit=1)
    assert page.total == 2
    assert [task.id for task in page.items] == ["a"]


def test_query_tasks_offset_is_stable() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("c", {}, priority=3))
    runtime.submit(SwarmTask("a", {}, priority=1))
    runtime.submit(SwarmTask("b", {}, priority=2))
    page = query_tasks(runtime, offset=1, limit=2)
    assert [task.id for task in page.items] == ["b", "c"]
