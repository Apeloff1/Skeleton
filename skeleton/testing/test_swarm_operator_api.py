from __future__ import annotations

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_operator_routes import autoscale, compact_snapshot, hot_workers, normalized_snapshot, overview


def test_operator_overview_contains_health_autoscale_retention() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("a", {}))
    result = overview(stale_after=90.0, runtime=runtime)
    assert {"health", "autoscale", "retention", "workers"}.issubset(result)


def test_operator_hot_workers_detects_saturation() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("a", {}))
    runtime.lease("w")
    assert hot_workers(utilization=1.0, runtime=runtime)["workers"] == ("w",)


def test_operator_autoscale_reports_delta() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=1)
    for i in range(6):
        runtime.submit(SwarmTask(str(i), {}))
    result = autoscale(target_tasks_per_slot=2.0, min_slots=1, max_slots=10, runtime=runtime)
    assert result["desired_slots"] == 3
    assert result["delta"] == 2


def test_operator_snapshot_is_normalized() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("b", {}))
    runtime.submit(SwarmTask("a", {}))
    state = normalized_snapshot(runtime=runtime)
    assert [item["id"] for item in state["tasks"]] == ["a", "b"]


def test_operator_compact_snapshot_reports_pruning() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("done", {}))
    task = runtime.lease("w")[0]
    runtime.succeed("w", task.id)
    state = compact_snapshot(max_terminal_tasks=0, runtime=runtime)
    assert state["tasks"] == []
    assert state["maintenance"]["pruned_terminal_tasks"] == 1
