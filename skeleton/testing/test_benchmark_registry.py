from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.reproducibility import ReproducibilityBundle
from skeleton.eval.benchmark_registry import (
    BenchmarkDataset,
    BenchmarkEnvironment,
    BenchmarkManifest,
    BenchmarkMetric,
    BenchmarkQualificationDecision,
    BenchmarkRegistry,
    BenchmarkRegistryError,
    BenchmarkScoreObservation,
    BenchmarkSplit,
    BenchmarkSplitRole,
    ContaminationStatus,
    evaluate_improvement_claim,
    qualify_benchmark,
)
from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    MetricDirection,
    TrafficMode,
)


def _evidence(source: str = "scan://benchmark") -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest="a" * 64,
        category="contamination_scan",
    )


def _experiment(
    *,
    traffic_mode: TrafficMode = TrafficMode.OFFLINE,
    environment_id: str = "env-ci",
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="experiment-1",
        hypothesis="Candidate improves exact-match quality.",
        owner="team-eval",
        source_commit="b" * 40,
        environment_id=environment_id,
        candidate_ref="candidate-v2",
        eligibility=ExperimentEligibility(
            traffic_mode=traffic_mode,
            max_traffic_fraction=(
                0.0 if traffic_mode is TrafficMode.OFFLINE else 0.1
            ),
            allowed_data_classes=("public",),
        ),
        budget=ExperimentBudget(
            max_samples=1000,
            max_tokens=100000,
            max_cost_units=100.0,
            max_wall_time_s=3600.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="exact-match",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=100,
                source="independent-evaluator",
            ),
        ),
    )


def _repro(
    *,
    environment_digest: str = "c" * 64,
    runner_digest: str = "d" * 64,
    source_date_epoch: int = 1_800_000_000,
) -> ReproducibilityBundle:
    return ReproducibilityBundle(
        repository="Apeloff1/Skeleton",
        commit_sha="b" * 40,
        task_id="P1-EVID-05",
        accountability_id="ACC-P1-EVID-05",
        configuration_digest="1" * 64,
        environment_digest=environment_digest,
        verifier_id="github-actions:p1-reproducibility-bundle",
        verifier_digest="2" * 64,
        test_manifest_digest="3" * 64,
        runner_id="runner-ci",
        runner_digest=runner_digest,
        budget_id="budget-ci",
        budget_digest="4" * 64,
        source_date_epoch=source_date_epoch,
        expected_subject_digest="5" * 64,
        expected_evidence_digest="6" * 64,
        inputs=(
            EvidenceRef(
                source="fixture://repro-input",
                digest="7" * 64,
                category="fixture",
            ),
        ),
    )


def _manifest(
    experiment: ExperimentManifest,
    repro: ReproducibilityBundle,
    *,
    contamination_status: ContaminationStatus = ContaminationStatus.CLEAN,
    contamination_sources: tuple[str, ...] = (),
    metric_direction: MetricDirection = MetricDirection.MAXIMIZE,
    metric_minimum_samples: int = 100,
) -> BenchmarkManifest:
    dataset = BenchmarkDataset(
        dataset_id="qa-benchmark",
        version="v1",
        source_ref="dataset://qa-benchmark/v1",
        source_digest="8" * 64,
        content_digest="9" * 64,
        license_id="internal-eval",
    )
    split = BenchmarkSplit(
        split_id="test",
        role=BenchmarkSplitRole.TEST,
        dataset_digest=dataset.digest,
        content_digest="0" * 64,
        sample_count=500,
        contamination_status=contamination_status,
        contamination_evidence=(_evidence(),),
        contamination_sources=contamination_sources,
    )
    metric = BenchmarkMetric(
        metric_id="exact-match",
        direction=metric_direction,
        minimum_samples=metric_minimum_samples,
        evaluator_id="independent-evaluator",
        evaluator_digest="e" * 64,
    )
    return BenchmarkManifest(
        benchmark_id="qa-core",
        version="v1",
        datasets=(dataset,),
        splits=(split,),
        metrics=(metric,),
        primary_metric_id="exact-match",
        environment=BenchmarkEnvironment(
            environment_id=experiment.environment_id,
            environment_digest=repro.environment_digest,
            runner_digest=repro.runner_digest,
            dependency_lock_digest="f" * 64,
            source_date_epoch=repro.source_date_epoch,
        ),
        experiment_manifest_digest=experiment.manifest_digest,
        reproducibility_bundle_digest=repro.bundle_digest,
        tags=("core", "promotion"),
    )


