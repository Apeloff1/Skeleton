"""Ancestor checks must walk parents, not children."""

import pytest

from skeleton.intelligence.causal import CausalGraph, CausalVariable


def _graph() -> CausalGraph:
    graph = CausalGraph()
    for name in ("Z", "T", "Y"):
        graph.variables[name] = CausalVariable(name, [0, 1])
    graph.add_edge("Z", "T")
    graph.add_edge("T", "Y")
    return graph


def test_ancestor_follows_parents() -> None:
    graph = _graph()
    assert graph.is_ancestor("Z", "Y") is True
    assert graph.is_ancestor("Y", "Z") is False
    assert graph.is_ancestor("Y", "Y") is False


def test_self_loop_and_duplicate_edges_are_rejected() -> None:
    graph = _graph()
    with pytest.raises(ValueError):
        graph.add_edge("T", "T")
    graph.add_edge("Z", "T")
    assert graph.variables["T"].parents == ["Z"]
