from skeleton.repo_machine.workgraph import WorkGraph, WorkNode

def _node(identity, prerequisites=(), conflicts=(), confidence=90, verification=True):
    return WorkNode(identity=identity,lane="architecture",zone=identity,priority=10,objective=identity,conflict_keys=tuple(conflicts),prerequisites=tuple(prerequisites),evidence=("test",),verification_paths=("verify",) if verification else (),topology_confidence=confidence,blast_radius=2)

def test_graph_exposes_stable_fingerprint_and_deep_metrics():
    graph=WorkGraph((_node("root",conflicts=("shared",)),_node("child",prerequisites=("root",),conflicts=("child",)),_node("leaf",prerequisites=("child",))))
    assert len(graph.fingerprint)==64
    assert graph.downstream_value("root")>=graph.downstream_value("leaf")
    assert graph.risk_adjusted_influence("root")>=0
    assert graph.verification_efficiency("root")>=0
    assert graph.counterfactual_unlock("root")>=0
    assert graph.decision_margin("root")>=0

def test_safe_parallel_groups_and_bridge_candidates_are_bounded():
    graph=WorkGraph((_node("a",conflicts=("x",)),_node("b",conflicts=("x",)),_node("c")))
    groups=graph.safe_parallel_groups(limit=2)
    assert len(groups)<=2
    assert all(len(group)>0 for group in groups)
    assert len(graph.bridge_candidates(limit=2))<=2

def test_decision_surface_is_bounded_and_consistent():
    graph=WorkGraph((_node("a",conflicts=("x",),confidence=100),_node("b",conflicts=("y",),confidence=80),_node("c",prerequisites=("a",))))
    surface=graph.decision_surface(limit=2)
    assert len(surface)<=2
    assert all(0<=row["risk_adjusted_influence"]<=100 for row in surface)
    assert all(0<=row["verification_efficiency"]<=100 for row in surface)
    assert all(row["counterfactual_unlock"]>=0 for row in surface)
    assert all(row["decision_margin"]>=0 for row in surface)
    assert {row["identity"] for row in surface}<={"a","b"}

def test_parallel_batch_surface_is_bounded_deterministic_and_actionable():
    graph=WorkGraph((_node("a",conflicts=("x",),confidence=100),_node("b",conflicts=("y",),confidence=80),_node("c",conflicts=("x",),verification=False)))
    first=graph.parallel_batch_surface(limit=2)
    second=graph.parallel_batch_surface(limit=2)
    assert first==second
    assert len(first)<=2
    assert all(1<=row["size"] for row in first)
    assert all(0<=row["risk_adjusted_influence"]<=100 for row in first)
    assert all(0<=row["counterfactual_unlock"]<=100 for row in first)
    assert all(0<=row["verification_coverage"]<=100 for row in first)
    assert all(0<=row["pressure"]<=100 for row in first)

def test_parallel_batch_surface_rejects_unsafe_limits():
    graph=WorkGraph((_node("a"),))
    for limit in (0,9):
        try:
            graph.parallel_batch_surface(limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe batch limit accepted")
