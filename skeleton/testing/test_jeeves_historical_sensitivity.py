from __future__ import annotations

import pytest

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
    HistoricalSensitivityError,
    SensitivityPolicy,
    summarize_sensitivity,
)


NOW = 1_000.0
REASON = BenchmarkDefinition("sens-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("sens-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)


def _snapshot(snapshot_id, model, benchmark, score):
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=900.0,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=900.0,
        provenance=provenance,
    )


def _policy():
    return SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )


def _registry(scores):
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    models = []
    for index, (reason, code) in enumerate(scores):
        model = ModelIdentity("provider", f"model-{index}", "r1")
        models.append(model)
        registry.ingest(_snapshot(f"m{index}-r", model, REASON, reason))
        registry.ingest(_snapshot(f"m{index}-c", model, CODE, code))
    return registry, tuple(models)


def test_clear_leader_is_robust_to_weight_shifts() -> None:
    registry, models = _registry([(95.0, 95.0), (80.0, 82.0), (70.0, 90.0)])
    report = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
        sensitivity_policy=SensitivityPolicy(
            relative_weight_shift=0.20,
            min_champion_share=0.80,
            max_base_champion_regret=0.01,
        ),
    ).analyze()
    assert report.base_champion == models[0]
    assert report.scenario_count == 5
    assert report.champion_share == 1.0
    assert report.flip_rate == 0.0
    assert report.max_base_champion_regret == 0.0
    assert report.robust is True


def test_tradeoff_champion_can_flip_under_reasonable_weight_shift() -> None:
    registry, models = _registry([(90.0, 80.0), (80.0, 89.0)])
    report = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
        sensitivity_policy=SensitivityPolicy(
            relative_weight_shift=0.20,
            min_champion_share=0.90,
            max_base_champion_regret=0.001,
        ),
    ).analyze()
    assert report.base_champion == models[0]
    assert report.flip_rate > 0.0
    assert any(item.champion == models[1] for item in report.scenarios)
    assert report.max_base_champion_regret > 0.0
    assert report.robust is False


def test_scenario_matrix_perturbs_each_domain_up_and_down() -> None:
    registry, _ = _registry([(90.0, 90.0), (80.0, 80.0)])
    report = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
        sensitivity_policy=SensitivityPolicy(relative_weight_shift=0.10),
    ).analyze()
    names = {item.scenario_id for item in report.scenarios}
    assert "base" in names
    assert "reasoning:up:0.100000" in names
    assert "reasoning:down:0.100000" in names
    assert "coding:up:0.100000" in names
    assert "coding:down:0.100000" in names


def test_explicit_model_scope_is_respected() -> None:
    registry, models = _registry([(90.0, 80.0), (80.0, 95.0)])
    report = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
    ).analyze(models=[models[0]])
    assert report.base_champion == models[0]
    assert report.champion_share == 1.0
    assert all(item.champion == models[0] for item in report.scenarios)


def test_report_is_deterministic() -> None:
    registry, _ = _registry([(90.0, 80.0), (80.0, 89.0)])
    analyzer = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
        sensitivity_policy=SensitivityPolicy(relative_weight_shift=0.20),
    )
    first = analyzer.analyze()
    second = analyzer.analyze()
    assert first.report_fingerprint == second.report_fingerprint
    assert first.champion_counts == second.champion_counts


def test_zero_shift_is_rejected() -> None:
    with pytest.raises(HistoricalSensitivityError):
        SensitivityPolicy(relative_weight_shift=0.0)


def test_full_down_shift_is_rejected_because_weights_must_remain_positive() -> None:
    with pytest.raises(HistoricalSensitivityError):
        SensitivityPolicy(relative_weight_shift=1.0)


def test_invalid_model_scope_fails_closed() -> None:
    registry, _ = _registry([(90.0, 90.0)])
    analyzer = HistoricalSelectionSensitivityAnalyzer(registry=registry, selection_policy=_policy())
    with pytest.raises(HistoricalSensitivityError):
        analyzer.analyze(models=["not-a-model"])  # type: ignore[list-item]


def test_summary_exposes_robustness_metrics() -> None:
    registry, models = _registry([(95.0, 95.0), (80.0, 80.0)])
    report = HistoricalSelectionSensitivityAnalyzer(
        registry=registry,
        selection_policy=_policy(),
    ).analyze()
    summary = summarize_sensitivity(report)
    assert summary["base_champion"] == models[0].key
    assert summary["scenario_count"] == 5
    assert summary["robust"] is True
    assert summary["report_fingerprint"] == report.report_fingerprint
