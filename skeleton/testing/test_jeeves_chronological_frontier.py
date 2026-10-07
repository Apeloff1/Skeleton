from __future__ import annotations

import pytest

from skeleton.jeeves.agent.types import AgentContractError
from skeleton.jeeves.science.chronological_frontier import (
    ChronologicalFrontierTournament,
    ForecastFamily,
    ForecastTechnique,
    FrontierDecisionStatus,
    FrontierTournamentPolicy,
    HistoricalEvaluation,
    MetricDirection,
    MetricRule,
    TechniqueRegistry,
    default_prediction_lineage,
)


def _modern_metrics(scale: float = 1.0) -> dict[str, float]:
    return {
        "mae": 1.00 * scale,
        "rmse": 1.20 * scale,
        "brier": 0.18 * scale,
        "log_loss": 0.52 * scale,
        "coverage_gap": 0.08 * scale,
        "crps": 0.62 * scale,
        "calibration_ece": 0.07 * scale,
        "energy_efficiency": 0.55 / scale,
    }


def _evaluation(
    technique_id: str,
    year: int,
    *,
    metrics: dict[str, float] | None = None,
    benchmark: str = "shared-benchmark",
    window: str = "shared-window",
    knowledge_year: int | None = None,
    data_cutoff_year: int | None = None,
    calibration_checked: bool = True,
    folds: int = 64,
    series: int = 250,
    domains: int = 4,
    runs: int = 4,
) -> HistoricalEvaluation:
    return HistoricalEvaluation(
        technique_id=technique_id,
        as_of_year=year,
        knowledge_year=year if knowledge_year is None else knowledge_year,
        data_cutoff_year=year if data_cutoff_year is None else data_cutoff_year,
        benchmark_id=benchmark,
        target_window_fingerprint=window,
        folds=folds,
        series_count=series,
        domain_count=domains,
        independent_runs=runs,
        metrics=metrics or _modern_metrics(),
        leakage_audited=True,
        temporal_custody_verified=True,
        provenance_ids=(f"evidence:{technique_id}:{year}",),
        calibration_checked=calibration_checked,
    )


def test_default_prediction_lineage_spans_precomputing_history_to_2026() -> None:
    registry = default_prediction_lineage()
    ordered = registry.ordered()
    assert ordered[0].available_year == 1657
    assert ordered[-1].available_year == 2026
    assert any(item.technique_id == "bayes_inverse_1763" for item in ordered)
    assert any(item.technique_id == "kalman_1960" for item in ordered)
    assert any(item.technique_id == "timesfm_2024" for item in ordered)
    assert any(item.technique_id == "accuracy_energy_2026" for item in ordered)
    assert tuple((item.available_year, item.technique_id) for item in ordered) == tuple(
        sorted((item.available_year, item.technique_id) for item in ordered)
    )


def test_registry_rejects_future_predecessor_and_requires_registration_order() -> None:
    old = ForecastTechnique(
        "old",
        1900,
        "Old",
        ForecastFamily.REGRESSION,
        "baseline",
    )
    future = ForecastTechnique(
        "future",
        2000,
        "Future",
        ForecastFamily.NEURAL,
        "later challenger",
        predecessors=("old",),
    )
    registry = TechniqueRegistry((old, future))
    with pytest.raises(AgentContractError):
        registry.register(
            ForecastTechnique(
                "bad",
                1950,
                "Bad",
                ForecastFamily.PROBABILISTIC,
                "invalid predecessor chronology",
                predecessors=("future",),
            )
        )


def test_historical_evaluation_rejects_future_knowledge_and_future_data() -> None:
    with pytest.raises(AgentContractError, match="future knowledge"):
        _evaluation("holt_smoothing_1957", 1960, knowledge_year=1961)
    with pytest.raises(AgentContractError, match="future observations"):
        _evaluation("holt_smoothing_1957", 1960, data_cutoff_year=1961)


def test_same_target_custody_is_required_for_challenger_comparison() -> None:
    tournament = ChronologicalFrontierTournament(default_prediction_lineage())
    incumbent = _evaluation("holt_smoothing_1957", 1960, window="window-a")
    challenger = _evaluation("kalman_1960", 1960, metrics=_modern_metrics(0.8), window="window-b")
    result = tournament.compare(incumbent, challenger)
    assert result.status is FrontierDecisionStatus.INCOMPARABLE
    assert "different_target_custody" in result.failures


def test_technique_cannot_compete_before_historical_availability() -> None:
    tournament = ChronologicalFrontierTournament(default_prediction_lineage())
    incumbent = _evaluation("box_jenkins_1970", 2023)
    future = _evaluation("timesfm_2024", 2023, metrics=_modern_metrics(0.5))
    result = tournament.compare(incumbent, future)
    assert result.status is FrontierDecisionStatus.NOT_YET_AVAILABLE
    assert "technique_not_historically_available" in result.failures


def test_stronger_same_year_challenger_can_earn_promotion() -> None:
    tournament = ChronologicalFrontierTournament(default_prediction_lineage())
    incumbent = _evaluation("box_jenkins_1970", 2024, metrics=_modern_metrics(1.0))
    challenger = _evaluation("timesfm_2024", 2024, metrics=_modern_metrics(0.70))
    result = tournament.compare(incumbent, challenger)
    assert result.status is FrontierDecisionStatus.PROMOTE
    assert result.adjusted_gain >= tournament.policy.minimum_adjusted_gain
    assert any(item.meaningful_improvement for item in result.metrics)
    assert result.complexity_penalty > 0.0


