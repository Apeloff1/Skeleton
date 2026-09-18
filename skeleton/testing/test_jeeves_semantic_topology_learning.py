from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.epistemic_frontier import EpistemicFrontierEngine
from skeleton.jeeves.agent.frontier_control_plane import (
    FrontierCognitiveControlPlane,
)
from skeleton.jeeves.agent.semantic_frontier import (
    LensCompositionEngine,
    LensInteractionKind,
    LensInteractionRule,
    default_interaction_rules,
)
from skeleton.jeeves.agent.semantic_lens_topology import SemanticLensTopology
from skeleton.jeeves.agent.semantic_lenses import (
    LensSelection,
    SemanticFinding,
    SemanticObservation,
    SemanticRole,
)
from skeleton.jeeves.agent.semantic_maximal import (
    MaximalLensRouter,
    MaximalSemanticRegistry,
)
from skeleton.jeeves.agent.semantic_plane import (
    SemanticLensPlane,
    SemanticPlanePolicy,
)
from skeleton.jeeves.agent.semantic_topology_learning import (
    SemanticTopologyLearningLab,
    SemanticTopologyLearningState,
    TopologyBridgePolicy,
    TopologyBridgePrediction,
    TopologyBridgeStatus,
    TopologyBridgeTrial,
)
from skeleton.jeeves.agent.types import AgentContractError


def test_system_role_is_available_to_system_oriented_lenses() -> None:
    registry = MaximalSemanticRegistry()

    assert SemanticRole.SYSTEM.value == "system"
    assert registry.get("mechanics_dynamics_aesthetics").role is SemanticRole.SYSTEM
    assert any(
        spec.role is SemanticRole.SYSTEM
        for spec in registry.all()
    )


class _FixedRouter(MaximalLensRouter):
    def __init__(
        self,
        registry: MaximalSemanticRegistry,
        selection: LensSelection,
    ) -> None:
        super().__init__(registry)
        self._selection = selection

    def select_maximal(
        self,
        observations,
        **kwargs,
    ) -> LensSelection:
        return self._selection


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
    return registry, topology, candidate, lab


def _trial(
    lab: SemanticTopologyLearningLab,
    candidate,
    index: int,
    *,
    kind: LensInteractionKind = LensInteractionKind.REINFORCES,
    probability: float = 0.90,
    outcome: bool = True,
    domain: str = "film",
    run: str | None = None,
    negative_control: bool = False,
) -> TopologyBridgeTrial:
    prediction = TopologyBridgePrediction(
        prediction_id=(
            f"bridge-prediction:{kind.value}:{index}"
        ),
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=kind,
        predicted_probability=probability,
        domain=domain,
        independent_run=run or f"run-{index}",
        predicted_at=float(index * 2),
        negative_control=negative_control,
        source_finding_ids=(
            f"finding:{index}:left",
            f"finding:{index}:right",
        ),
        source_forecast_ids=(f"forecast:{index}",),
        metadata={"predeclared": True},
    )
    lab.declare(prediction)
    return TopologyBridgeTrial.from_prediction(
        prediction,
        trial_id=f"bridge-trial:{kind.value}:{index}",
        outcome=outcome,
        observed_at=float(index * 2 + 1),
    )


def _promote(
    lab: SemanticTopologyLearningLab,
    candidate,
    *,
    kind: LensInteractionKind = LensInteractionKind.REINFORCES,
) -> None:
    rows = (
        (1, "film", "run-a"),
        (2, "film", "run-b"),
        (3, "game", "run-c"),
        (4, "game", "run-d"),
    )
    for index, domain, run in rows:
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=kind,
                domain=domain,
                run=run,
            )
        )
    for index, domain, run in (
        (101, "film", "control-a"),
        (102, "game", "control-b"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=kind,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=run,
                negative_control=True,
            )
        )


def test_bridge_trial_is_bound_to_exact_candidate_fingerprint() -> None:
    _, _, candidate, lab = _system()
    trial = _trial(lab, candidate, 1)
    mutated = replace(
        trial,
        candidate_fingerprint="0" * 64,
    )

    with pytest.raises(
        AgentContractError,
        match="candidate changed after trial declaration",
    ):
        lab.record(mutated)


def test_bridge_trial_rejects_post_outcome_prediction() -> None:
    _, _, candidate, lab = _system()
    prediction = TopologyBridgePrediction(
        prediction_id="bridge-prediction:time",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.8,
        domain="film",
        independent_run="run-time",
        predicted_at=20.0,
    )
    lab.declare(prediction)

    with pytest.raises(
        AgentContractError,
        match="outcome cannot predate",
    ):
        lab.resolve(
            prediction.prediction_id,
            outcome=True,
            observed_at=19.0,
        )


