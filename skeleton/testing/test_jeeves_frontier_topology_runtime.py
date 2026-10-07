from __future__ import annotations

from skeleton.jeeves.agent.frontier_control_plane import (
    FrontierCognitiveControlPlane,
)
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.semantic_frontier import LensInteractionKind


def _runtime() -> FrontierJeevesAgentRuntime:
    provider = DeterministicProvider(("unused",))
    return FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter((provider,)),
        cortex_enabled=False,
    )


def test_frontier_runtime_declares_and_settles_canonical_topology_experiment() -> None:
    runtime = _runtime()
    candidate = runtime.semantic_plane.topology.bridge_candidates(
        limit=1,
        minimum_score=0.0,
    )[0]

    prediction = runtime.declare_semantic_topology_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="frontier-run",
        predicted_at=10.0,
        source_forecast_ids=("forecast:frontier",),
    )

    assert runtime.unresolved_semantic_topology_predictions(
        candidate_id=candidate.candidate_id
    ) == (prediction,)

    report = runtime.resolve_semantic_topology_prediction(
        prediction.prediction_id,
        outcome=True,
        observed_at=11.0,
        outcome_evidence_ids=("evidence:frontier-outcome",),
    )

    assert report.candidate_id == candidate.candidate_id
    assert report.trial_count == 1
    assert runtime.unresolved_semantic_topology_predictions(
        candidate_id=candidate.candidate_id
    ) == ()


def test_frontier_runtime_topology_state_round_trip() -> None:
    source = _runtime()
    candidate = source.semantic_plane.topology.bridge_candidates(
        limit=1,
        minimum_score=0.0,
    )[0]
    prediction = source.declare_semantic_topology_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.CONDITIONS,
        predicted_probability=0.65,
        domain="game",
        independent_run="state-run",
        predicted_at=20.0,
    )
    source.resolve_semantic_topology_prediction(
        prediction.prediction_id,
        outcome=True,
        observed_at=21.0,
    )
    state = source.export_semantic_topology_learning_state()

    target = _runtime()
    restored = target.restore_semantic_topology_learning_state(
        state.as_json()
    )

    assert restored.fingerprint == source.semantic_plane.topology_learning.snapshot().fingerprint
    assert (
        target.export_semantic_topology_learning_state().fingerprint
        == state.fingerprint
    )


def test_frontier_runtime_maps_topology_debt_into_research_program() -> None:
    runtime = _runtime()
    control = FrontierCognitiveControlPlane(clock=lambda: 100.0)

    update = runtime.map_semantic_topology_research(
        control,
        limit=20,
        minimum_candidate_score=0.0,
    )

    assert update.obligations
    assert update.topology_agenda_ids
    assert update.frontier.fingerprint
    assert update.agenda.fingerprint
    for agenda_id in update.topology_agenda_ids:
        item = control.research_agenda.item(agenda_id)
        metadata = item.metadata["obligation_metadata"]
        assert metadata["semantic_topology"] is True


def test_frontier_runtime_topology_summary_exposes_custody_invariants() -> None:
    runtime = _runtime()
    summary = runtime.semantic_topology_learning_summary()

    assert summary["prediction_count"] == 0
    assert summary["trial_count"] == 0
    assert (
        summary["invariants"]["outcomes_require_predeclared_predictions"]
        is True
    )
    assert (
        summary["invariants"]["each_prediction_resolves_at_most_once"]
        is True
    )
    assert (
        summary["invariants"]["learned_bridges_never_create_evidence"]
        is True
    )
