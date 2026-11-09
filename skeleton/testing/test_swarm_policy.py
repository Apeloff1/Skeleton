from __future__ import annotations

import pytest

from skeleton.agents.swarm_admission import AdmissionPolicy, capability_coverage
from skeleton.agents.swarm_idempotency import IdempotencyConflict, IdempotencyRegistry
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.agents.swarm_scheduler import SwarmScheduler


def test_admission_requires_capability_route_when_configured() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("cpu", capabilities=["cpu"])
    task = SwarmTask("gpu-task", {}, required_capabilities=frozenset({"gpu"}))
    decision = AdmissionPolicy(require_capability_route=True).evaluate(runtime, task)
    assert decision.accepted is False
    assert decision.reason == "no worker satisfies required capabilities"


def test_admission_can_fail_closed_without_workers() -> None:
    decision = AdmissionPolicy(reject_when_no_workers=True).evaluate(SwarmRuntime(), SwarmTask("x", {}))
    assert decision.accepted is False


def test_capability_coverage_counts_workers_and_free_slots() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("a", capabilities=["gpu"], capacity=3)
    runtime.register_worker("b", capabilities=["gpu", "cpu"], capacity=2)
    coverage = capability_coverage(runtime, ["gpu", "cpu"])
    assert coverage == {"gpu.workers": 2, "gpu.slots": 5, "cpu.workers": 1, "cpu.slots": 2}


def test_scheduler_prefers_available_reliable_worker() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("busy", capabilities=["gpu"], capacity=1)
    runtime.register_worker("wide", capabilities=["gpu", "cpu"], capacity=3)
    runtime.submit(SwarmTask("occupy", {}, required_capabilities=frozenset({"gpu"})))
    runtime.lease("busy")
    task = SwarmTask("next", {}, required_capabilities=frozenset({"gpu"}))
    assert SwarmScheduler().best_worker(runtime, task).id == "wide"


def test_scheduler_is_deterministic_on_equal_scores() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("b", capabilities=["cpu"])
    runtime.register_worker("a", capabilities=["cpu"])
    ranked = SwarmScheduler().rank(runtime, SwarmTask("x", {}, required_capabilities=frozenset({"cpu"})))
    assert [item.worker_id for item in ranked] == ["a", "b"]


def test_idempotency_returns_same_record_for_same_request() -> None:
    registry = IdempotencyRegistry()
    first = registry.resolve("key", "task", {"x": 1})
    second = registry.resolve("key", "task", {"x": 1})
    assert first == second
    assert len(registry) == 1


def test_idempotency_rejects_key_reuse_with_changed_payload() -> None:
    registry = IdempotencyRegistry()
    registry.resolve("key", "task", {"x": 1})
    with pytest.raises(IdempotencyConflict):
        registry.resolve("key", "task", {"x": 2})


def test_idempotency_registry_evicts_oldest_entry() -> None:
    registry = IdempotencyRegistry(max_entries=2)
    registry.resolve("a", "a", {})
    registry.resolve("b", "b", {})
    registry.resolve("c", "c", {})
    assert registry.get("a") is None
    assert registry.get("c") is not None