def test_candidate_prediction_helper_is_idempotent_and_slot_guarded() -> None:
    _, _, candidate, lab = _system()

    first = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="canonical-run",
        predicted_at=10.0,
        source_forecast_ids=("forecast:canonical",),
    )
    same = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="canonical-run",
        predicted_at=10.0,
        source_forecast_ids=("forecast:canonical",),
    )

    assert same.prediction_id == first.prediction_id
    assert same.fingerprint == first.fingerprint
    assert lab.unresolved_predictions(
        candidate_id=candidate.candidate_id
    ) == (first,)

    with pytest.raises(
        AgentContractError,
        match="experiment slot already has",
    ):
        lab.declare_candidate_prediction(
            candidate.candidate_id,
            kind=LensInteractionKind.REINFORCES,
            predicted_probability=0.90,
            domain="film",
            independent_run="canonical-run",
            predicted_at=10.0,
            source_forecast_ids=("forecast:canonical",),
        )

    lab.resolve(
        first.prediction_id,
        outcome=True,
        observed_at=11.0,
        outcome_evidence_ids=("evidence:canonical-outcome",),
    )
    assert lab.unresolved_predictions(
        candidate_id=candidate.candidate_id
    ) == ()


def test_semantic_plane_candidate_helper_owns_candidate_fingerprint() -> None:
    registry, topology, candidate, lab = _system()
    plane = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=lab,
    )

    prediction = plane.declare_topology_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.CONDITIONS,
        predicted_probability=0.65,
        domain="game",
        independent_run="plane-run",
        predicted_at=20.0,
        evidence_ids=("evidence:plane",),
    )

    assert prediction.candidate_id == candidate.candidate_id
    assert (
        prediction.candidate_fingerprint
        == lab.candidate_fingerprint(candidate)
    )
    assert plane.unresolved_topology_predictions(
        candidate_id=candidate.candidate_id
    ) == (prediction,)


def test_outcome_requires_prediction_in_ledger() -> None:
    _, _, candidate, lab = _system()
    prediction = TopologyBridgePrediction(
        prediction_id="bridge-prediction:undeclared",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.8,
        domain="film",
        independent_run="run-undeclared",
        predicted_at=10.0,
    )
    trial = TopologyBridgeTrial.from_prediction(
        prediction,
        trial_id="bridge-trial:undeclared",
        outcome=True,
        observed_at=11.0,
    )

    with pytest.raises(
        AgentContractError,
        match="must be declared before outcome",
    ):
        lab.record(trial)


def test_prediction_resolution_is_single_assignment_and_idempotent() -> None:
    _, _, candidate, lab = _system()
    prediction = TopologyBridgePrediction(
        prediction_id="bridge-prediction:single",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.8,
        domain="film",
        independent_run="run-single",
        predicted_at=10.0,
    )
    lab.declare(prediction)

    pending = lab.snapshot()
    assert pending.prediction_count == 1
    assert pending.unresolved_prediction_count == 1
    assert pending.trial_count == 0

    first = lab.resolve(
        prediction.prediction_id,
        outcome=True,
        observed_at=11.0,
    )
    same = lab.resolve(
        prediction.prediction_id,
        outcome=True,
        observed_at=11.0,
    )
    assert same.fingerprint == first.fingerprint

    resolved = lab.snapshot()
    assert resolved.prediction_count == 1
    assert resolved.unresolved_prediction_count == 0
    assert resolved.trial_count == 1

    with pytest.raises(
        AgentContractError,
        match="reused differently",
    ):
        lab.resolve(
            prediction.prediction_id,
            outcome=False,
            observed_at=11.0,
        )


def test_unresolved_prediction_capacity_fails_closed_without_mutation() -> None:
    _, topology, candidate, base = _system()
    lab = SemanticTopologyLearningLab(
        topology,
        policy=replace(
            base.policy,
            maximum_predictions=3,
            maximum_trials=3,
            maximum_unresolved_predictions=1,
        ),
    )
    first = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="capacity-a",
        predicted_at=1.0,
    )
    before = lab.fingerprint

    with pytest.raises(
        AgentContractError,
        match="unresolved prediction capacity exhausted",
    ):
        lab.declare_candidate_prediction(
            candidate.candidate_id,
            kind=LensInteractionKind.REINFORCES,
            predicted_probability=0.72,
            domain="film",
            independent_run="capacity-b",
            predicted_at=2.0,
        )

    assert lab.fingerprint == before
    assert lab.unresolved_predictions() == (first,)


def test_total_prediction_capacity_survives_resolution_but_stays_bounded() -> None:
    _, topology, candidate, base = _system()
    lab = SemanticTopologyLearningLab(
        topology,
        policy=replace(
            base.policy,
            maximum_predictions=2,
            maximum_trials=3,
            maximum_unresolved_predictions=2,
        ),
    )
    first = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="total-a",
        predicted_at=1.0,
    )
    lab.resolve(first.prediction_id, outcome=True, observed_at=2.0)
    second = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.72,
        domain="game",
        independent_run="total-b",
        predicted_at=3.0,
    )
    lab.resolve(second.prediction_id, outcome=True, observed_at=4.0)
    before = lab.fingerprint

    with pytest.raises(
        AgentContractError,
        match="prediction capacity exhausted",
    ):
        lab.declare_candidate_prediction(
            candidate.candidate_id,
            kind=LensInteractionKind.REINFORCES,
            predicted_probability=0.74,
            domain="literature",
            independent_run="total-c",
            predicted_at=5.0,
        )

    assert lab.fingerprint == before
    assert lab.snapshot().prediction_count == 2
    assert lab.snapshot().trial_count == 2


