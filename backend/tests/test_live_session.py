import pytest

from core.evolution_policy import Direction, EvolutionPolicy, MetricSpec
from core.live_session import AdoptionRejected, LiveSession, SessionClosed, SessionState
from core.world_graph import PatchOp, RevisionConflict, WorldGraph, WorldNode, WorldPatch


def _canonical():
    return WorldGraph(
        nodes=(
            WorldNode("world", "world", "World"),
            WorldNode("player", "actor", "Player", parent_id="world"),
        )
    )


def _policy():
    return EvolutionPolicy(
        (MetricSpec("quality", Direction.HIGHER, max_regression_fraction=0.0),),
        minimum_evidence=1,
        evolve_minimum_gain=0.001,
    )


def test_session_overlay_is_isolated_until_adoption():
    canonical = _canonical()
    baseline_hash = canonical.semantic_hash()
    session = LiveSession(canonical, session_id="s1")

    session.apply(
        (PatchOp("set_property", "player", {"key": "hp", "value": 150}),),
        evidence_ids=("test:hp",),
    )
    assert canonical.semantic_hash() == baseline_hash
    assert "hp" not in canonical.get_node("player").properties
    assert session.working_graph.get_node("player").properties["hp"] == 150

    evaluation = session.evaluate(
        _policy(),
        baseline_metrics={"quality": 0.8},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("test:quality",),
    )
    adoption = session.adopt(
        canonical,
        evaluation,
        evidence_ids=("test:quality", "test:hp"),
    )

    assert adoption.evaluation.decision.accepted is True
    assert canonical.get_node("player").properties["hp"] == 150
    assert canonical.semantic_hash() == session.preview()["candidate_hash"]
    assert session.state is SessionState.ADOPTED


def test_rejected_candidate_never_reaches_canonical():
    canonical = _canonical()
    session = LiveSession(canonical)
    session.apply((PatchOp("set_name", "player", {"name": "Hero"}),))
    evaluation = session.evaluate(
        _policy(),
        baseline_metrics={"quality": 0.9},
        candidate_metrics={"quality": 0.8},
        evidence_ids=("bench:regression",),
    )
    assert evaluation.decision.accepted is False
    with pytest.raises(AdoptionRejected, match="rejected"):
        session.adopt(canonical, evaluation)
    assert canonical.get_node("player").name == "Player"


def test_canonical_drift_blocks_adoption():
    canonical = _canonical()
    session = LiveSession(canonical)
    session.apply((PatchOp("set_name", "player", {"name": "Hero"}),))
    evaluation = session.evaluate(
        _policy(),
        baseline_metrics={"quality": 0.8},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("bench:1",),
    )

    canonical.apply(
        WorldPatch(
            canonical.revision,
            (PatchOp("set_property", "world", {"key": "weather", "value": "rain"}),),
        )
    )
    with pytest.raises(RevisionConflict, match="drifted"):
        session.adopt(canonical, evaluation)
    assert canonical.get_node("player").name == "Player"


def test_overlay_change_after_evaluation_requires_reevaluation():
    canonical = _canonical()
    session = LiveSession(canonical)
    session.apply((PatchOp("set_name", "player", {"name": "Hero"}),))
    evaluation = session.evaluate(
        _policy(),
        baseline_metrics={"quality": 0.8},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("bench:1",),
    )
    session.apply(
        (PatchOp("set_property", "player", {"key": "hp", "value": 200}),)
    )
    with pytest.raises(AdoptionRejected, match="changed after evaluation"):
        session.adopt(canonical, evaluation)


def test_rollback_last_restores_overlay_semantics_and_removes_active_patch():
    canonical = _canonical()
    session = LiveSession(canonical)
    base = session.preview()["candidate_hash"]
    session.apply((PatchOp("set_name", "player", {"name": "Hero"}),))
    assert session.preview()["changed"] is True
    session.rollback_last()
    preview = session.preview()
    assert preview["candidate_hash"] == base
    assert preview["changed"] is False
    assert preview["active_patches"] == 0


def test_discard_closes_session_without_touching_canonical():
    canonical = _canonical()
    base = canonical.semantic_hash()
    session = LiveSession(canonical)
    session.apply((PatchOp("set_name", "player", {"name": "Hero"}),))
    discarded = session.discard()
    assert discarded["state"] == "discarded"
    assert canonical.semantic_hash() == base
    with pytest.raises(SessionClosed):
        session.apply((PatchOp("set_name", "player", {"name": "Nope"}),))


def test_evaluation_requires_semantic_change():
    canonical = _canonical()
    session = LiveSession(canonical)
    with pytest.raises(AdoptionRejected, match="no semantic change"):
        session.evaluate(
            _policy(),
            baseline_metrics={"quality": 0.8},
            candidate_metrics={"quality": 0.9},
            evidence_ids=("bench:1",),
        )