def _qualified():
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(experiment, repro)
    qualification = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("test",),
    )
    return experiment, repro, manifest, qualification


def test_clean_benchmark_qualifies() -> None:
    experiment, repro, manifest, qualification = _qualified()

    assert qualification.accepted is True
    assert qualification.reasons == ()
    assert qualification.experiment_manifest_digest == experiment.manifest_digest
    assert qualification.reproducibility_bundle_digest == repro.bundle_digest
    evidence = qualification.accepted_evidence_ref()
    assert evidence.category == "benchmark_qualification"
    assert evidence.digest == qualification.decision_digest
    assert BenchmarkRegistry((manifest,)).registry_digest


@pytest.mark.parametrize(
    ("status", "sources"),
    (
        (ContaminationStatus.UNKNOWN, ()),
        (ContaminationStatus.SUSPECTED, ("training-corpus",)),
        (ContaminationStatus.CONFIRMED, ("training-corpus",)),
    ),
)
def test_non_clean_contamination_blocks(
    status: ContaminationStatus,
    sources: tuple[str, ...],
) -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(
        experiment,
        repro,
        contamination_status=status,
        contamination_sources=sources,
    )

    decision = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("test",),
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("contamination-not-clean:test:")
        for reason in decision.reasons
    )


def test_experiment_and_reproducibility_substitution_block() -> None:
    experiment, repro, manifest, _ = _qualified()
    other_experiment = replace(
        experiment,
        candidate_ref="candidate-other",
    )
    other_repro = replace(
        repro,
        environment_digest="0" * 64,
    )

    decision = qualify_benchmark(
        manifest=manifest,
        experiment=other_experiment,
        reproducibility=other_repro,
        evaluated_split_ids=("test",),
    )

    assert decision.accepted is False
    assert "experiment-manifest-digest-mismatch" in decision.reasons
    assert "reproducibility-bundle-digest-mismatch" in decision.reasons
    assert "environment-digest-mismatch" in decision.reasons


def test_experiment_source_commit_must_match_reproducibility() -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(experiment, repro)
    drifted = replace(experiment, source_commit="c" * 40)
    manifest = replace(
        manifest,
        experiment_manifest_digest=drifted.manifest_digest,
    )

    decision = qualify_benchmark(
        manifest=manifest,
        experiment=drifted,
        reproducibility=repro,
        evaluated_split_ids=("test",),
    )

    assert decision.accepted is False
    assert "experiment-source-commit-mismatch" in decision.reasons


def test_shadow_experiment_cannot_qualify_as_offline_benchmark() -> None:
    experiment = _experiment(traffic_mode=TrafficMode.SHADOW)
    repro = _repro()
    manifest = _manifest(experiment, repro)

    decision = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("test",),
    )

    assert decision.accepted is False
    assert "benchmark-experiment-must-be-offline" in decision.reasons


def test_metric_direction_and_sample_policy_must_match_experiment() -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(
        experiment,
        repro,
        metric_direction=MetricDirection.MINIMIZE,
        metric_minimum_samples=50,
    )

    decision = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("test",),
    )

    assert decision.accepted is False
    assert "metric-direction-mismatch:exact-match" in decision.reasons
    assert "metric-minimum-samples-too-low:exact-match" in decision.reasons


def test_unknown_or_non_evaluation_split_blocks() -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(experiment, repro)
    train = replace(
        manifest.splits[0],
        split_id="train",
        role=BenchmarkSplitRole.TRAIN,
        content_digest="1" * 64,
    )
    manifest = replace(manifest, splits=(train, manifest.splits[0]))

    unknown = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("missing",),
    )
    assert unknown.accepted is False
    assert "unknown-evaluation-split:missing" in unknown.reasons
    assert "no-evaluation-split-selected" in unknown.reasons

    train_only = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("train",),
    )
    assert train_only.accepted is False
    assert "non-evaluation-split-selected:train" in train_only.reasons


def test_dataset_and_split_lineage_fail_closed() -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(experiment, repro)
    split = replace(
        manifest.splits[0],
        dataset_digest="0" * 64,
    )

    with pytest.raises(BenchmarkRegistryError, match="unknown dataset digest"):
        replace(manifest, splits=(split,))