def test_trial_capacity_leaves_declared_prediction_unresolved() -> None:
    _, topology, candidate, base = _system()
    lab = SemanticTopologyLearningLab(
        topology,
        policy=replace(
            base.policy,
            maximum_predictions=3,
            maximum_trials=1,
            maximum_unresolved_predictions=3,
        ),
    )
    first = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="trial-a",
        predicted_at=1.0,
    )
    lab.resolve(first.prediction_id, outcome=True, observed_at=2.0)
    second = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="game",
        independent_run="trial-b",
        predicted_at=3.0,
    )

    with pytest.raises(
        AgentContractError,
        match="trial capacity exhausted",
    ):
        lab.resolve(second.prediction_id, outcome=True, observed_at=4.0)

    assert lab.unresolved_predictions() == (second,)
    assert lab.snapshot().trial_count == 1


def test_replicated_bridge_promotes_to_active_learned_rule() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)

    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    learned = lab.learned_rules()
    snapshot = lab.snapshot()

    assert report.status is TopologyBridgeStatus.ACTIVE
    assert report.trial_count == 4
    assert report.negative_control_count == 2
    assert report.independent_run_count == 4
    assert report.domain_count == 2
    assert report.brier is not None and report.brier < 0.02
    assert report.calibration_error is not None
    assert report.calibration_error < 0.11
    assert report.negative_control_positive_rate == 0.0
    assert len(learned) == 1
    assert learned[0].candidate_id == candidate.candidate_id
    assert learned[0].rule.kind is LensInteractionKind.REINFORCES
    assert learned[0].rule.key == tuple(
        sorted((candidate.left_key, candidate.right_key))
    )
    assert "cannot create evidence" in learned[0].rule.rationale
    assert snapshot.active_report_ids == (report.report_id,)
    assert snapshot.learned_rule_keys == (learned[0].rule.key,)


def test_persistently_wrong_bridge_is_rejected() -> None:
    _, _, candidate, lab = _system()
    for index, domain, run in (
        (1, "film", "bad-a"),
        (2, "film", "bad-b"),
        (3, "game", "bad-c"),
        (4, "game", "bad-d"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=False,
                domain=domain,
                run=run,
            )
        )
    for index, domain in ((101, "film"), (102, "game")):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=f"bad-control-{index}",
                negative_control=True,
            )
        )

    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )

    assert report.status is TopologyBridgeStatus.REJECTED
    assert "brier_rejection_threshold" in report.reasons
    assert "empirical_rate_rejection_threshold" in report.reasons
    assert lab.learned_rules() == ()


def test_pooled_metrics_cannot_hide_bad_transfer_domain() -> None:
    _, _, candidate, lab = _system()
    primary_rows = (
        (1, "film", "film-a", True),
        (2, "film", "film-b", True),
        (3, "game", "game-a", True),
        (4, "game", "game-b", False),
    )
    for index, domain, run, outcome in primary_rows:
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=outcome,
                domain=domain,
                run=run,
            )
        )
    for index, domain, run in (
        (101, "film", "film-control"),
        (102, "game", "game-control"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=run,
                negative_control=True,
            )
        )

    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )

    assert report.empirical_rate == pytest.approx(0.75)
    assert report.brier is not None
    assert report.brier < lab.policy.maximum_brier
    assert report.qualified_domain_count == 2
    assert report.qualified_control_domain_count == 2
    assert report.worst_domain_brier is not None
    assert report.worst_domain_brier > lab.policy.maximum_domain_brier
    assert report.minimum_domain_empirical_rate == pytest.approx(0.5)
    assert report.status is TopologyBridgeStatus.RESTRICTED
    assert "domain_transfer_failure" in report.reasons
    assert lab.learned_rules() == ()


def test_domain_reports_expose_transfer_and_control_quality() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)

    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    domains = {item.domain: item for item in report.domain_reports}

    assert set(domains) == {"film", "game"}
    assert all(item.qualified_primary for item in domains.values())
    assert all(item.qualified_control for item in domains.values())
    assert all(item.trial_count == 2 for item in domains.values())
    assert all(item.negative_control_count == 1 for item in domains.values())
    assert all(
        item.brier is not None and item.brier < 0.02
        for item in domains.values()
    )
    assert report.worst_domain_control_positive_rate == 0.0


def test_negative_control_failure_blocks_promotion() -> None:
    _, _, candidate, lab = _system()
    for index, domain, run in (
        (1, "film", "run-a"),
        (2, "film", "run-b"),
        (3, "game", "run-c"),
        (4, "game", "run-d"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                domain=domain,
                run=run,
            )
        )
    for index, domain in ((101, "film"), (102, "game")):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=True,
                domain=domain,
                run=f"control-{index}",
                negative_control=True,
            )
        )

    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )

    assert report.status is TopologyBridgeStatus.RESTRICTED
    assert report.negative_control_positive_rate == 1.0
    assert "negative_control_failure" in report.reasons
    assert lab.learned_rules() == ()


