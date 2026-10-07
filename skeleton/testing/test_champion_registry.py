from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes
from skeleton.contracts.reproducibility import ReproducibilityBundle
from skeleton.eval.benchmark_registry import (
    BenchmarkDataset,
    BenchmarkEnvironment,
    BenchmarkManifest,
    BenchmarkMetric,
    BenchmarkQualificationDecision,
    BenchmarkScoreObservation,
    BenchmarkSplit,
    BenchmarkSplitRole,
    ContaminationStatus,
    evaluate_improvement_claim,
    qualify_benchmark,
)
from skeleton.eval.champion_registry import (
    CandidateArtifact,
    ChampionRegistry,
    ChampionRegistryError,
    apply_promotion,
    evaluate_promotion,
    qualify_candidate_artifact,
)
from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    MetricDirection,
    TrafficMode,
)


def _repro() -> ReproducibilityBundle:
    return ReproducibilityBundle(
        repository="Apeloff1/Skeleton",
        commit_sha="a" * 40,
        task_id="P1-EVID-05",
        accountability_id="ACC-P1-EVID-05",
        configuration_digest="1" * 64,
        environment_digest="2" * 64,
        verifier_id="pytest:learn-03",
        verifier_digest="3" * 64,
        test_manifest_digest="4" * 64,
        runner_id="ubuntu2404",
        runner_digest="5" * 64,
        budget_id="learn03",
        budget_digest="6" * 64,
        source_date_epoch=1_800_000_000,
        expected_subject_digest="7" * 64,
        expected_evidence_digest="8" * 64,
        inputs=(
            EvidenceRef(
                source="fixture://learn-03",
                digest="9" * 64,
                category="candidate_input",
            ),
        ),
    )


def _experiment(
    candidate_ref: str = "candidate:v2",
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="exp.learn03.v2",
        hypothesis="Challenger improves independent holdout quality.",
        owner="p1-learning",
        source_commit="a" * 40,
        environment_id="eval.env",
        candidate_ref=candidate_ref,
        eligibility=ExperimentEligibility(
            traffic_mode=TrafficMode.OFFLINE,
            max_traffic_fraction=0.0,
            allowed_data_classes=("public",),
        ),
        budget=ExperimentBudget(
            max_samples=1000,
            max_tokens=1_000_000,
            max_cost_units=20.0,
            max_wall_time_s=1800.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality.acceptance",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=50,
                source="independent-eval",
                independent=True,
            ),
        ),
    )


def _benchmark(
    experiment: ExperimentManifest,
    repro: ReproducibilityBundle,
):
    dataset = BenchmarkDataset(
        dataset_id="quality-suite",
        version="v1",
        source_ref="fixture://quality-suite/v1",
        source_digest="a" * 64,
        content_digest="b" * 64,
        license_id="internal-test",
    )
    split = BenchmarkSplit(
        split_id="holdout.v1",
        role=BenchmarkSplitRole.HOLDOUT,
        dataset_digest=dataset.digest,
        content_digest="c" * 64,
        sample_count=100,
        contamination_status=ContaminationStatus.CLEAN,
        contamination_evidence=(
            EvidenceRef(
                source="fixture://contamination-scan",
                digest="d" * 64,
                category="contamination_scan",
            ),
        ),
    )
    metric = BenchmarkMetric(
        metric_id="quality.acceptance",
        direction=MetricDirection.MAXIMIZE,
        minimum_samples=50,
        evaluator_id="independent-eval",
        evaluator_digest="e" * 64,
        independent=True,
    )
    manifest = BenchmarkManifest(
        benchmark_id="quality-holdout",
        version="v1",
        datasets=(dataset,),
        splits=(split,),
        metrics=(metric,),
        primary_metric_id=metric.metric_id,
        environment=BenchmarkEnvironment(
            environment_id=experiment.environment_id,
            environment_digest=repro.environment_digest,
            runner_digest=repro.runner_digest,
            dependency_lock_digest="f" * 64,
            source_date_epoch=repro.source_date_epoch,
        ),
        experiment_manifest_digest=experiment.manifest_digest,
        reproducibility_bundle_digest=repro.bundle_digest,
        tags=("quality", "holdout"),
    )
    qualification = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=(split.split_id,),
    )
    assert qualification.accepted is True
    return manifest, qualification, split, metric


