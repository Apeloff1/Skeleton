import asyncio

import pytest

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY
from core.product_control_plane import ProductControlPlane
from core.product_executor_registry import ExecutorNotRegistered, ProductExecutorRegistry


def test_registry_requires_exact_capability_action_binding(tmp_path):
    registry = ProductExecutorRegistry()
    with pytest.raises(ExecutorNotRegistered, match="no executor registered"):
        registry.require("studio", "build.submit")
    binding = registry.register("studio", "build.submit", lambda operation, payload: True,
                                name="builder", version=3, effect_class="external", replay_safe=True)
    assert binding.name == "builder"
    assert binding.version == 3
    assert binding.effect_class == "external"
    assert binding.replay_safe is True
    assert registry.require("studio", "build.submit") == binding
    assert registry.resolve("studio", "build.unknown") is None
    with pytest.raises(ValueError, match="already registered"):
        registry.register("studio", "build.submit", lambda operation, payload: True)


def test_registry_rejects_invalid_contract_metadata():
    registry = ProductExecutorRegistry()
    with pytest.raises(ValueError, match="version"):
        registry.register("studio", "x", lambda operation, payload: True, version=0)
    with pytest.raises(ValueError, match="effect class"):
        registry.register("studio", "x", lambda operation, payload: True, effect_class="magic")  # type: ignore[arg-type]


def test_control_plane_executes_only_when_exact_executor_exists(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(capability_id="studio", domain="studio", action="build.submit",
                            principal="creator", actor_weight=0, payload={"target": "android"})
    registry = ProductExecutorRegistry()
    assert asyncio.run(plane.execute_registered(operation.outbox_seq, registry)) is False
    assert plane.operations.outbox.pending_count == 1
    seen = []
    registry.register("studio", "build.submit",
                      lambda admitted, payload: seen.append((admitted.id, payload["target"])) or True,
                      name="android-builder", effect_class="external")
    assert asyncio.run(plane.execute_registered(operation.outbox_seq, registry)) is True
    assert seen == [(operation.id, "android")]
    assert plane.operations.outbox.pending_count == 0


def test_registry_snapshot_is_deterministic_and_introspectable():
    registry = ProductExecutorRegistry()
    registry.register("world-forge", "world.create", lambda operation, payload: True, name="world", replay_safe=True)
    registry.register("studio", "project.create", lambda operation, payload: True, name="project", effect_class="state")
    snapshot = registry.snapshot()
    assert snapshot[0]["capability_id"] == "studio"
    assert snapshot[1]["capability_id"] == "world-forge"
    assert snapshot[1]["replay_safe"] is True
    assert snapshot[0]["version"] == 1


def test_default_control_plane_reports_expanded_native_coverage(tmp_path):
    plane = ProductControlPlane(tmp_path)
    coverage = plane.executor_coverage()
    assert coverage["canonical_actions"] == sum(len(item.actions) for item in CANONICAL_PRODUCT_POLICY)
    assert coverage["bound_actions"] == 10
    assert coverage["coverage_pct"] == 47.6
    missing = {item["action"] for item in coverage["missing"]}
    assert {"build.submit", "jeeves.reason", "academy.continue"} <= missing


def test_injected_query_executors_return_real_control_plane_state(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(capability_id="operations", domain="operations", action="ops.runtime",
                            principal="operator", actor_weight=0, payload={})
    assert asyncio.run(plane.execute_registered(operation.outbox_seq)) is True
    result = plane.receipt_result(operation.id)
    assert result["operations"]["capabilities"] == len(plane.operations.kernel.all())
    assert result["sessions"]["capacity"] >= 1
    assert result["receipts"]["version"] == 2


def test_governance_query_executor_is_policy_backed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(capability_id="governance", domain="governance", action="governance.policy",
                            principal="auditor", actor_weight=0, payload={})
    assert asyncio.run(plane.execute_registered(operation.outbox_seq)) is True
    result = plane.receipt_result(operation.id)
    assert result["policy"]["policy_version"] >= 1
    assert len(result["policy"]["charters"]) == len(CANONICAL_PRODUCT_POLICY)


def test_governance_safety_executor_inspects_live_integrity_posture(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(capability_id="governance", domain="governance", action="governance.safety",
                            principal="auditor", actor_weight=0, payload={})
    assert asyncio.run(plane.execute_registered(operation.outbox_seq)) is True
    result = plane.receipt_result(operation.id)["safety"]
    assert result["posture"] in {"healthy", "degraded", "blocked"}
    assert result["canonical_actions"] == 21
    assert result["native_bound_actions"] == 10
    assert result["native_coverage_pct"] == 47.6
    assert result["audit_sequence"] >= 1


def test_canonical_policy_has_no_implicit_executor_requirement():
    registry = ProductExecutorRegistry()
    assert len(registry) == 0
    assert sum(len(item.actions) for item in CANONICAL_PRODUCT_POLICY) > 0
