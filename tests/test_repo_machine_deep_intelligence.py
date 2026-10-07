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


def test_decision_surface_is_bounded_and_consistent():
    graph = WorkGraph((
        _node("a", conflicts=("x",), confidence=100),
        _node("b", conflicts=("y",), confidence=80),
        _node("c", prerequisites=("a",)),
    ))
    surface = graph.decision_surface(limit=2)
    assert len(surface) <= 2
    assert all(0 <= row["risk_adjusted_influence"] <= 100 for row in surface)
    assert all(0 <= row["verification_efficiency"] <= 100 for row in surface)
    assert all(row["counterfactual_unlock"] >= 0 for row in surface)
    assert all(row["decision_margin"] >= 0 for row in surface)
    assert {row["identity"] for row in surface} <= {"a", "b"}


def test_counterfactual_surface_is_bounded_deterministic_and_actionable():
    graph = WorkGraph((
        _node("root", conflicts=("shared",)),
        _node("child", prerequisites=("root",), conflicts=("child",)),
        _node("side", conflicts=("side",)),
        _node("leaf", prerequisites=("child",)),
    ))
    first = graph.counterfactual_surface(limit=3)
    second = graph.counterfactual_surface(limit=3)
    assert first == second
    assert len(first) <= 3
    assert all(0 <= row["pressure_reduction"] <= 100 for row in first)
    assert all(0 <= row["projected_pressure"] <= 100 for row in first)
    assert all(0 <= row["newly_unblocked_count"] <= 16 for row in first)
    assert all(len(row["newly_unblocked"]) <= 16 for row in first)
    assert all(0 <= row["risk_adjusted_influence"] <= 100 for row in first)
    assert all(0 <= row["strategic_value"] <= 100 for row in first)
    assert all(row["identity"] in {"root", "side"} for row in first)


def test_counterfactual_surface_rejects_unbounded_limits():
    graph = WorkGraph((_node("a"),))
    for limit in (0, 65):
        try:
            graph.counterfactual_surface(limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError("counterfactual surface must reject unsafe limits")