def _champion() -> CandidateArtifact:
    return CandidateArtifact(
        candidate_id="candidate-v1",
        version="v1",
        candidate_ref="candidate:v1",
        artifact_digest="0" * 64,
        source_commit="0" * 40,
        experiment_manifest_digest="1" * 64,
        benchmark_manifest_digest="2" * 64,
        benchmark_qualification_digest="3" * 64,
        reproducibility_bundle_digest="4" * 64,
        tags=("champion",),
    )


def _qualified_challenger():
    repro = _repro()
    experiment = _experiment()
    benchmark, benchmark_qualification, split, metric = _benchmark(
        experiment,
        repro,
    )
    challenger = CandidateArtifact(
        candidate_id="candidate-v2",
        version="v2",
        candidate_ref=experiment.candidate_ref,
        artifact_digest="5" * 64,
        source_commit=experiment.source_commit,
        experiment_manifest_digest=experiment.manifest_digest,
        benchmark_manifest_digest=benchmark.manifest_digest,
        benchmark_qualification_digest=benchmark_qualification.decision_digest,
        reproducibility_bundle_digest=repro.bundle_digest,
        tags=("challenger",),
    )
    qualification = qualify_candidate_artifact(
        candidate=challenger,
        experiment=experiment,
        benchmark=benchmark,
        benchmark_qualification=benchmark_qualification,
        reproducibility=repro,
    )
    return (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        split,
        metric,
        challenger,
        qualification,
    )


def _comparison(
    champion: CandidateArtifact,
    challenger: CandidateArtifact,
    experiment: ExperimentManifest,
    benchmark: BenchmarkManifest,
    benchmark_qualification: BenchmarkQualificationDecision,
    metric: BenchmarkMetric,
    *,
    baseline_ref: str | None = None,
    challenger_ref: str | None = None,
    baseline_score: float = 0.80,
    challenger_score: float = 0.90,
):
    baseline = BenchmarkScoreObservation(
        benchmark_manifest_digest=benchmark.manifest_digest,
        split_id="holdout.v1",
        metric_id=metric.metric_id,
        candidate_ref=baseline_ref or champion.candidate_ref,
        score=baseline_score,
        sample_count=100,
        evaluator_id=metric.evaluator_id,
        evaluator_digest=metric.evaluator_digest,
        independent=True,
    )
    candidate = BenchmarkScoreObservation(
        benchmark_manifest_digest=benchmark.manifest_digest,
        split_id="holdout.v1",
        metric_id=metric.metric_id,
        candidate_ref=challenger_ref or challenger.candidate_ref,
        score=challenger_score,
        sample_count=100,
        evaluator_id=metric.evaluator_id,
        evaluator_digest=metric.evaluator_digest,
        independent=True,
    )
    claim = evaluate_improvement_claim(
        manifest=benchmark,
        qualification=benchmark_qualification,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
    )
    return baseline, candidate, claim


def test_candidate_artifact_qualification_binds_all_upstream_evidence() -> None:
    (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        _,
        challenger,
        qualification,
    ) = _qualified_challenger()

    assert qualification.accepted is True
    assert qualification.reasons == ()
    assert qualification.candidate_digest == challenger.candidate_digest
    assert (
        qualification.experiment_manifest_digest
        == experiment.manifest_digest
    )
    assert qualification.benchmark_manifest_digest == benchmark.manifest_digest
    assert (
        qualification.benchmark_qualification_digest
        == benchmark_qualification.decision_digest
    )
    assert qualification.reproducibility_bundle_digest == repro.bundle_digest
    evidence = qualification.accepted_evidence_ref()
    assert evidence.category == "candidate_qualification"


