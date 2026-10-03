from skeleton.repo_machine.workgraph import WorkGraph, WorkNode


def _node(identity, prerequisites=(), conflicts=(), confidence=90):
    return WorkNode(
        identity=identity,
        lane="architecture",
        zone=identity,
        priority=10,
        objective=identity,
        conflict_keys=tuple(conflicts),
        prerequisites=tuple(prerequisites),
        evidence=("test",),
        topology_confidence=confidence,
        blast_radius=2,
    )


def test_graph_exposes_stable_fingerprint_and_deep_metrics():
    graph = WorkGraph((
        _node("root", conflicts=("shared",)),
        _node("child", prerequisites=("root",), conflicts=("child",)),
        _node("leaf", prerequisites=("child",)),
    ))
    assert len(graph.fingerprint) == 64
    assert graph.downstream_value("root") >= graph.downstream_value("leaf")
    assert graph.risk_adjusted_influence("root") >= 0
    assert graph.verification_efficiency("root") >= 0
    assert graph.counterfactual_unlock("root") >= 0
    assert graph.decision_margin("root") >= 0


def test_safe_parallel_groups_and_bridge_candidates_are_bounded():
    graph = WorkGraph((
        _node("a", conflicts=("x",)),
        _node("b", conflicts=("x",)),
        _node("c"),
    ))
    groups = graph.safe_parallel_groups(limit=2)
    assert len(groups) <= 2
    assert all(len(group) > 0 for group in groups)
    assert len(graph.bridge_candidates(limit=2)) <= 2
