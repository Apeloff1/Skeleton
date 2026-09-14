import pytest

from core.evolution_policy import ChangeMode, Direction, EvolutionPolicy, MetricSpec
from core.jeeves_control_plane import (
    ApprovalRequired,
    JeevesControlPlane,
    UnknownPendingEvolution,
)
from core.jeeves_execution_kernel import BudgetExceeded, JeevesRuntime
from core.jeeves_memory import MemoryBank
from core.model_router import ModelEndpoint, ModelRouter, PrivacyLevel, RouteRequest
from core.world_graph import PatchOp, RevisionConflict, WorldGraph, WorldNode, WorldPatch


def _graph():
    return WorldGraph(
        nodes=(
            WorldNode("world", "world", "World"),
            WorldNode("player", "actor", "Player", parent_id="world"),
        )
    )


def _policy():
    return EvolutionPolicy(
        (MetricSpec("quality", Direction.HIGHER, max_regression_fraction=0.0),),
        minimum_evidence=2,
        evolve_minimum_gain=0.001,
        mutation_minimum_gain=0.10,
    )


def _plane(*, max_pending=8):
    return JeevesControlPlane(
        runtime=JeevesRuntime(capacity=2, queue_capacity=4),
        router=ModelRouter(telemetry_alpha=1.0),
        memory=MemoryBank(per_agent_capacity=32),
        policy=_policy(),
        max_pending=max_pending,
    )


def _quality_change(value=100):
    return (PatchOp("set_property", "player", {"key": "quality", "value": value}),)


def test_accepted_evolution_auto_adopts_and_records_memory():
    graph = _graph()
    plane = _plane()

    outcome = plane.evolve_world(
        graph,
        _quality_change(100),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.8},
        evidence_ids=("bench:1", "test:1"),
    )

    assert outcome.status == "adopted"
    assert outcome.accepted is True
    assert outcome.adopted is True
    assert graph.get_node("player").properties["quality"] == 100
    assert graph.revision == 1
    assert plane.pending() == ()
    assert len(outcome.memory_ids) == 2
    profile = plane.memory.profile("jeeves")
    assert profile["count"] == 2
    assert profile["reflection_count"] == 1
    assert any(row["kind"] == "jeeves.session.adopted" for row in outcome.evidence)
    assert any(row["kind"] == "execution.finish" for row in outcome.evidence)


def test_rejected_candidate_never_mutates_canonical_world():
    graph = _graph()
    baseline = graph.semantic_hash()
    plane = _plane()

    outcome = plane.evolve_world(
        graph,
        _quality_change(20),
        baseline_metrics={"quality": 0.8},
        candidate_metrics={"quality": 0.4},
        evidence_ids=("bench:bad", "test:bad"),
    )

    assert outcome.status == "rejected"
    assert outcome.accepted is False
    assert outcome.adopted is False
    assert graph.semantic_hash() == baseline
    assert graph.revision == 0
    assert plane.pending() == ()
    assert any("quality" in item for item in outcome.evaluation.decision.violations)
    assert any(row["kind"] == "execution.finish" for row in outcome.evidence)


def test_mutation_is_held_for_explicit_approval_then_can_be_adopted():
    graph = _graph()
    plane = _plane()

    outcome = plane.evolve_world(
        graph,
        _quality_change(130),
        baseline_metrics={"quality": 1.0},
        candidate_metrics={"quality": 1.3},
        evidence_ids=("bench:mutation", "test:mutation"),
        mode=ChangeMode.MUTATE,
        auto_adopt=True,
        mutation_approved=False,
    )

    assert outcome.status == "approval_required"
    assert outcome.accepted is True
    assert outcome.adopted is False
    assert graph.revision == 0
    assert len(plane.pending()) == 1
    session_id = outcome.session_id

    with pytest.raises(ApprovalRequired):
        plane.adopt_pending(session_id, graph, approved=False)
    assert graph.revision == 0

    adopted = plane.adopt_pending(session_id, graph, approved=True)
    assert graph.revision == 1
    assert graph.get_node("player").properties["quality"] == 130
    assert adopted.adoption.evaluation.decision.mode is ChangeMode.MUTATE
    assert any(row["kind"] == "execution.finish" for row in adopted.evidence)
    assert plane.pending() == ()


def test_accepted_evolution_can_be_left_pending_and_discarded():
    graph = _graph()
    plane = _plane()

    outcome = plane.evolve_world(
        graph,
        _quality_change(90),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("bench:pending", "test:pending"),
        auto_adopt=False,
    )
    assert outcome.status == "accepted_pending"
    assert graph.revision == 0
    assert plane.pending()[0].session_id == outcome.session_id

    discarded = plane.discard_pending(outcome.session_id)
    assert discarded["state"] == "discarded"
    assert plane.pending() == ()
    with pytest.raises(UnknownPendingEvolution):
        plane.discard_pending(outcome.session_id)