def test_candidate_ref_substitution_blocks_qualification() -> None:
    (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        _,
        challenger,
        _,
    ) = _qualified_challenger()
    forged = replace(challenger, candidate_ref="candidate:other")

    decision = qualify_candidate_artifact(
        candidate=forged,
        experiment=experiment,
        benchmark=benchmark,
        benchmark_qualification=benchmark_qualification,
        reproducibility=repro,
    )

    assert decision.accepted is False
    assert "candidate-ref-mismatch" in decision.reasons


def test_candidate_source_commit_must_match_reproducibility() -> None:
    (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        _,
        challenger,
        _,
    ) = _qualified_challenger()
    forged = replace(challenger, source_commit="b" * 40)

    decision = qualify_candidate_artifact(
        candidate=forged,
        experiment=experiment,
        benchmark=benchmark,
        benchmark_qualification=benchmark_qualification,
        reproducibility=repro,
    )

    assert decision.accepted is False
    assert "candidate-source-commit-experiment-mismatch" in decision.reasons
    assert (
        "candidate-source-commit-reproducibility-mismatch"
        in decision.reasons
    )


def test_candidate_cannot_qualify_from_rejected_benchmark() -> None:
    (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        _,
        challenger,
        _,
    ) = _qualified_challenger()
    rejected = replace(
        benchmark_qualification,
        accepted=False,
        reasons=("contamination-not-clean",),
    )
    challenger = replace(
        challenger,
        benchmark_qualification_digest=rejected.decision_digest,
    )

    decision = qualify_candidate_artifact(
        candidate=challenger,
        experiment=experiment,
        benchmark=benchmark,
        benchmark_qualification=rejected,
        reproducibility=repro,
    )

    assert decision.accepted is False
    assert "benchmark-qualification-rejected" in decision.reasons


def test_accepted_comparative_promotion_is_append_only() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
    )
    assert claim.accepted is True

    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )
    advanced = apply_promotion(registry, decision)

    assert decision.accepted is True
    assert decision.transition is not None
    assert registry.current_champion_digest == champion.candidate_digest
    assert advanced.current_champion_digest == challenger.candidate_digest
    assert len(registry.transitions) == 0
    assert len(advanced.transitions) == 1
    assert advanced.transitions[0].previous_champion_digest == champion.candidate_digest
    assert advanced.transitions[0].challenger_digest == challenger.candidate_digest
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "champion_challenger_promotion"


def test_baseline_must_be_current_champion() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
        baseline_ref="candidate:not-champion",
    )
    assert claim.accepted is True

    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )

    assert decision.accepted is False
    assert "baseline-is-not-current-champion" in decision.reasons


def test_observation_must_be_registered_challenger() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
        challenger_ref="candidate:other",
    )
    assert claim.accepted is False

    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )

    assert decision.accepted is False
    assert "improvement-claim-rejected" in decision.reasons
    assert "observation-is-not-challenger" in decision.reasons


def test_non_improvement_cannot_advance_champion() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
        baseline_score=0.90,
        challenger_score=0.80,
    )
    assert claim.accepted is False

    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )

    assert decision.accepted is False
    with pytest.raises(
        ChampionRegistryError,
        match="only accepted promotion",
    ):
        apply_promotion(registry, decision)


def test_unregistered_challenger_is_rejected() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion,),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
    )

    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )

    assert decision.accepted is False
    assert "challenger-not-registered" in decision.reasons


def test_stale_promotion_decision_cannot_apply_to_changed_registry() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
    )
    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )
    extra = CandidateArtifact(
        candidate_id="candidate-v3",
        version="v3",
        candidate_ref="candidate:v3",
        artifact_digest="a" * 64,
        source_commit="a" * 40,
        experiment_manifest_digest="b" * 64,
        benchmark_manifest_digest="c" * 64,
        benchmark_qualification_digest="d" * 64,
        reproducibility_bundle_digest="e" * 64,
    )
    changed_registry = registry.with_candidate(extra)

    with pytest.raises(
        ChampionRegistryError,
        match="another registry",
    ):
        apply_promotion(changed_registry, decision)


