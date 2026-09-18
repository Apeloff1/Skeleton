from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.semantic_frontier import (
    LensCompositionEngine,
    LensInteractionKind,
    default_interaction_rules,
)
from skeleton.jeeves.agent.semantic_lens_topology import SemanticLensTopology
from skeleton.jeeves.agent.semantic_lenses import (
    SemanticFinding,
    SemanticObservation,
    SemanticRole,
)
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
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


def test_supplemental_rule_cannot_override_static_interaction_contract() -> None:
    engine = LensCompositionEngine()
    static = default_interaction_rules()[0]

    with pytest.raises(
        AgentContractError,
        match="collides with static interaction",
    ):
        engine.compose((), supplemental_rules=(static,))


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