def test_mandatory_metric_regression_blocks_promotion_even_when_average_improves() -> None:
    rules = (
        MetricRule("mae", MetricDirection.LOWER_IS_BETTER, 0.9, introduced_year=1805, mandatory_from_year=1805),
        MetricRule(
            "log_loss",
            MetricDirection.LOWER_IS_BETTER,
            0.1,
            introduced_year=1952,
            mandatory_from_year=1952,
            regression_tolerance=0.01,
        ),
    )
    registry = TechniqueRegistry(
        (
            ForecastTechnique("inc", 1900, "Inc", ForecastFamily.REGRESSION, "baseline", complexity_rank=1),
            ForecastTechnique("chall", 1952, "Chall", ForecastFamily.PROBABILISTIC, "challenger", complexity_rank=2),
        )
    )
    tournament = ChronologicalFrontierTournament(registry, metric_rules=rules)
    incumbent = _evaluation("inc", 2000, metrics={"mae": 10.0, "log_loss": 0.5})
    challenger = _evaluation("chall", 2000, metrics={"mae": 1.0, "log_loss": 0.8})
    result = tournament.compare(incumbent, challenger)
    assert result.weighted_gain > 0
    assert result.status is FrontierDecisionStatus.INSUFFICIENT_EVIDENCE
    assert "mandatory_metric_regression:log_loss" in result.failures


def test_complexity_penalty_prevents_gratuitous_replacement() -> None:
    registry = TechniqueRegistry(
        (
            ForecastTechnique("simple", 2000, "Simple", ForecastFamily.REGRESSION, "simple", complexity_rank=1),
            ForecastTechnique("huge", 2001, "Huge", ForecastFamily.NEURAL, "huge", complexity_rank=100),
        )
    )
    rules = (
        MetricRule("mae", MetricDirection.LOWER_IS_BETTER, 1.0, introduced_year=1805, mandatory_from_year=1805),
    )
    tournament = ChronologicalFrontierTournament(
        registry,
        metric_rules=rules,
        policy=FrontierTournamentPolicy(
            minimum_folds=1,
            minimum_series=1,
            minimum_domains=1,
            minimum_independent_runs=1,
            minimum_adjusted_gain=0.01,
            complexity_penalty_per_rank=0.01,
            require_calibration_after_year=2100,
        ),
    )
    incumbent = _evaluation("simple", 2001, metrics={"mae": 1.0}, folds=1, series=1, domains=1, runs=1)
    challenger = _evaluation("huge", 2001, metrics={"mae": 0.99}, folds=1, series=1, domains=1, runs=1)
    result = tournament.compare(incumbent, challenger)
    assert result.weighted_gain > 0.0
    assert result.complexity_penalty > result.weighted_gain
    assert result.status is FrontierDecisionStatus.HOLD


def test_missing_calibration_after_policy_year_freezes_promotion() -> None:
    tournament = ChronologicalFrontierTournament(default_prediction_lineage())
    incumbent = _evaluation("box_jenkins_1970", 2024, calibration_checked=True)
    challenger = _evaluation(
        "timesfm_2024",
        2024,
        metrics=_modern_metrics(0.5),
        calibration_checked=False,
    )
    result = tournament.compare(incumbent, challenger)
    assert result.status is FrontierDecisionStatus.INSUFFICIENT_EVIDENCE
    assert "missing_calibration_check" in result.failures


def test_replay_moves_year_by_year_and_preserves_incumbent_when_evidence_is_missing() -> None:
    registry = default_prediction_lineage()
    tournament = ChronologicalFrontierTournament(registry)
    metrics_1960_inc = {
        "mae": 1.0,
        "rmse": 1.2,
        "brier": 0.20,
        "log_loss": 0.60,
        "coverage_gap": 0.10,
    }
    metrics_1960_chall = {
        "mae": 0.75,
        "rmse": 0.90,
        "brier": 0.15,
        "log_loss": 0.45,
        "coverage_gap": 0.08,
    }
    evaluations = (
        _evaluation("holt_smoothing_1957", 1959, metrics=metrics_1960_inc),
        _evaluation("holt_smoothing_1957", 1960, metrics=metrics_1960_inc),
        _evaluation("kalman_1960", 1960, metrics=metrics_1960_chall),
        # 1961 intentionally has no evidence for the promoted incumbent.
        _evaluation("holt_smoothing_1957", 1961, metrics=metrics_1960_inc),
    )
    report = tournament.replay("holt_smoothing_1957", evaluations, start_year=1959, end_year=1961)
    by_year = {item.year: item for item in report.decisions}
    assert by_year[1959].incumbent_after == "holt_smoothing_1957"
    assert by_year[1960].status is FrontierDecisionStatus.PROMOTE
    assert by_year[1960].incumbent_after == "kalman_1960"
    assert by_year[1961].status is FrontierDecisionStatus.INSUFFICIENT_EVIDENCE
    assert by_year[1961].incumbent_after == "kalman_1960"
    assert report.final_incumbent == "kalman_1960"
    assert report.promotion_years == (1960,)


def test_old_techniques_remain_in_registry_after_frontier_moves() -> None:
    registry = default_prediction_lineage()
    assert registry.get("holt_smoothing_1957").survives_as
    assert registry.get("box_jenkins_1970").survives_as
    assert registry.get("kalman_1960").survives_as
    assert registry.get("timesfm_2024").survives_as


def test_frontier_fingerprints_are_deterministic() -> None:
    tournament = ChronologicalFrontierTournament(default_prediction_lineage())
    left = _evaluation("box_jenkins_1970", 2024)
    right = _evaluation("timesfm_2024", 2024, metrics=_modern_metrics(0.8))
    first = tournament.compare(left, right)
    second = tournament.compare(left, right)
    assert first.fingerprint == second.fingerprint
