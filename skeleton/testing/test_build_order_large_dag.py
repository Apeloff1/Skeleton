"""Deterministic, stack-safe build ordering for large world/asset graphs."""
from __future__ import annotations

import pytest

from skeleton.automation.build_order import (
    BuildDependency,
    BuildOrder,
    BuildOrderError,
    BuildStopCondition,
    DependencyKind,
)


def _names(size: int) -> tuple[str, ...]:
    return tuple(f"AIQ.{index:05d}" for index in range(size))


def test_two_thousand_node_hard_chain_does_not_hit_python_recursion_limit():
    nodes = _names(2000)
    edges = tuple(
        BuildDependency(nodes[i], nodes[i + 1], DependencyKind.HARD)
        for i in range(len(nodes) - 1)
    )
    order = BuildOrder(nodes, edges)
    assert order.ready(()) == (nodes[0],)
    assert order.ready(nodes[:-1]) == (nodes[-1],)
    assert order.maturity_allowed(nodes[-1], nodes[:-1])


def test_deep_hard_cycle_is_detected_not_mistaken_for_recursion_failure():
    nodes = _names(1600)
    edges = tuple(
        BuildDependency(nodes[i], nodes[i + 1], DependencyKind.HARD)
        for i in range(len(nodes) - 1)
    ) + (BuildDependency(nodes[-1], nodes[0], DependencyKind.HARD),)
    with pytest.raises(BuildOrderError, match="hard dependency cycle"):
        BuildOrder(nodes, edges)


def test_soft_cycle_does_not_block_unrelated_parallel_work():
    nodes = ("AIQ.001", "AIQ.002", "AIQ.003")
    edges = (
        BuildDependency(nodes[0], nodes[1], DependencyKind.SOFT),
        BuildDependency(nodes[1], nodes[0], DependencyKind.SOFT),
        BuildDependency(nodes[1], nodes[2], DependencyKind.HARD),
    )
    order = BuildOrder(nodes, edges)
    assert order.ready(()) == (nodes[0], nodes[1])
    assert order.ready((nodes[1],)) == (nodes[0], nodes[2])


def test_active_stops_and_hard_prerequisites_remain_sorted_in_snapshot():
    order = BuildOrder(
        ("AIQ.003", "AIQ.001", "AIQ.002"),
        (
            BuildDependency("AIQ.002", "AIQ.003", DependencyKind.HARD),
            BuildDependency("AIQ.001", "AIQ.003", DependencyKind.HARD),
        ),
        (
            BuildStopCondition("AIQ.003", "STOP.Z", True, "z-risk"),
            BuildStopCondition("AIQ.003", "STOP.A", True, "a-risk"),
        ),
    )
    blockers = (
        "dependency:AIQ.001",
        "dependency:AIQ.002",
        "stop:STOP.A:a-risk",
        "stop:STOP.Z:z-risk",
    )
    assert order.blocked_reasons("AIQ.003", ()) == blockers
    assert order.snapshot(()) == (
        ("AIQ.001", False, ()),
        ("AIQ.002", False, ()),
        ("AIQ.003", False, blockers),
    )
    assert order.ready(()) == ("AIQ.001", "AIQ.002")
    assert order.ready(("AIQ.001", "AIQ.002")) == ()
    assert order.blocked_reasons("AIQ.003", ("AIQ.001", "AIQ.002")) == (
        "stop:STOP.A:a-risk",
        "stop:STOP.Z:z-risk",
    )


def test_mirrored_implementations_have_same_build_graph_semantics():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert (root / "skeleton/automation/build_order.py").read_bytes() == (
        root / "skeleton/ai/build/automation/build_order.py"
    ).read_bytes()
