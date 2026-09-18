from __future__ import annotations

import pytest

from skeleton.jeeves.historical_backtest import (
    BacktestFold,
    BacktestPlan,
    HistoricalBacktestError,
    TemporalHistoricalBacktester,
    summarize_backtest,
)
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


NOW = 1_000.0
REASON = BenchmarkDefinition(
    benchmark_id="reasoning-backtest",
    revision="v1",
    domain=BenchmarkDomain.REASONING,
    raw_min=0.0,
    raw_max=100.0,
)
SUITE = BenchmarkSuite(
    suite_id="temporal-suite",
    revision="v1",
    benchmark_keys=frozenset({REASON.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING}),
)
POLICY = SelectionPolicy(
    domain_weights={BenchmarkDomain.REASONING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING}),
    minimum_sample_count=1,
    confidence_z=0.0,
    max_snapshot_age_seconds=10_000.0,
)


def _snapshot(snapshot_id: str, model: ModelIdentity, score: float, at: float) -> BenchmarkSnapshot:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=REASON,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=REASON,
        raw_score=score,
        sample_count=100,
        measured_at=at,
        provenance=provenance,
    )


def _registry() -> tuple[HistoricalModelRegistry, ModelIdentity, ModelIdentity]:
    a = ModelIdentity("provider-a", "alpha", "r1")
    b = ModelIdentity("provider-b", "beta", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    # Before fold 1: alpha is the obvious historical winner.
    registry.ingest(_snapshot("a-train", a, 90.0, 90.0))
    registry.ingest(_snapshot("b-train", b, 80.0, 90.0))
    # Fold 1 forward evidence: beta becomes stronger.
    registry.ingest(_snapshot("a-test-1", a, 70.0, 200.0))
    registry.ingest(_snapshot("b-test-1", b, 95.0, 200.0))
    # Fold 2 forward evidence: beta remains stronger.
    registry.ingest(_snapshot("a-test-2", a, 75.0, 300.0))
    registry.ingest(_snapshot("b-test-2", b, 90.0, 300.0))
    return registry, a, b


def _plan() -> BacktestPlan:
    return BacktestPlan(
        plan_id="rolling",
        revision="v1",
        folds=(
            BacktestFold("fold-1", train_end=100.0, test_start=200.0, test_end=201.0),
            BacktestFold("fold-2", train_end=210.0, test_start=300.0, test_end=301.0),
        ),
    )


def test_fold_rejects_temporal_leakage() -> None:
    with pytest.raises(HistoricalBacktestError) as exc:
        BacktestFold("bad", train_end=100.0, test_start=100.0, test_end=110.0)
    assert exc.value.context["reason"] == "temporal_leakage"


def test_plan_requires_chronological_order() -> None:
    late = BacktestFold("late", train_end=200.0, test_start=300.0, test_end=310.0)
    early = BacktestFold("early", train_end=100.0, test_start=150.0, test_end=160.0)
    with pytest.raises(HistoricalBacktestError) as exc:
        BacktestPlan("bad", "v1", (late, early))
    assert exc.value.context["reason"] == "unordered_folds"


def test_plan_rejects_duplicate_fold_ids() -> None:
    with pytest.raises(HistoricalBacktestError) as exc:
        BacktestPlan(
            "bad",
            "v1",
            (
                BacktestFold("same", 100.0, 150.0, 160.0),
                BacktestFold("same", 200.0, 250.0, 260.0),
            ),
        )
    assert exc.value.context["reason"] == "duplicate_fold_id"


def test_backtest_replays_policy_without_future_leakage() -> None:
    registry, a, b = _registry()
    report = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=_plan(),
    ).run()

    assert report.folds[0].selected_model == a
    assert report.folds[0].oracle_model == b
    assert report.folds[0].selected_score == pytest.approx(0.70)
    assert report.folds[0].oracle_score == pytest.approx(0.95)
    assert report.folds[0].regret == pytest.approx(0.25)

    # Fold 2 may use fold-1 observations because they were known by train_end.
    assert report.folds[1].selected_model == b
    assert report.folds[1].oracle_model == b
    assert report.folds[1].selected_score == pytest.approx(0.90)
    assert report.folds[1].regret == pytest.approx(0.0)


def test_future_observation_cannot_change_earlier_fold_selection() -> None:
    registry, a, b = _registry()
    registry.ingest(_snapshot("b-very-future", b, 100.0, 900.0))
    report = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=BacktestPlan(
            "single",
            "v1",
            (BacktestFold("f", 100.0, 200.0, 201.0),),
        ),
    ).run()
    assert report.folds[0].selected_model == a


def test_backtest_aggregates_regret_and_stability() -> None:
    registry, a, b = _registry()
    report = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=_plan(),
    ).run()

    assert report.fold_count == 2
    assert report.mean_selected_score == pytest.approx(0.80)
    assert report.mean_oracle_score == pytest.approx(0.925)
    assert report.mean_regret == pytest.approx(0.125)
    assert report.worst_regret == pytest.approx(0.25)
    assert report.champion_stability == pytest.approx(0.0)
    assert report.unique_selected_models == (a, b)


def test_candidate_scope_limits_selection_and_oracle() -> None:
    registry, _, b = _registry()
    report = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=_plan(),
    ).run(models=[b])
    assert all(fold.selected_model == b for fold in report.folds)
    assert all(fold.oracle_model == b for fold in report.folds)
    assert all(fold.regret == pytest.approx(0.0) for fold in report.folds)


def test_report_fingerprint_is_deterministic() -> None:
    registry, _, _ = _registry()
    backtester = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=_plan(),
    )
    first = backtester.run()
    second = backtester.run()
    assert first.report_fingerprint == second.report_fingerprint
    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.policy_fingerprint == second.policy_fingerprint


def test_missing_training_evidence_fails_closed() -> None:
    registry, _, _ = _registry()
    backtester = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=BacktestPlan(
            "too-early",
            "v1",
            (BacktestFold("f", 10.0, 20.0, 30.0),),
        ),
    )
    with pytest.raises(HistoricalBacktestError) as exc:
        backtester.run()
    assert exc.value.context["reason"] == "no_training_evidence"


def test_selected_model_without_forward_holdout_fails_closed() -> None:
    a = ModelIdentity("provider-a", "alpha", "r1")
    b = ModelIdentity("provider-b", "beta", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a-train", a, 99.0, 90.0))
    registry.ingest(_snapshot("b-train", b, 80.0, 90.0))
    registry.ingest(_snapshot("b-test", b, 90.0, 200.0))
    backtester = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=BacktestPlan(
            "missing-forward",
            "v1",
            (BacktestFold("f", 100.0, 200.0, 201.0),),
        ),
    )
    with pytest.raises(HistoricalBacktestError) as exc:
        backtester.run()
    assert exc.value.context["reason"] == "selected_holdout_missing"


def test_summary_exposes_temporal_evidence_and_regret() -> None:
    registry, _, _ = _registry()
    report = TemporalHistoricalBacktester(
        registry=registry,
        selection_policy=POLICY,
        suite=SUITE,
        plan=_plan(),
    ).run()
    summary = summarize_backtest(report)
    assert summary["fold_count"] == 2
    assert summary["mean_regret"] == pytest.approx(0.125)
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["folds"][0]["train_evidence_fingerprint"]
    assert summary["folds"][0]["test_evidence_fingerprint"]