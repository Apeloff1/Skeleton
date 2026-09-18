from __future__ import annotations

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
)
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
from skeleton.jeeves.agent.semantic_plane import (
    SemanticLensPlane,
    SemanticPlanePolicy,
)
from skeleton.jeeves.agent.semantic_topology_learning import (
    SemanticTopologyLearningLab,
    TopologyBridgePolicy,
    TopologyBridgeStatus,
    TopologyBridgeTrial,
)
from skeleton.jeeves.agent.types import AgentContractError


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
    return TopologyBridgeTrial(
        trial_id=f"bridge-trial:{index}",
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=lab.candidate_fingerprint(candidate),
        left_key=candidate.left_key,
        right_key=candidate.right_key,
        kind=kind,
        predicted_probability=probability,
        outcome=outcome,
        domain=domain,
        independent_run=run or f"run-{index}",
        negative_control=negative_control,
        source_finding_ids=(f"finding:{index}:left", f"finding:{index}:right"),
        source_forecast_ids=(f"forecast:{index}",),
        metadata={"predeclared": True},
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
    mutated = TopologyBridgeTrial(
        trial_id=trial.trial_id,
        candidate_id=trial.candidate_id,
        candidate_fingerprint="0" * 64,
        left_key=trial.left_key,
        right_key=trial.right_key,
        kind=trial.kind,
        predicted_probability=trial.predicted_probability,
        outcome=trial.outcome,
        domain=trial.domain,
        independent_run=trial.independent_run,
    )

    with pytest.raises(
        AgentContractError,
        match="candidate changed after trial declaration",
    ):
        lab.record(mutated)


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
    assert len(after.learned_topology_rules) == 1
    assert after.coverage.topology_learned_bridges == 1
    assert after.coverage.topology_active_learning_reports == 1
    assert candidate.candidate_id not in {
        item.candidate_id for item in after.topology_bridge_candidates
    }
    assert after.factual_assertion_authorized is False
    assert after.causal_assertion_authorized is False


def test_topology_learning_summary_preserves_epistemic_boundaries() -> None:
    registry, topology, candidate, lab = _system()
    plane = SemanticLensPlane(
        registry=registry,
        topology=topology,
        topology_learning=lab,
    )
    _promote(lab, candidate)

    summary = plane.topology_learning_summary()

    assert summary["trial_count"] == 6
    assert summary["tested_bridge_count"] == 1
    assert summary["learned_rule_keys"]
    assert summary["invariants"]["cue_overlap_never_auto_promotes"] is True
    assert summary["invariants"]["negative_controls_are_required"] is True
    assert summary["invariants"]["learned_bridges_never_create_evidence"] is True
