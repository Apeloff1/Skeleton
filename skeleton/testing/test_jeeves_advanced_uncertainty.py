from __future__ import annotations

import math

import pytest

from skeleton.jeeves.agent.advanced_uncertainty import (
    AbstentionPolicy,
    AdvancedLens,
    CalibrationDiagnostics,
    ConformalControl,
    ConformalExample,
    DistributionShift,
    ForecastCase,
    InformationDiagnostics,
    LensMeasurement,
    LensRegistry,
    ProperScoring,
    RiskDiagnostics,
    SelectivePrediction,
    SemanticCluster,
    UncertaintyAxis,
    UncertaintyProfiler,
)


def test_proper_scores_reward_better_binary_forecasts() -> None:
    good = (
        ForecastCase(0.95, True),
        ForecastCase(0.90, True),
        ForecastCase(0.10, False),
        ForecastCase(0.05, False),
    )
    weak = (
        ForecastCase(0.60, True),
        ForecastCase(0.55, True),
        ForecastCase(0.45, False),
        ForecastCase(0.40, False),
    )
    assert ProperScoring.brier(good) < ProperScoring.brier(weak)
    assert ProperScoring.log_score(good) < ProperScoring.log_score(weak)


def test_crps_empirical_is_zero_for_perfect_degenerate_forecast() -> None:
    assert ProperScoring.crps_empirical((3.0, 3.0, 3.0), 3.0) == pytest.approx(0.0)
    assert ProperScoring.crps_empirical((2.0, 3.0, 4.0), 3.0) > 0.0


def test_calibration_tracks_reliability_and_sharpness_separately() -> None:
    cases = tuple(
        ForecastCase(probability, outcome)
        for probability, outcome in (
            (0.9, True),
            (0.8, True),
            (0.2, False),
            (0.1, False),
            (0.55, True),
            (0.45, False),
        )
    )
    report = CalibrationDiagnostics.evaluate(cases, bins=5)
    assert report.brier >= 0.0
    assert report.log_score >= 0.0
    assert 0.0 <= report.ece <= 1.0
    assert report.sharpness_variance >= 0.0
    assert report.fingerprint


def test_semantic_entropy_operates_on_meaning_clusters_not_string_count() -> None:
    clusters = (
        SemanticCluster("yes", 0.75, ("yes", "certainly", "affirmative")),
        SemanticCluster("no", 0.25, ("no", "negative")),
    )
    measurement = InformationDiagnostics.semantic_entropy(clusters)
    assert measurement.lens is AdvancedLens.SEMANTIC_ENTROPY
    assert measurement.sample_size == 5.0
    assert measurement.value > 0.0
    assert 0.0 < measurement.normalized_risk < 1.0


def test_mutual_information_separates_model_disagreement_from_within_model_entropy() -> None:
    disagreement = InformationDiagnostics.mutual_information_from_ensemble(((0.99, 0.01), (0.01, 0.99)))
    agreement = InformationDiagnostics.mutual_information_from_ensemble(((0.99, 0.01), (0.98, 0.02)))
    assert disagreement.value > agreement.value
    assert disagreement.normalized_risk > agreement.normalized_risk


def test_split_conformal_rank_is_finite_sample_conservative() -> None:
    calibration = tuple(ConformalExample(score / 100.0) for score in range(1, 101))
    threshold = ConformalControl.threshold(calibration, alpha=0.10)
    assert threshold.calibration_size == 100
    assert threshold.nominal_coverage == pytest.approx(0.90)
    assert threshold.threshold >= 0.90
    assert ConformalControl.accept(threshold.threshold, threshold)
    assert not ConformalControl.accept(threshold.threshold + 0.05, threshold)


def test_distribution_shift_flags_large_location_change() -> None:
    reference = tuple(float(index) / 100.0 for index in range(100))
    same = tuple(float(index) / 100.0 for index in range(100))
    shifted = tuple(10.0 + float(index) / 100.0 for index in range(100))
    same_signal = DistributionShift.population_stability_index(reference, same)
    shifted_signal = DistributionShift.population_stability_index(reference, shifted)
    assert not same_signal.shifted
    assert shifted_signal.shifted
    assert shifted_signal.score > same_signal.score


def test_cvar_is_more_tail_sensitive_than_mean() -> None:
    losses = (0.0, 0.0, 0.0, 1.0, 10.0)
    cvar = RiskDiagnostics.cvar(losses, alpha=0.8)
    assert cvar.value >= sum(losses) / len(losses)
    assert cvar.normalized_risk > 0.5


def test_minimax_regret_chooses_robust_action() -> None:
    # Action 0 wins model 0 but catastrophically loses model 1. Action 1 is
    # moderately good in both worlds and therefore has smaller worst regret.
    chosen, measurement = RiskDiagnostics.minimax_regret(((10.0, 7.0), (0.0, 6.0)))
    assert chosen == 1
    assert measurement.lens is AdvancedLens.MINIMAX_REGRET


def test_profiler_preserves_vector_and_abstains_on_semantic_risk() -> None:
    measurements = (
        LensMeasurement(
            AdvancedLens.SEMANTIC_ENTROPY,
            1.5,
            (UncertaintyAxis.SEMANTIC, UncertaintyAxis.EPISTEMIC),
            normalized_risk=0.9,
        ),
        LensMeasurement(
            AdvancedLens.CALIBRATION_ERROR,
            0.02,
            (UncertaintyAxis.CALIBRATION,),
            normalized_risk=0.02,
        ),
    )
    profile = UncertaintyProfiler.build(measurements)
    assert len(profile.measurements) == 2
    assert profile.axis_risk[UncertaintyAxis.SEMANTIC.value] >= 0.9
    decision = SelectivePrediction.decide(profile, utility_margin=0.5)
    assert decision.abstain
    assert UncertaintyAxis.SEMANTIC.value in decision.violated_axes


def test_profiler_does_not_let_low_risk_cancel_high_risk() -> None:
    profile = UncertaintyProfiler.build(
        (
            LensMeasurement(AdvancedLens.OOD_SCORE, 0.9, (UncertaintyAxis.DISTRIBUTION_SHIFT,), normalized_risk=0.9),
            LensMeasurement(AdvancedLens.DRIFT_SCORE, 0.01, (UncertaintyAxis.DISTRIBUTION_SHIFT,), normalized_risk=0.01),
        )
    )
    assert profile.axis_risk[UncertaintyAxis.DISTRIBUTION_SHIFT.value] > 0.9


def test_invalid_uncertainty_contract_forces_abstention() -> None:
    profile = UncertaintyProfiler.build(
        (
            LensMeasurement(
                AdvancedLens.CONFORMAL_COVERAGE,
                0.9,
                (UncertaintyAxis.COVERAGE,),
                normalized_risk=0.1,
                valid=False,
                assumptions=("exchangeability violated",),
            ),
        )
    )
    decision = SelectivePrediction.decide(profile, utility_margin=1.0)
    assert decision.abstain
    assert AdvancedLens.CONFORMAL_COVERAGE.value in profile.invalid_lenses


def test_lens_registry_is_broader_than_original_eighteen_and_axis_addressable() -> None:
    registry = LensRegistry()
    assert len(registry.all()) >= 30
    semantic = registry.by_axis(UncertaintyAxis.SEMANTIC)
    assert any(contract.lens is AdvancedLens.SEMANTIC_ENTROPY for contract in semantic)
    tail = registry.by_axis(UncertaintyAxis.TAIL)
    assert {contract.lens for contract in tail} >= {AdvancedLens.CVAR, AdvancedLens.TAIL_CALIBRATION}