def test_pending_adoption_fails_closed_when_canonical_world_drifted():
    graph = _graph()
    plane = _plane()
    outcome = plane.evolve_world(
        graph,
        _quality_change(90),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("bench:pending", "test:pending"),
        auto_adopt=False,
    )

    graph.apply(
        WorldPatch(
            graph.revision,
            (PatchOp("set_property", "player", {"key": "external", "value": True}),),
        )
    )
    with pytest.raises(RevisionConflict):
        plane.adopt_pending(outcome.session_id, graph)

    # Conflict does not silently destroy the candidate; it can still be inspected/discarded.
    assert plane.pending()[0].session_id == outcome.session_id
    plane.discard_pending(outcome.session_id)


def test_model_route_is_attached_to_evolution_evidence():
    graph = _graph()
    plane = _plane()
    plane.register_model(
        ModelEndpoint(
            endpoint_id="local-code",
            provider="local",
            model="code-model",
            capabilities=frozenset({"code", "world"}),
            privacy_ceiling=PrivacyLevel.LOCAL_ONLY,
            local=True,
            nominal_latency_ms=25,
        )
    )
    plane.register_model(
        ModelEndpoint(
            endpoint_id="remote-code",
            provider="remote",
            model="remote-model",
            capabilities=frozenset({"code", "world"}),
            privacy_ceiling=PrivacyLevel.PUBLIC,
            nominal_latency_ms=10,
        )
    )

    outcome = plane.evolve_world(
        graph,
        _quality_change(101),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.8},
        evidence_ids=("bench:route", "test:route"),
        route_request=RouteRequest(
            "world_edit",
            required_capabilities=frozenset({"world"}),
            privacy=PrivacyLevel.LOCAL_ONLY,
        ),
    )

    assert outcome.route is not None
    assert outcome.route.selected.endpoint_id == "local-code"
    assert "remote-code" in outcome.route.rejected
    assert any(row["kind"] == "jeeves.route.selected" for row in outcome.evidence)
    recalled = plane.memory.recall("jeeves", "local-code", limit=4)
    assert any("local-code" in row.record.content for row in recalled)


def test_model_observation_changes_control_plane_route():
    plane = _plane()
    plane.register_model(
        ModelEndpoint("a", "alpha", "a", nominal_latency_ms=100)
    )
    plane.register_model(
        ModelEndpoint("b", "beta", "b", nominal_latency_ms=100)
    )
    plane.observe_model("a", ok=False, quality=0.1, latency_ms=500, observed_at=1)
    plane.observe_model("b", ok=True, quality=1.0, latency_ms=10, observed_at=1)

    assert plane.route(RouteRequest("chat")).selected.endpoint_id == "b"


def test_execution_step_budget_stops_before_canonical_adoption():
    graph = _graph()
    baseline = graph.semantic_hash()
    plane = _plane()

    # route omitted: open + patch consume two steps; evaluation would require a third.
    with pytest.raises(BudgetExceeded):
        plane.evolve_world(
            graph,
            _quality_change(100),
            baseline_metrics={"quality": 0.5},
            candidate_metrics={"quality": 0.9},
            evidence_ids=("bench:budget", "test:budget"),
            max_steps=2,
        )
    assert graph.semantic_hash() == baseline
    assert graph.revision == 0


def test_pending_capacity_discards_oldest_overlay_without_touching_canonical():
    graph = _graph()
    plane = _plane(max_pending=1)

    first = plane.evolve_world(
        graph,
        (PatchOp("set_property", "player", {"key": "candidate", "value": 1}),),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.8},
        evidence_ids=("bench:1", "test:1"),
        auto_adopt=False,
    )
    second = plane.evolve_world(
        graph,
        (PatchOp("set_property", "player", {"key": "candidate", "value": 2}),),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.9},
        evidence_ids=("bench:2", "test:2"),
        auto_adopt=False,
    )

    pending = plane.pending()
    assert len(pending) == 1
    assert pending[0].session_id == second.session_id
    with pytest.raises(UnknownPendingEvolution):
        plane.discard_pending(first.session_id)
    assert graph.revision == 0


def test_snapshot_exposes_runtime_router_and_pending_without_live_objects():
    graph = _graph()
    plane = _plane()
    outcome = plane.evolve_world(
        graph,
        _quality_change(99),
        baseline_metrics={"quality": 0.5},
        candidate_metrics={"quality": 0.8},
        evidence_ids=("bench:snapshot", "test:snapshot"),
        auto_adopt=False,
    )

    snapshot = plane.snapshot()
    assert set(snapshot) == {"runtime", "router", "pending"}
    assert snapshot["pending"][0]["session_id"] == outcome.session_id
    assert snapshot["pending"][0]["mode"] == "evolve"
