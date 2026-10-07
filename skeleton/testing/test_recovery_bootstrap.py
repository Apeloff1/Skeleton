from __future__ import annotations

import pytest

from skeleton.resilience.recovery_bootstrap import (
    DEFAULT_UNAVAILABLE_CONTROL_PLANES,
    RecoveryBootstrapError,
    RecoveryDependencyGraph,
    RecoveryNode,
    build_default_recovery_graph,
)


def test_default_graph_is_acyclic_and_dependency_first() -> None:
    graph = build_default_recovery_graph()
    order = graph.topological_order()

    assert order.index("local_trust_root") < order.index("recovery_identity")
    assert order.index("recovery_identity") < order.index("cold_authority_store")
    assert order.index("cold_authority_store") < order.index("repair_executor")
    assert order.index("normal_scheduler") < order.index("normal_queue")
    assert order.index("repair_executor") < order.index("normal_runtime")


def test_default_safe_mode_excludes_normal_control_planes() -> None:
    graph = build_default_recovery_graph()
    order = graph.dependency_reduced_order(
        unavailable=DEFAULT_UNAVAILABLE_CONTROL_PLANES,
    )

    assert order == (
        "local_trust_root",
        "recovery_identity",
        "cold_authority_store",
        "repair_executor",
    )
    assert set(order).isdisjoint(DEFAULT_UNAVAILABLE_CONTROL_PLANES)


def test_safe_mode_rejects_hidden_dependency_on_normal_scheduler() -> None:
    graph = RecoveryDependencyGraph(
        (
            RecoveryNode("root", safe_mode=True, cold_restore_order=1),
            RecoveryNode("normal_scheduler"),
            RecoveryNode(
                "repair",
                dependencies=("root", "normal_scheduler"),
                safe_mode=True,
                cold_restore_order=2,
            ),
        )
    )

    with pytest.raises(RecoveryBootstrapError, match="safe mode depends"):
        graph.dependency_reduced_order(unavailable={"normal_scheduler"})


def test_dependency_cycle_fails_at_graph_construction() -> None:
    with pytest.raises(RecoveryBootstrapError, match="cycle"):
        RecoveryDependencyGraph(
            (
                RecoveryNode("a", dependencies=("b",)),
                RecoveryNode("b", dependencies=("a",)),
            )
        )


def test_cold_restore_order_is_explicit_and_dependency_safe() -> None:
    graph = build_default_recovery_graph()
    assert graph.cold_restore_order() == (
        "local_trust_root",
        "recovery_identity",
        "cold_authority_store",
        "repair_executor",
    )


def test_cold_restore_rejects_dependency_inversion() -> None:
    graph = RecoveryDependencyGraph(
        (
            RecoveryNode("root", cold_restore_order=2),
            RecoveryNode(
                "identity",
                dependencies=("root",),
                cold_restore_order=1,
            ),
        )
    )
    with pytest.raises(RecoveryBootstrapError, match="dependency order"):
        graph.cold_restore_order()


def test_unknown_unavailable_dependency_is_rejected() -> None:
    graph = build_default_recovery_graph()
    with pytest.raises(RecoveryBootstrapError, match="unknown nodes"):
        graph.dependency_reduced_order(unavailable={"not-a-node"})


def test_graph_description_is_deterministic() -> None:
    first = build_default_recovery_graph().describe()
    second = build_default_recovery_graph().describe()
    assert first == second


def test_safe_mode_requires_at_least_one_survivor() -> None:
    graph = RecoveryDependencyGraph(
        (
            RecoveryNode("normal_scheduler"),
            RecoveryNode("normal_queue", dependencies=("normal_scheduler",)),
        )
    )
    with pytest.raises(RecoveryBootstrapError, match="no safe-mode"):
        graph.dependency_reduced_order(
            unavailable={"normal_scheduler", "normal_queue"}
        )