def test_active_bridge_is_revoked_when_new_trials_break_calibration() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)
    active = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    assert active.status is TopologyBridgeStatus.ACTIVE
    assert len(lab.learned_rules()) == 1

    for index, domain in (
        (401, "film"),
        (402, "film"),
        (403, "game"),
        (404, "game"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=False,
                domain=domain,
                run=f"drift-{index}",
            )
        )

    restricted = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    assert restricted.status is TopologyBridgeStatus.RESTRICTED
    assert lab.learned_rules() == ()

    obligations = lab.research_obligations(
        limit=100,
        minimum_candidate_score=0.0,
    )
    obligation = next(
        item
        for item in obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )
    assert obligation.metadata["status"] == "restricted"
    assert obligation.contradiction_strength > 0.0


def test_restricted_bridge_can_recover_after_new_replication() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)
    for index, domain in (
        (401, "film"),
        (402, "film"),
        (403, "game"),
        (404, "game"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=False,
                domain=domain,
                run=f"drift-{index}",
            )
        )
    assert lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    ).status is TopologyBridgeStatus.RESTRICTED

    for index, domain in (
        (501, "film"),
        (502, "film"),
        (503, "game"),
        (504, "game"),
        (505, "film"),
        (506, "game"),
        (507, "film"),
        (508, "game"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=True,
                domain=domain,
                run=f"recovery-{index}",
            )
        )

    recovered = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    assert recovered.status is TopologyBridgeStatus.ACTIVE
    assert len(lab.learned_rules()) == 1


def _companion_fixture():
    registry, topology, candidate, lab = _system()
    _promote(lab, candidate)
    left = registry.get(candidate.left_key)
    right = registry.get(candidate.right_key)
    selection = LensSelection(
        lenses=(left,),
        activation_scores={left.key: 0.90},
        families=(left.family,),
        perpendicular=True,
    )
    cue_text = " ".join(right.activation_cues)
    observation_count = max(3, right.minimum_observations)
    supported = tuple(
        SemanticObservation(
            f"companion-supported:{index}",
            cue_text,
            index,
        )
        for index in range(observation_count)
    )
    unsupported = tuple(
        SemanticObservation(
            f"companion-unsupported:{index}",
            "unrelated qzjx token with no registered companion cues",
            index,
        )
        for index in range(observation_count)
    )
    return (
        registry,
        topology,
        candidate,
        lab,
        left,
        right,
        selection,
        supported,
        unsupported,
    )


def test_active_learned_bridge_can_add_freshly_supported_companion_lens() -> None:
    (
        registry,
        topology,
        _candidate,
        lab,
        _left,
        right,
        selection,
        supported,
        _unsupported,
    ) = _companion_fixture()
    plane = SemanticLensPlane(
        registry=registry,
        router=_FixedRouter(registry, selection),
        topology=topology,
        topology_learning=lab,
        policy=SemanticPlanePolicy(
            require_selected_findings=False,
            max_lenses=8,
            max_per_family=6,
            enable_learned_companions=True,
            max_learned_companions=2,
            minimum_learned_companion_cue_support=0.20,
        ),
    )

    snapshot = plane.analyze(supported)

    assert right.key in {
        item.key for item in snapshot.selection.lenses
    }
    assert snapshot.learned_companion_keys == (right.key,)
    assert snapshot.coverage.learned_companion_lenses == 1
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False


def test_learned_bridge_never_adds_companion_without_fresh_cue_support() -> None:
    (
        registry,
        topology,
        _candidate,
        lab,
        _left,
        right,
        selection,
        _supported,
        unsupported,
    ) = _companion_fixture()
    plane = SemanticLensPlane(
        registry=registry,
        router=_FixedRouter(registry, selection),
        topology=topology,
        topology_learning=lab,
        policy=SemanticPlanePolicy(
            require_selected_findings=False,
            max_lenses=8,
            max_per_family=6,
            enable_learned_companions=True,
            minimum_learned_companion_cue_support=0.20,
        ),
    )

    snapshot = plane.analyze(unsupported)

    assert right.key not in {
        item.key for item in snapshot.selection.lenses
    }
    assert snapshot.learned_companion_keys == ()
    assert snapshot.coverage.learned_companion_lenses == 0


def test_learned_companion_policy_can_be_disabled_without_changing_router_selection() -> None:
    (
        registry,
        topology,
        _candidate,
        lab,
        _left,
        right,
        selection,
        supported,
        _unsupported,
    ) = _companion_fixture()
    plane = SemanticLensPlane(
        registry=registry,
        router=_FixedRouter(registry, selection),
        topology=topology,
        topology_learning=lab,
        policy=SemanticPlanePolicy(
            require_selected_findings=False,
            max_lenses=8,
            max_per_family=6,
            enable_learned_companions=False,
        ),
    )

    snapshot = plane.analyze(supported)

    assert tuple(item.key for item in snapshot.selection.lenses) == (
        tuple(item.key for item in selection.lenses)
    )
    assert right.key not in {
        item.key for item in snapshot.selection.lenses
    }
    assert snapshot.learned_companion_keys == ()


