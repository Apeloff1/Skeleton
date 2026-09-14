import asyncio

import pytest

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY
from core.product_control_plane import ProductControlPlane
from core.product_executor_registry import ExecutorNotRegistered, ProductExecutorRegistry


def test_registry_requires_exact_capability_action_binding(tmp_path):
    registry = ProductExecutorRegistry()
    with pytest.raises(ExecutorNotRegistered, match="no executor registered"):
        registry.require("studio", "build.submit")

    binding = registry.register("studio", "build.submit", lambda operation, payload: True, name="builder")
    assert binding.name == "builder"
    assert registry.require("studio", "build.submit") == binding
    assert registry.resolve("studio", "build.unknown") is None
    with pytest.raises(ValueError, match="already registered"):
        registry.register("studio", "build.submit", lambda operation, payload: True)


def test_control_plane_executes_only_when_exact_executor_exists(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(
        capability_id="studio",
        domain="studio",
        action="build.submit",
        principal="creator",
        actor_weight=0,
        payload={"target": "android"},
    )
    registry = ProductExecutorRegistry()

    assert asyncio.run(plane.execute_registered(operation.outbox_seq, registry)) is False
    assert plane.operations.outbox.pending_count == 1

    seen = []
    registry.register(
        "studio",
        "build.submit",
        lambda admitted, payload: seen.append((admitted.id, payload["target"])) or True,
        name="android-builder",
    )
    assert asyncio.run(plane.execute_registered(operation.outbox_seq, registry)) is True
    assert seen == [(operation.id, "android")]
    assert plane.operations.outbox.pending_count == 0


def test_registry_snapshot_is_deterministic():
    registry = ProductExecutorRegistry()
    registry.register("world-forge", "world.create", lambda operation, payload: True, name="world")
    registry.register("studio", "project.create", lambda operation, payload: True, name="project")
    snapshot = registry.snapshot()
    assert snapshot[0]["capability_id"] == "studio"
    assert snapshot[1]["capability_id"] == "world-forge"


def test_canonical_policy_has_no_implicit_executor_requirement():
    # Governance and execution are separate seams: every canonical action may be
    # admitted by policy, but none is executable until an adapter is registered.
    registry = ProductExecutorRegistry()
    assert len(registry) == 0
    assert sum(len(item.actions) for item in CANONICAL_PRODUCT_POLICY) > 0
