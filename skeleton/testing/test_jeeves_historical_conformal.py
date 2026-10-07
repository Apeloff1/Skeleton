from __future__ import annotations

import pytest

from skeleton.jeeves.historical_autoregression import (
    AdvancedHistoricalForecastTournament,
    AutoRegressiveParameters,
    AutoRegressiveSelectionPolicy,
)
from skeleton.jeeves.historical_conformal import (
    ConformalPolicy,
    HistoricalConformalCalibrator,
    HistoricalConformalError,
    summarize_conformal_band,
    summarize_coverage_audit,
)
from skeleton.jeeves.historical_forecasting import (
    ForecastMethod,
    ForecastObservation,
    ForecastParameters,
    ForecastSelectionPolicy,
    HistoricalForecastTournament,
    HistoricalSeries,
)


def _series(values: list[float] | tuple[float, ...], *, series_id: str = "conformal-fixture") -> HistoricalSeries:
    return HistoricalSeries(
        series_id=series_id,
        observations=tuple(
            ForecastObservation(timestamp=float(index), value=float(value))
            for index, value in enumerate(values, start=1)
        ),
    )


def _forecast_policy() -> ForecastSelectionPolicy:
    return ForecastSelectionPolicy(
        horizons=(1, 2),
        minimum_training_points=5,
        minimum_origins=3,
        alpha_grid=(0.4, 0.8),
        beta_grid=(0.2, 0.5),
        damping_grid=(0.9, 0.98),
    )


def test_policy_requires_open_interval_coverage() -> None:
    with pytest.raises(HistoricalConformalError) as exc:
        ConformalPolicy(coverage=1.0)
    assert exc.value.context["reason"] == "invalid_coverage"


def test_policy_rejects_zero_minimum_residuals() -> None:
    with pytest.raises(HistoricalConformalError) as exc:
        ConformalPolicy(minimum_residuals=0)
    assert exc.value.context["reason"] == "invalid_minimum_residuals"


def test_policy_rejects_negative_minimum_radius() -> None:
    with pytest.raises(HistoricalConformalError) as exc:
        ConformalPolicy(minimum_radius=-0.1)
    assert exc.value.context["reason"] == "invalid_minimum_radius"


def test_finite_sample_quantile_uses_conformal_rank() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.8,
            minimum_residuals=5,
            horizon_growth_exponent=0.0,
        )
    )
    band = calibrator.fit(
        residuals=(1.0, -2.0, 3.0, -4.0, 5.0),
        source_fingerprint="source",
    )
    # ceil((5 + 1) * .8) = 5, therefore the maximum absolute residual.
    assert band.quantile_rank == 5
    assert band.base_radius == pytest.approx(5.0)


def test_quantile_rank_is_clamped_to_available_residuals() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.99, minimum_residuals=3)
    )
    band = calibrator.fit((1.0, 2.0, 3.0), source_fingerprint="source")
    assert band.quantile_rank == 3
    assert band.base_radius == pytest.approx(3.0)


def test_minimum_radius_sets_floor() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.5,
            minimum_residuals=4,
            minimum_radius=10.0,
        )
    )
    band = calibrator.fit((0.1, -0.2, 0.3, -0.4), source_fingerprint="source")
    assert band.base_radius == pytest.approx(10.0)


def test_fit_rejects_insufficient_residuals() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(minimum_residuals=5)
    )
    with pytest.raises(HistoricalConformalError) as exc:
        calibrator.fit((1.0, 2.0), source_fingerprint="source")
    assert exc.value.context["reason"] == "insufficient_residuals"


def test_fit_requires_source_fingerprint() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(minimum_residuals=2)
    )
    with pytest.raises(HistoricalConformalError) as exc:
        calibrator.fit((1.0, 2.0), source_fingerprint="")
    assert exc.value.context["reason"] == "missing_source_fingerprint"


def test_band_applies_symmetric_interval() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.5,
            minimum_residuals=4,
            horizon_growth_exponent=0.0,
        )
    ).fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="source")
    points = band.apply((10.0, 20.0))
    assert points[0].predicted == pytest.approx(10.0)
    assert points[0].lower == pytest.approx(10.0 - band.base_radius)
    assert points[0].upper == pytest.approx(10.0 + band.base_radius)
    assert points[1].radius == pytest.approx(band.base_radius)


def test_horizon_growth_expands_band() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.5,
            minimum_residuals=4,
            horizon_growth_exponent=0.5,
        )
    ).fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="source")
    points = band.apply((10.0, 10.0, 10.0, 10.0))
    assert points[1].radius > points[0].radius
    assert points[3].radius == pytest.approx(points[0].radius * 2.0)


def test_zero_growth_keeps_constant_radius() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.5,
            minimum_residuals=4,
            horizon_growth_exponent=0.0,
        )
    ).fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="source")
    assert [point.radius for point in band.apply((1.0, 2.0, 3.0))] == pytest.approx(
        [band.base_radius] * 3
    )