def test_competing_active_relation_kinds_fail_closed() -> None:
    _, _, candidate, lab = _system()
    _promote(
        lab,
        candidate,
        kind=LensInteractionKind.REINFORCES,
    )
    for index, domain, run in (
        (201, "film", "conflict-a"),
        (202, "film", "conflict-b"),
        (203, "game", "conflict-c"),
        (204, "game", "conflict-d"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=LensInteractionKind.CONFLICTS,
                domain=domain,
                run=run,
            )
        )
    for index, domain, run in (
        (301, "film", "conflict-control-a"),
        (302, "game", "conflict-control-b"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=LensInteractionKind.CONFLICTS,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=run,
                negative_control=True,
            )
        )

    reinforces = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )
    conflicts = lab.report(
        candidate.candidate_id,
        LensInteractionKind.CONFLICTS,
    )
    snapshot = lab.snapshot()

    assert reinforces.status is TopologyBridgeStatus.ACTIVE
    assert conflicts.status is TopologyBridgeStatus.ACTIVE
    assert lab.learned_rules() == ()
    assert snapshot.ambiguous_active_candidate_ids == (
        candidate.candidate_id,
    )


def test_controls_do_not_pollute_primary_bridge_calibration() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)
    report = lab.report(
        candidate.candidate_id,
        LensInteractionKind.REINFORCES,
    )

    assert report.trial_count == 4
    assert report.negative_control_count == 2
    assert report.empirical_rate == 1.0
    assert report.mean_probability == pytest.approx(0.90)


def test_learned_topology_edge_identity_tracks_report_lineage_without_mutating_static_graph() -> None:
    _, topology, candidate, _lab = _system()
    static_fingerprint = topology.snapshot.fingerprint

    def rule(report_fingerprint: str) -> LensInteractionRule:
        return LensInteractionRule(
            left_key=candidate.left_key,
            right_key=candidate.right_key,
            kind=LensInteractionKind.REINFORCES,
            rationale="validated learned bridge",
            question="Does the relation replicate?",
            predictive_effect="Retest on an independent case.",
            symmetric=True,
            tangent_axis_hint="semantic",
            metadata={
                "rule_source": "learned_topology",
                "report_fingerprint": report_fingerprint,
            },
        )

    first = topology.snapshot_with_rules((rule("report-a"),))
    second = topology.snapshot_with_rules((rule("report-b"),))
    first_edge = next(
        item for item in first.edges if item.source == "learned"
    )
    second_edge = next(
        item for item in second.edges if item.source == "learned"
    )

    assert first_edge.key == second_edge.key
    assert first_edge.edge_id != second_edge.edge_id
    assert first.fingerprint != second.fingerprint
    assert topology.snapshot.fingerprint == static_fingerprint


def test_semantic_plane_executes_default_interaction_rules_known_to_topology() -> None:
    registry = MaximalSemanticRegistry()
    plane = SemanticLensPlane(
        registry=registry,
        policy=SemanticPlanePolicy(
            require_selected_findings=False,
        ),
    )
    observations = (
        SemanticObservation(
            "default-rule:obs:1",
            "A neutral face is placed after a contextual image.",
            0,
        ),
        SemanticObservation(
            "default-rule:obs:2",
            "The narrator claims a meaning that independent context challenges.",
            1,
        ),
    )
    observation_ids = tuple(item.observation_id for item in observations)
    findings = (
        SemanticFinding(
            finding_id="default-rule:kuleshov",
            lens_key="kuleshov_context",
            family=registry.get("kuleshov_context").family,
            observation_ids=observation_ids,
            interpretation="Adjacent context changes the plausible reading.",
            prediction="Changing context changes the induced interpretation.",
            confidence=0.80,
            ambiguity=0.20,
            novelty=0.55,
        ),
        SemanticFinding(
            finding_id="default-rule:narrator",
            lens_key="unreliable_narrator",
            family=registry.get("unreliable_narrator").family,
            observation_ids=observation_ids,
            interpretation="Independent context challenges the source report.",
            prediction="Independent evidence diverges from the narrated claim.",
            confidence=0.78,
            ambiguity=0.24,
            novelty=0.52,
        ),
    )

    snapshot = plane.analyze(
        observations,
        findings=findings,
        requested=("kuleshov_context", "unreliable_narrator"),
    )

    interaction = next(
        item
        for item in snapshot.composition.interactions
        if item.rule.key
        == tuple(sorted(("kuleshov_context", "unreliable_narrator")))
    )
    assert interaction.rule.kind is LensInteractionKind.CONDITIONS
    assert interaction.metadata["interpretive_only"] is True
    assert interaction.metadata["may_promote_to_evidence"] is False
    assert any(
        edge.key == interaction.rule.key
        for edge in snapshot.topology.edges
    )


def test_supplemental_rule_cannot_override_static_interaction_contract() -> None:
    engine = LensCompositionEngine()
    static = default_interaction_rules()[0]

    with pytest.raises(
        AgentContractError,
        match="collides with static interaction",
    ):
        engine.compose((), supplemental_rules=(static,))