def test_duplicate_split_content_is_rejected() -> None:
    experiment = _experiment()
    repro = _repro()
    manifest = _manifest(experiment, repro)
    duplicate = replace(
        manifest.splits[0],
        split_id="holdout",
        role=BenchmarkSplitRole.HOLDOUT,
    )

    with pytest.raises(
        BenchmarkRegistryError,
        match="split content digests must be unique",
    ):
        replace(manifest, splits=(manifest.splits[0], duplicate))


def test_improvement_claim_accepts_independent_better_candidate() -> None:
    experiment, _, manifest, qualification = _qualified()
    baseline = BenchmarkScoreObservation(
        benchmark_manifest_digest=manifest.manifest_digest,
        split_id="test",
        metric_id="exact-match",
        candidate_ref="champion-v1",
        score=0.80,
        sample_count=500,
        evaluator_id="independent-evaluator",
        evaluator_digest="e" * 64,
    )
    candidate = replace(
        baseline,
        candidate_ref=experiment.candidate_ref,
        score=0.86,
    )

    decision = evaluate_improvement_claim(
        manifest=manifest,
        qualification=qualification,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
    )

    assert decision.accepted is True
    assert decision.improvement == pytest.approx(0.06)
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "benchmark_improvement_claim"
    assert evidence.digest == decision.decision_digest


def test_improvement_claim_rejects_non_improvement() -> None:
    experiment, _, manifest, qualification = _qualified()
    baseline = BenchmarkScoreObservation(
        benchmark_manifest_digest=manifest.manifest_digest,
        split_id="test",
        metric_id="exact-match",
        candidate_ref="champion-v1",
        score=0.80,
        sample_count=500,
        evaluator_id="independent-evaluator",
        evaluator_digest="e" * 64,
    )
    candidate = replace(
        baseline,
        candidate_ref=experiment.candidate_ref,
        score=0.79,
    )

    decision = evaluate_improvement_claim(
        manifest=manifest,
        qualification=qualification,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
    )

    assert decision.accepted is False
    assert "candidate-did-not-improve" in decision.reasons


def test_improvement_claim_rejects_under_sampling_and_evaluator_drift() -> None:
    experiment, _, manifest, qualification = _qualified()
    baseline = BenchmarkScoreObservation(
        benchmark_manifest_digest=manifest.manifest_digest,
        split_id="test",
        metric_id="exact-match",
        candidate_ref="champion-v1",
        score=0.80,
        sample_count=50,
        evaluator_id="wrong-evaluator",
        evaluator_digest="1" * 64,
    )
    candidate = replace(
        baseline,
        candidate_ref=experiment.candidate_ref,
        score=0.90,
    )

    decision = evaluate_improvement_claim(
        manifest=manifest,
        qualification=qualification,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
    )

    assert decision.accepted is False
    assert "baseline-sample-count-too-low" in decision.reasons
    assert "candidate-sample-count-too-low" in decision.reasons
    assert "baseline-evaluator-id-mismatch" in decision.reasons
    assert "candidate-evaluator-digest-mismatch" in decision.reasons


def test_rejected_qualification_and_claim_cannot_be_evidence() -> None:
    experiment, repro, manifest, _ = _qualified()
    qualification = qualify_benchmark(
        manifest=manifest,
        experiment=experiment,
        reproducibility=repro,
        evaluated_split_ids=("missing",),
    )
    assert qualification.accepted is False
    with pytest.raises(BenchmarkRegistryError, match="cannot become promotion"):
        qualification.accepted_evidence_ref()

    baseline = BenchmarkScoreObservation(
        benchmark_manifest_digest=manifest.manifest_digest,
        split_id="test",
        metric_id="exact-match",
        candidate_ref="champion-v1",
        score=0.90,
        sample_count=500,
        evaluator_id="independent-evaluator",
        evaluator_digest="e" * 64,
    )
    candidate = replace(
        baseline,
        candidate_ref=experiment.candidate_ref,
        score=0.80,
    )
    accepted_qualification = BenchmarkQualificationDecision(
        accepted=True,
        reasons=(),
        benchmark_manifest_digest=manifest.manifest_digest,
        experiment_manifest_digest=experiment.manifest_digest,
        reproducibility_bundle_digest=repro.bundle_digest,
        evaluated_split_ids=("test",),
    )
    claim = evaluate_improvement_claim(
        manifest=manifest,
        qualification=accepted_qualification,
        experiment=experiment,
        baseline=baseline,
        candidate=candidate,
    )
    assert claim.accepted is False
    with pytest.raises(BenchmarkRegistryError, match="cannot become promotion"):
        claim.accepted_evidence_ref()