def test_coverage_audit_reports_exact_coverage() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.75,
            minimum_residuals=4,
            horizon_growth_exponent=0.0,
        )
    ).fit((1.0, -1.0, 1.0, -1.0), source_fingerprint="source")
    audit = HistoricalConformalCalibrator.audit(
        band,
        predictions=(0.0, 0.0, 0.0, 0.0),
        actuals=(0.0, 0.5, 2.0, -2.0),
    )
    assert audit.sample_count == 4
    assert audit.covered_count == 2
    assert audit.realized_coverage == pytest.approx(0.5)
    assert audit.coverage_gap == pytest.approx(-0.25)
    assert audit.under_target is True
    assert audit.mean_absolute_miss > 0.0


def test_coverage_audit_detects_target_met() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(
            coverage=0.5,
            minimum_residuals=4,
            horizon_growth_exponent=0.0,
        )
    ).fit((2.0, -2.0, 2.0, -2.0), source_fingerprint="source")
    audit = HistoricalConformalCalibrator.audit(
        band,
        predictions=(0.0, 0.0, 0.0, 0.0),
        actuals=(0.0, 1.0, -1.0, 2.0),
    )
    assert audit.realized_coverage == pytest.approx(1.0)
    assert audit.under_target is False
    assert audit.mean_absolute_miss == pytest.approx(0.0)


def test_coverage_audit_rejects_length_mismatch() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(minimum_residuals=2)
    ).fit((1.0, -1.0), source_fingerprint="source")
    with pytest.raises(HistoricalConformalError) as exc:
        HistoricalConformalCalibrator.audit(
            band,
            predictions=(1.0, 2.0),
            actuals=(1.0,),
        )
    assert exc.value.context["reason"] == "audit_length_mismatch"


def test_calibration_from_baseline_tournament_uses_rolling_residuals() -> None:
    series = _series([1.0, 2.0, 2.5, 4.0, 4.2, 5.5, 6.0, 7.2, 7.5, 9.0, 9.2, 10.5, 11.0])
    report = HistoricalForecastTournament(_forecast_policy()).run(series)
    band = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.8, minimum_residuals=6)
    ).from_tournament(report)
    assert band.residual_count == len(report.champion.residuals)
    assert band.source_fingerprint == report.champion.evaluation_fingerprint


def test_calibration_from_specific_forecast_evaluation() -> None:
    series = _series([float(index) for index in range(14)])
    evaluation = HistoricalForecastTournament(_forecast_policy()).evaluate(
        series,
        ForecastMethod.DRIFT,
        ForecastParameters(),
    )
    band = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.8, minimum_residuals=6)
    ).from_forecast_evaluation(evaluation)
    assert band.source_fingerprint == evaluation.evaluation_fingerprint
    assert band.base_radius == pytest.approx(0.0)


def test_calibration_from_autoregression_evaluation() -> None:
    values = [1.0, 0.0]
    while len(values) < 30:
        values.append(-values[-2])
    series = _series(values)
    advanced = AdvancedHistoricalForecastTournament(
        forecast_policy=ForecastSelectionPolicy(
            horizons=(1, 2),
            minimum_training_points=8,
            minimum_origins=3,
            alpha_grid=(0.4,),
            beta_grid=(0.2,),
            damping_grid=(0.9,),
        ),
        autoregression_policy=AutoRegressiveSelectionPolicy(
            orders=(2,),
            ridge_grid=(1e-8,),
            include_intercept=False,
        ),
    )
    evaluation = advanced.evaluate(
        series,
        AutoRegressiveParameters(order=2, ridge=1e-8, include_intercept=False),
    )
    band = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.8, minimum_residuals=6)
    ).from_autoregression(evaluation)
    assert band.source_fingerprint == evaluation.evaluation_fingerprint
    assert band.residual_count == len(evaluation.residuals)


def test_band_fingerprint_is_deterministic() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.8, minimum_residuals=4)
    )
    left = calibrator.fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="source")
    right = calibrator.fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="source")
    assert left.band_fingerprint == right.band_fingerprint


def test_band_fingerprint_changes_with_source() -> None:
    calibrator = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.8, minimum_residuals=4)
    )
    left = calibrator.fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="left")
    right = calibrator.fit((1.0, -2.0, 3.0, -4.0), source_fingerprint="right")
    assert left.band_fingerprint != right.band_fingerprint


def test_summaries_expose_fingerprints_and_coverage_state() -> None:
    band = HistoricalConformalCalibrator(
        ConformalPolicy(coverage=0.5, minimum_residuals=4, horizon_growth_exponent=0.0)
    ).fit((1.0, -1.0, 1.0, -1.0), source_fingerprint="source")
    audit = HistoricalConformalCalibrator.audit(
        band,
        predictions=(0.0, 0.0),
        actuals=(0.0, 2.0),
    )
    band_summary = summarize_conformal_band(band)
    audit_summary = summarize_coverage_audit(audit)
    assert band_summary["band_fingerprint"] == band.band_fingerprint
    assert band_summary["policy_fingerprint"] == band.policy_fingerprint
    assert audit_summary["audit_fingerprint"] == audit.audit_fingerprint
    assert audit_summary["under_target"] == audit.under_target