def test_learned_bridge_overlays_effective_topology_without_mutating_static_graph() -> None:
    _, topology, candidate, lab = _system()
    static = topology.snapshot
    _promote(lab, candidate)
    learned = lab.learned_rules()
    assert len(learned) == 1

    effective = topology.snapshot_with_rules((learned[0].rule,))

    assert topology.snapshot.fingerprint == static.fingerprint
    assert len(effective.edges) == len(static.edges) + 1
    learned_edge = next(
        edge
        for edge in effective.edges
        if edge.key
        == tuple(sorted((candidate.left_key, candidate.right_key)))
    )
    assert learned_edge.source == "learned"
    assert effective.candidate_bridge_count == static.candidate_bridge_count - 1
    assert sum(item[2] for item in effective.family_pair_counts) == len(
        effective.edges
    )
    assert candidate.right_key in topology.neighbors_with_rules(
        candidate.left_key,
        (learned[0].rule,),
    )
    assert topology.shortest_path_with_rules(
        candidate.left_key,
        candidate.right_key,
        supplemental_rules=(learned[0].rule,),
    ) == (candidate.left_key, candidate.right_key)


def test_topology_overlay_rejects_collision_with_static_edge() -> None:
    registry = MaximalSemanticRegistry()
    topology = SemanticLensTopology(registry)
    static_rule = default_interaction_rules()[0]

    with pytest.raises(
        AgentContractError,
        match="collides with static edge",
    ):
        topology.snapshot_with_rules((static_rule,))


def test_semantic_plane_activates_bridge_only_after_empirical_promotion() -> None:
    registry, topology, candidate, lab = _system()
    plane = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=lab,
        policy=SemanticPlanePolicy(
            require_selected_findings=False,
            max_lenses=40,
            max_per_family=6,
        ),
    )
    left_spec = registry.get(candidate.left_key)
    right_spec = registry.get(candidate.right_key)
    shared = " ".join(candidate.shared_cues) or "semantic relation"
    observations = (
        SemanticObservation(
            "obs:1",
            f"{shared} first context for {candidate.left_key}.",
            0,
        ),
        SemanticObservation(
            "obs:2",
            f"{shared} second context for {candidate.right_key}.",
            1,
        ),
        SemanticObservation(
            "obs:3",
            f"{shared} independent discriminating context.",
            2,
        ),
    )
    observation_ids = tuple(item.observation_id for item in observations)
    findings = (
        SemanticFinding(
            finding_id="finding:left",
            lens_key=candidate.left_key,
            family=left_spec.family,
            observation_ids=observation_ids,
            interpretation="Left lens supplies one bounded interpretation.",
            prediction="A later observation can discriminate the left reading.",
            confidence=0.82,
            ambiguity=0.20,
            novelty=0.65,
        ),
        SemanticFinding(
            finding_id="finding:right",
            lens_key=candidate.right_key,
            family=right_spec.family,
            observation_ids=observation_ids,
            interpretation="Right lens supplies a complementary reading.",
            prediction="A later observation can discriminate the right reading.",
            confidence=0.80,
            ambiguity=0.22,
            novelty=0.62,
        ),
    )

    before = plane.analyze(
        observations,
        findings=findings,
        requested=(candidate.left_key, candidate.right_key),
        sequence=1,
    )

    assert not any(
        interaction.rule.key
        == tuple(sorted((candidate.left_key, candidate.right_key)))
        for interaction in before.composition.interactions
    )
    assert before.learned_topology_rules == ()
    assert any(
        item.candidate_id == candidate.candidate_id
        for item in before.topology_bridge_candidates
    )

    _promote(lab, candidate)

    after = plane.analyze(
        observations,
        findings=findings,
        requested=(candidate.left_key, candidate.right_key),
        sequence=2,
    )

    learned_pair = tuple(sorted((candidate.left_key, candidate.right_key)))
    interactions = [
        item
        for item in after.composition.interactions
        if item.rule.key == learned_pair
    ]
    assert len(interactions) == 1
    assert interactions[0].rule.kind is LensInteractionKind.REINFORCES
    assert interactions[0].metadata["interpretive_only"] is True
    assert interactions[0].metadata["may_promote_to_evidence"] is False
    provenance = interactions[0].metadata["rule_provenance"]
    assert provenance["rule_source"] == "learned_topology"
    assert provenance["candidate_id"] == candidate.candidate_id
    assert provenance["report_id"] == after.learned_topology_rules[0].report_id
    assert provenance["report_fingerprint"] == (
        after.learned_topology_rules[0].report_fingerprint
    )
    assert provenance["evidence_ceiling"] == "interpretive_only"
    assert provenance["may_promote_to_evidence"] is False
    assert len(after.learned_topology_rules) == 1
    assert after.coverage.topology_learned_bridges == 1
    assert after.coverage.topology_active_learning_reports == 1
    assert candidate.candidate_id not in {
        item.candidate_id for item in after.topology_bridge_candidates
    }
    assert after.factual_assertion_authorized is False
    assert after.causal_assertion_authorized is False