def test_transition_chain_tampering_is_rejected() -> None:
    (
        _,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        candidate_qualification,
    ) = _qualified_challenger()
    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
    )
    decision = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=candidate_qualification,
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )
    assert decision.transition is not None
    tampered = replace(
        decision.transition,
        prior_transition_digest="f" * 64,
    )

    with pytest.raises(
        ChampionRegistryError,
        match="transition chain mismatch",
    ):
        ChampionRegistry(
            registry_id=registry.registry_id,
            candidates=registry.candidates,
            initial_champion_digest=registry.initial_champion_digest,
            transitions=(tampered,),
        )


def test_rejected_candidate_and_promotion_cannot_be_evidence() -> None:
    (
        repro,
        experiment,
        benchmark,
        benchmark_qualification,
        _,
        metric,
        challenger,
        _,
    ) = _qualified_challenger()
    rejected_candidate = qualify_candidate_artifact(
        candidate=replace(challenger, candidate_ref="candidate:wrong"),
        experiment=experiment,
        benchmark=benchmark,
        benchmark_qualification=benchmark_qualification,
        reproducibility=repro,
    )
    with pytest.raises(
        ChampionRegistryError,
        match="cannot become promotion evidence",
    ):
        rejected_candidate.accepted_evidence_ref()

    champion = _champion()
    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    baseline, candidate, claim = _comparison(
        champion,
        challenger,
        experiment,
        benchmark,
        benchmark_qualification,
        metric,
        baseline_score=0.9,
        challenger_score=0.8,
    )
    rejected_promotion = evaluate_promotion(
        registry=registry,
        challenger=challenger,
        candidate_qualification=replace(
            rejected_candidate,
            candidate_digest=challenger.candidate_digest,
        ),
        benchmark_qualification=benchmark_qualification,
        improvement_claim=claim,
        baseline_observation=baseline,
        candidate_observation=candidate,
    )
    assert rejected_promotion.accepted is False
    with pytest.raises(
        ChampionRegistryError,
        match="cannot become promotion evidence",
    ):
        rejected_promotion.accepted_evidence_ref()


def test_candidate_and_registry_identity_use_shared_canonical_contract_bytes() -> None:
    candidate = CandidateArtifact(
        candidate_id="candidate-v1",
        version="v1",
        candidate_ref="candidate:v1",
        artifact_digest="a" * 64,
        source_commit="b" * 40,
        experiment_manifest_digest="c" * 64,
        benchmark_manifest_digest="d" * 64,
        benchmark_qualification_digest="e" * 64,
        reproducibility_bundle_digest="f" * 64,
        tags=("core",),
    )

    assert candidate.candidate_digest == hashlib.sha256(
        canonical_json_bytes(candidate.payload())
    ).hexdigest()

    registry = ChampionRegistry(
        registry_id="core-model",
        candidates=(candidate,),
        initial_champion_digest=candidate.candidate_digest,
    )
    expected_registry = {
        "schema_version": registry.schema_version,
        "task_id": "P1-LEARN-03",
        "accountability_id": "ACC-P1-LEARN-03",
        "registry_id": registry.registry_id,
        "candidates": [candidate.payload()],
        "initial_champion_digest": candidate.candidate_digest,
        "transitions": [],
        "current_champion_digest": candidate.candidate_digest,
        "production_authority": False,
    }
    assert registry.registry_digest == hashlib.sha256(
        canonical_json_bytes(expected_registry)
    ).hexdigest()


def test_champion_registry_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/eval/champion_registry.py"
    mirror = root / "skeleton/ai/evaluation/champion_registry.py"

    assert source.read_bytes() == mirror.read_bytes()
