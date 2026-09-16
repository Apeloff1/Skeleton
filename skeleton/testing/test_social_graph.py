from __future__ import annotations

import pytest

from skeleton.social.graph import Interaction, InteractionLog, SocialGraph


def _connect(graph: SocialGraph, from_agent: str, to_agent: str) -> None:
    graph.record_interaction(from_agent, to_agent, "collaboration", 1.0)


def test_get_network_honors_requested_depth() -> None:
    graph = SocialGraph()
    _connect(graph, "alpha", "beta")
    _connect(graph, "beta", "gamma")
    _connect(graph, "gamma", "delta")

    depth_one = graph.get_network("alpha", depth=1)
    assert depth_one == {
        "alpha": ["beta"],
        "beta": ["gamma"],
    }

    depth_two = graph.get_network("alpha", depth=2)
    assert depth_two == {
        "alpha": ["beta"],
        "beta": ["gamma"],
        "gamma": ["delta"],
    }
    assert "delta" not in depth_two


def test_get_network_terminates_on_cycles_without_reexpanding_nodes() -> None:
    graph = SocialGraph()
    _connect(graph, "alpha", "beta")
    _connect(graph, "beta", "alpha")
    _connect(graph, "beta", "gamma")

    network = graph.get_network("alpha", depth=4)

    assert network == {
        "alpha": ["beta"],
        "beta": ["alpha", "gamma"],
        "gamma": [],
    }


def test_get_network_non_positive_depth_preserves_direct_neighbors() -> None:
    graph = SocialGraph()
    _connect(graph, "alpha", "beta")

    assert graph.get_network("alpha", depth=0) == {"alpha": ["beta"]}
    assert graph.get_network("alpha", depth=-1) == {"alpha": ["beta"]}


def test_interaction_log_enforces_small_capacity_and_rebuilds_indices() -> None:
    log = InteractionLog(max_size=3)

    for sequence in range(5):
        log.append(
            Interaction(
                from_agent=f"agent-{sequence}",
                to_agent="sink",
                interaction_type="message" if sequence % 2 else "task",
                outcome=1.0,
                timestamp=float(sequence),
                context={"sequence": sequence},
            )
        )

    assert [item.context["sequence"] for item in log.query()] == [2, 3, 4]
    assert [item.context["sequence"] for item in log.query(interaction_type="task")] == [2, 4]
    assert log.stats() == {"total": 3, "types": 2, "agents": 4}


def test_interaction_log_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        InteractionLog(max_size=0)

    with pytest.raises(ValueError, match="greater than zero"):
        InteractionLog(max_size=-1)