def test_topology_diagnostics_expose_pending_prediction_without_claiming_evidence() -> None:
    _, _, candidate, lab = _system()
    prediction = lab.declare_candidate_prediction(
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="diagnostic-pending",
        predicted_at=10.0,
    )

    payload = lab.diagnostics(
        candidate_id=candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
    )

    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["candidate_id"] == candidate.candidate_id
    assert payload["reports"] == []
    assert [
        item["prediction_id"]
        for item in payload["unresolved_predictions"]
    ] == [prediction.prediction_id]
    assert payload["snapshot"]["unresolved_prediction_count"] == 1
    assert payload["invariants"]["diagnostics_are_not_evidence"] is True


def test_topology_diagnostics_expose_domain_calibration_and_rule_provenance() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)

    payload = lab.diagnostics(
        candidate_id=candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
    )

    assert len(payload["reports"]) == 1
    report = payload["reports"][0]
    assert report["status"] == "active"
    assert report["qualified_domain_count"] == 2
    assert report["qualified_control_domain_count"] == 2
    assert {item["domain"] for item in report["domain_reports"]} == {
        "film",
        "game",
    }
    assert len(payload["learned_rules"]) == 1
    learned = payload["learned_rules"][0]
    assert learned["rule"]["metadata"]["rule_source"] == "learned_topology"
    assert (
        learned["rule"]["metadata"]["evidence_ceiling"]
        == "interpretive_only"
    )
    assert learned["rule"]["metadata"]["may_promote_to_evidence"] is False


def test_topology_diagnostics_are_bounded_and_report_truncation() -> None:
    _, _, _, lab = _system()

    payload = lab.diagnostics(limit=1)

    assert len(payload["candidates"]) == 1
    assert payload["truncated"]["candidates"] is True
    assert payload["invariants"]["static_topology_contract_is_immutable"] is True


def test_unvalidated_topology_candidate_becomes_research_obligation() -> None:
    _, _, candidate, lab = _system()

    obligations = lab.research_obligations(
        limit=8,
        minimum_candidate_score=0.0,
    )
    obligation = next(
        item
        for item in obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )

    assert obligation.metadata["status"] == "shadow"
    assert obligation.evidence_coverage == 0.0
    assert obligation.assumption_load == pytest.approx(0.85)
    assert obligation.metadata["semantic_topology"] is True
    assert "shared cues do not establish" in obligation.assumptions[0]

    frontier = EpistemicFrontierEngine().discover((obligation,))
    assert frontier.gaps
    assert any(
        gap.obligation_id == obligation.obligation_id
        for gap in frontier.gaps
    )


def test_control_plane_ingests_topology_obligations_into_research_agenda() -> None:
    _, _, candidate, lab = _system()
    control = FrontierCognitiveControlPlane(clock=lambda: 1000.0)

    frontier = control.map_semantic_topology_frontier(
        lab,
        limit=8,
        minimum_candidate_score=0.0,
    )

    obligation = next(
        item
        for item in frontier.obligations
        if item.metadata["candidate_id"] == candidate.candidate_id
    )
    assert frontier.gaps
    agenda_items = control.research_agenda.items_for_obligation(
        obligation.obligation_id
    )
    assert agenda_items
    assert any(
        item.obligation_id == obligation.obligation_id
        for item in agenda_items
    )


def test_promoted_topology_bridge_leaves_research_debt_queue() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)

    obligations = lab.research_obligations(
        limit=10_000,
        minimum_candidate_score=0.0,
    )

    assert candidate.candidate_id not in {
        item.metadata["candidate_id"] for item in obligations
    }


def test_ambiguous_active_bridge_surfaces_as_high_disagreement_obligation() -> None:
    _, _, candidate, lab = _system()
    _promote(
        lab,
        candidate,
        kind=LensInteractionKind.REINFORCES,
    )
    for index, domain, run in (
        (201, "film", "ambiguity-a"),
        (202, "film", "ambiguity-b"),
        (203, "game", "ambiguity-c"),
        (204, "game", "ambiguity-d"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=LensInteractionKind.CONFLICTS,
                domain=domain,
                run=run,
            )
        )
    for index, domain, run in (
        (301, "film", "ambiguity-control-a"),
        (302, "game", "ambiguity-control-b"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                kind=LensInteractionKind.CONFLICTS,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=run,
                negative_control=True,
            )
        )

    obligation = next(
        item
        for item in lab.research_obligations(
            limit=10_000,
            minimum_candidate_score=0.0,
        )
        if item.metadata["candidate_id"] == candidate.candidate_id
    )

    assert obligation.metadata["status"] == "ambiguous_active"
    assert obligation.model_disagreement == 1.0
    assert obligation.contradiction_strength == 1.0
    assert set(obligation.metadata["active_kinds"]) == {
        LensInteractionKind.REINFORCES.value,
        LensInteractionKind.CONFLICTS.value,
    }


