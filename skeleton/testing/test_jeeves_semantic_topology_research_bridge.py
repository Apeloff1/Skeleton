from __future__ import annotations

from skeleton.jeeves.agent.frontier_control_plane import (
    FrontierCognitiveControlPlane,
)
from skeleton.jeeves.agent.semantic_frontier import LensInteractionKind
from skeleton.jeeves.agent.semantic_lens_topology import SemanticLensTopology
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
from skeleton.jeeves.agent.semantic_research_bridge import (
    SemanticTopologyResearchBridge,
)
from skeleton.jeeves.agent.semantic_topology_learning import (
    SemanticTopologyLearningLab,
    TopologyBridgePolicy,
    TopologyBridgePrediction,
)


def _system():
    registry = MaximalSemanticRegistry()
    topology = SemanticLensTopology(registry)
    candidate = topology.bridge_candidates(
        limit=1,
        minimum_score=0.0,
    )[0]
    policy = TopologyBridgePolicy(
        minimum_trials=4,
        minimum_independent_runs=2,
        minimum_domains=2,
        minimum_negative_controls=2,
        maximum_brier=0.25,
        maximum_ece=0.25,
        minimum_empirical_rate=0.75,
        maximum_negative_control_positive_rate=0.25,
        reject_brier=0.50,
        reject_ece=0.50,
        reject_empirical_rate=0.25,
    )
    lab = SemanticTopologyLearningLab(topology, policy=policy)
    control = FrontierCognitiveControlPlane(clock=lambda: 100.0)
    bridge = SemanticTopologyResearchBridge(lab, control)
    return candidate, lab, control, bridge


def _declare_and_resolve(
    lab: SemanticTopologyLearningLab,
    candidate,
    index: int,
    *,
    probability: float,
    outcome: bool,
    domain: str,
    run: str,
    negative_control: bool = False,
) -> None:
    prediction = TopologyBridgePrediction(
        prediction_id=f"research-bridge-prediction:{index}",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=probability,
        domain=domain,
        independent_run=run,
        predicted_at=float(index * 2),
        negative_control=negative_control,
        source_forecast_ids=(f"research-forecast:{index}",),
        evidence_ids=(f"research-evidence:{index}",),
    )
    lab.declare(prediction)
    lab.resolve(
        prediction.prediction_id,
        outcome=outcome,
        observed_at=float(index * 2 + 1),
        outcome_evidence_ids=(f"outcome-evidence:{index}",),
    )


def _promote(lab: SemanticTopologyLearningLab, candidate) -> None:
    for index, domain, run in (
        (1, "film", "run-a"),
        (2, "film", "run-b"),
        (3, "game", "run-c"),
        (4, "game", "run-d"),
    ):
        _declare_and_resolve(
            lab,
            candidate,
            index,
            probability=0.90,
            outcome=True,
            domain=domain,
            run=run,
        )
    for index, domain, run in (
        (101, "film", "control-a"),
        (102, "game", "control-b"),
    ):
        _declare_and_resolve(
            lab,
            candidate,
            index,
            probability=0.05,
            outcome=False,
            domain=domain,
            run=run,
            negative_control=True,
        )


def test_topology_research_bridge_preserves_obligation_provenance_in_agenda() -> None:
    candidate, _, control, bridge = _system()

    update = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )
    obligation = next(
        item
        for item in update.obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )
    agenda_items = control.research_agenda.items_for_obligation(
        obligation.obligation_id
    )

    assert agenda_items
    assert update.frontier.obligations
    assert set(update.topology_agenda_ids) == {
        item.agenda_id for item in agenda_items
    }
    for item in agenda_items:
        assert (
            item.metadata["obligation_fingerprint"]
            == obligation.fingerprint
        )
        metadata = item.metadata["obligation_metadata"]
        assert metadata["semantic_topology"] is True
        assert metadata["candidate_id"] == candidate.candidate_id
        assert (
            metadata["candidate_fingerprint"]
            == obligation.metadata["candidate_fingerprint"]
        )


def test_repeated_topology_research_refresh_reuses_agenda_identity() -> None:
    _, _, control, bridge = _system()

    first = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )
    second = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )

    assert first.topology_agenda_ids == second.topology_agenda_ids
    for agenda_id in first.topology_agenda_ids:
        item = control.research_agenda.item(agenda_id)
        assert item.recurrence_count == 2


def test_promoted_bridge_leaves_current_debt_without_auto_resolving_agenda() -> None:
    candidate, lab, control, bridge = _system()
    before = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )
    obligation = next(
        item
        for item in before.obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )
    prior_items = control.research_agenda.items_for_obligation(
        obligation.obligation_id
    )
    assert prior_items

    _promote(lab, candidate)

    after = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )
    assert candidate.candidate_id not in {
        item.metadata["candidate_id"]
        for item in after.obligations
    }
    assert not set(after.topology_agenda_ids).intersection(
        {item.agenda_id for item in prior_items}
    )

    # Topology promotion is bounded semantic authority, not a research
    # completion certificate. Existing agenda debt remains assurance-gated.
    for item in control.research_agenda.items_for_obligation(
        obligation.obligation_id
    ):
        assert item.status.value != "resolved"
        assert "completion_certificate_id" not in item.metadata


def test_rejected_bridge_requires_explicit_opt_in_to_research_frontier() -> None:
    candidate, lab, _, bridge = _system()
    for index, domain, run in (
        (1, "film", "bad-a"),
        (2, "film", "bad-b"),
        (3, "game", "bad-c"),
        (4, "game", "bad-d"),
    ):
        _declare_and_resolve(
            lab,
            candidate,
            index,
            probability=0.90,
            outcome=False,
            domain=domain,
            run=run,
        )
    for index, domain, run in (
        (101, "film", "bad-control-a"),
        (102, "game", "bad-control-b"),
    ):
        _declare_and_resolve(
            lab,
            candidate,
            index,
            probability=0.05,
            outcome=False,
            domain=domain,
            run=run,
            negative_control=True,
        )

    default_update = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
    )
    assert candidate.candidate_id not in {
        item.metadata["candidate_id"]
        for item in default_update.obligations
    }

    explicit_update = bridge.refresh(
        limit=100,
        minimum_candidate_score=0.0,
        include_rejected=True,
    )
    rejected = next(
        item
        for item in explicit_update.obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )
    assert rejected.metadata["status"] == "rejected"
    assert rejected.contradiction_strength > 0.0
