from __future__ import annotations

import pytest

from skeleton.jeeves.historical_assurance import (
    AssuranceEvidence,
    AssurancePolicy,
    HistoricalAssuranceError,
    HistoricalAssuranceGate,
    summarize_assurance,
)
from skeleton.jeeves.historical_backtest import BacktestFold, BacktestPlan, TemporalHistoricalBacktester
from skeleton.jeeves.historical_calibration import HistoricalScoreCalibrator
from skeleton.jeeves.historical_evaluation import BenchmarkSuite
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_sensitivity import (
    HistoricalSelectionSensitivityAnalyzer,
    SensitivityPolicy,
)


NOW = 100.0
BENCHMARK = BenchmarkDefinition(
    "assurance-reason",
    "v1",
    BenchmarkDomain.REASONING,
    0.0,
    100.0,
)
SUITE = BenchmarkSuite(
    suite_id="assurance-suite",
    revision="v1",
    benchmark_keys=frozenset({BENCHMARK.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING}),
)
SELECTION = SelectionPolicy(
    domain_weights={BenchmarkDomain.REASONING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING}),
    minimum_sample_count=1,
    confidence_z=0.0,
    max_snapshot_age_seconds=1_000.0,
)
PLAN = BacktestPlan(
    plan_id="assurance-plan",
    revision="v1",
    folds=(
        BacktestFold("fold-1", 10.0, 20.0, 21.0),
        BacktestFold("fold-2", 30.0, 40.0, 41.0),
        BacktestFold("fold-3", 50.0, 60.0, 61.0),
    ),
)


def _snapshot(snapshot_id, model, score, measured_at):
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=BENCHMARK,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=BENCHMARK,
        raw_score=score,
        sample_count=100,
        measured_at=measured_at,
        provenance=provenance,
    )


def _evidence():
    candidate = ModelIdentity("provider", "candidate", "r1")
    runner = ModelIdentity("provider", "runner", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for measured_at, candidate_score, runner_score in [
        (5.0, 90.0, 80.0),
        (20.0, 91.0, 81.0),
        (40.0, 92.0, 82.0),
        (60.0, 93.0, 83.0),
    ]:
        registry.ingest(_snapshot(f"c-{int(measured_at)}", candidate, candidate_score, measured_at))
        registry.ingest(_snapshot(f"r-{int(measured_at)}", runner, runner_score, measured_at))

    backtest = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=SELECTION,
        suite=SUITE,
        plan=PLAN,
    ).run(models=[candidate, runner])
    calibration = HistoricalScoreCalibrator.fit_backtest(backtest, bins=3)
    sensitivity = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=SELECTION,
        sensitivity_policy=SensitivityPolicy(
            relative_weight_shift=0.20,
            min_champion_share=0.80,
            max_base_champion_regret=0.02,
        ),
    ).analyze(models=[candidate, runner])
    return AssuranceEvidence(
        candidate=candidate,
        backtest=backtest,
        calibration=calibration,
        sensitivity=sensitivity,
    )


def test_well_supported_candidate_passes_assurance() -> None:
    evidence = _evidence()
    report = HistoricalAssuranceGate(
        AssurancePolicy(
            min_backtest_folds=3,
            max_mean_regret=0.01,
            max_worst_regret=0.01,
            min_champion_stability=0.90,
            max_calibration_mae=0.10,
            max_calibration_rmse=0.10,
            min_calibration_samples=3,
            min_sensitivity_champion_share=0.90,
            max_sensitivity_regret=0.01,
        )
    ).evaluate(evidence)

    assert report.passed is True
    assert report.failed_count == 0
    assert report.passed_count == len(report.checks)
    assert report.reasons == ()


def test_insufficient_calibration_samples_fails_closed() -> None:
    evidence = _evidence()
    report = HistoricalAssuranceGate(
        AssurancePolicy(
            min_backtest_folds=3,
            min_calibration_samples=4,
        )
    ).evaluate(evidence)
    assert report.passed is False
    assert "calibration_min_samples" in report.reasons


def test_required_drift_report_can_be_enforced_for_upgrade() -> None:
    evidence = _evidence()
    report = HistoricalAssuranceGate(
        AssurancePolicy(
            require_drift_report_for_upgrade=True,
        )
    ).evaluate(evidence)
    assert report.passed is False
    assert "lineage_drift_report_present" in report.reasons


def test_candidate_must_match_sensitivity_base_champion() -> None:
    evidence = _evidence()
    wrong = ModelIdentity("provider", "wrong", "r1")
    with pytest.raises(HistoricalAssuranceError):
        AssuranceEvidence(
            candidate=wrong,
            backtest=evidence.backtest,
            calibration=evidence.calibration,
            sensitivity=evidence.sensitivity,
        )


def test_policy_rejects_incoherent_regret_thresholds() -> None:
    with pytest.raises(HistoricalAssuranceError):
        AssurancePolicy(max_mean_regret=0.20, max_worst_regret=0.10)


def test_policy_rejects_incoherent_calibration_thresholds() -> None:
    with pytest.raises(HistoricalAssuranceError):
        AssurancePolicy(max_calibration_mae=0.20, max_calibration_rmse=0.10)


def test_assurance_report_is_deterministic() -> None:
    evidence = _evidence()
    gate = HistoricalAssuranceGate()
    first = gate.evaluate(evidence)
    second = gate.evaluate(evidence)
    assert first.report_fingerprint == second.report_fingerprint
    assert first.checks == second.checks


def test_summary_exposes_evidence_fingerprints_and_checks() -> None:
    evidence = _evidence()
    report = HistoricalAssuranceGate().evaluate(evidence)
    summary = summarize_assurance(report)
    assert summary["candidate"] == evidence.candidate.key
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["backtest_fingerprint"] == evidence.backtest.report_fingerprint
    assert summary["calibration_fingerprint"] == evidence.calibration.report_fingerprint
    assert summary["sensitivity_fingerprint"] == evidence.sensitivity.report_fingerprint
    assert summary["checks"]