def test_rejected_bridge_is_suppressed_unless_researcher_requests_it() -> None:
    _, _, candidate, lab = _system()
    for index, domain, run in (
        (1, "film", "reject-a"),
        (2, "film", "reject-b"),
        (3, "game", "reject-c"),
        (4, "game", "reject-d"),
    ):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.90,
                outcome=False,
                domain=domain,
                run=run,
            )
        )
    for index, domain in ((101, "film"), (102, "game")):
        lab.record(
            _trial(
                lab,
                candidate,
                index,
                probability=0.05,
                outcome=False,
                domain=domain,
                run=f"reject-control-{index}",
                negative_control=True,
            )
        )

    default_ids = {
        item.metadata["candidate_id"]
        for item in lab.research_obligations(
            limit=10_000,
            minimum_candidate_score=0.0,
        )
    }
    requested = lab.research_obligations(
        limit=10_000,
        minimum_candidate_score=0.0,
        include_rejected=True,
    )
    rejected = next(
        item
        for item in requested
        if item.metadata["candidate_id"] == candidate.candidate_id
    )

    assert candidate.candidate_id not in default_ids
    assert rejected.metadata["status"] == "rejected"
    assert rejected.contradiction_strength >= 0.65


def test_topology_learning_state_round_trip_preserves_promoted_rules() -> None:
    _, topology, candidate, lab = _system()
    _promote(lab, candidate)
    expected_snapshot = lab.snapshot()
    expected_rules = tuple(
        item.fingerprint for item in lab.learned_rules()
    )
    state = lab.export_state()

    restored = SemanticTopologyLearningLab(
        topology,
        policy=lab.policy,
    )
    restored_snapshot = restored.restore_state(state.as_json())

    assert restored_snapshot.fingerprint == expected_snapshot.fingerprint
    assert restored.export_state().fingerprint == state.fingerprint
    assert tuple(
        item.fingerprint for item in restored.learned_rules()
    ) == expected_rules
    assert restored.fingerprint == lab.fingerprint


def test_topology_learning_state_rejects_contract_drift() -> None:
    _, topology, candidate, lab = _system()
    _promote(lab, candidate)
    state = lab.export_state()
    different = SemanticTopologyLearningLab(
        topology,
        policy=replace(lab.policy, minimum_trials=5),
    )

    with pytest.raises(
        AgentContractError,
        match="contract fingerprint mismatch",
    ):
        different.restore_state(state)


def test_topology_learning_state_detects_nested_payload_corruption() -> None:
    _, _, candidate, lab = _system()
    _promote(lab, candidate)
    payload = lab.export_state().as_json()
    payload["predictions"][0]["predicted_probability"] = 0.01

    with pytest.raises(
        AgentContractError,
        match="prediction payload fingerprint mismatch",
    ):
        SemanticTopologyLearningState.from_json(payload)


def test_failed_topology_restore_is_transactional() -> None:
    _, topology, candidate, source = _system()
    _promote(source, candidate)
    payload = source.export_state().as_json()
    payload.pop("fingerprint", None)
    payload["trials"][0].pop("fingerprint", None)
    payload["trials"][0]["prediction_fingerprint"] = "0" * 64

    destination = SemanticTopologyLearningLab(
        topology,
        policy=source.policy,
    )
    pending = TopologyBridgePrediction(
        prediction_id="bridge-prediction:destination",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=destination.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.6,
        domain="film",
        independent_run="destination-run",
        predicted_at=1.0,
    )
    destination.declare(pending)
    before = destination.fingerprint
    before_snapshot = destination.snapshot()

    with pytest.raises(
        AgentContractError,
        match="differs from prediction custody",
    ):
        destination.restore_state(payload)

    assert destination.fingerprint == before
    after_snapshot = destination.snapshot()
    assert after_snapshot.fingerprint == before_snapshot.fingerprint
    assert after_snapshot.prediction_count == 1
    assert after_snapshot.unresolved_prediction_count == 1


def test_semantic_plane_exposes_topology_state_round_trip() -> None:
    registry, topology, candidate, lab = _system()
    source = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=lab,
    )
    _promote(lab, candidate)
    state = source.export_topology_learning_state()

    target_lab = SemanticTopologyLearningLab(
        topology,
        policy=lab.policy,
    )
    target = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=target_lab,
    )
    snapshot = target.restore_topology_learning_state(state)

    assert snapshot.fingerprint == source.topology_learning.snapshot().fingerprint
    assert target.export_topology_learning_state().fingerprint == state.fingerprint
    assert target.topology_learning_summary()["learned_rule_keys"]


def test_topology_learning_summary_preserves_epistemic_boundaries() -> None:
    registry, topology, candidate, lab = _system()
    plane = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=lab,
    )
    _promote(lab, candidate)

    summary = plane.topology_learning_summary()

    assert summary["prediction_count"] == 6
    assert summary["unresolved_prediction_count"] == 0
    assert summary["trial_count"] == 6
    assert summary["tested_bridge_count"] == 1
    assert summary["learned_rule_keys"]
    assert summary["invariants"]["cue_overlap_never_auto_promotes"] is True
    assert summary["invariants"]["outcomes_require_predeclared_predictions"] is True
    assert summary["invariants"]["each_prediction_resolves_at_most_once"] is True
    assert summary["invariants"]["negative_controls_are_required"] is True
    assert summary["invariants"]["learned_bridges_never_create_evidence"] is True
