from skeleton.repo_machine.workgraph import WorkGraph, WorkNode


def node(
    identity: str,
    *,
    priority: int,
    prerequisites: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    decision_score: int = 0,
) -> WorkNode:
    return WorkNode(
        identity=identity,
        lane="repository-health",
        zone="test",
        priority=priority,
        objective=identity,
        conflict_keys=conflicts,
        prerequisites=prerequisites,
        evidence=(),
        decision_score=decision_score,
    )


def test_frontier_excludes_blocked_nodes_until_prerequisites_complete() -> None:
    graph = WorkGraph(
        (
            node("root", priority=50),
            node("child", priority=100, prerequisites=("root",)),
        )
    )

    assert [item.identity for item in graph.frontier()] == ["root"]
    assert [item.identity for item in graph.frontier(("root",))] == ["child"]


def test_ready_respects_conflicts_and_limit() -> None:
    graph = WorkGraph(
        (
            node("alpha", priority=100, conflicts=("path:a",), decision_score=10),
            node("beta", priority=90, conflicts=("path:a",), decision_score=5),
            node("gamma", priority=80, conflicts=("path:g",), decision_score=1),
        )
    )

    ready = graph.ready(limit=2)

    assert [item.identity for item in ready] == ["alpha", "gamma"]
