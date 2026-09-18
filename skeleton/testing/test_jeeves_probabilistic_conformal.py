from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from skeleton.jeeves.probabilistic_conformal import (
    ConformalConfig,
    ConformalInterval,
    ForecastObservation,
    attainable_alpha_floor,
    conformal_interval,
    conformal_quantile,
    conformalize_next_forecast,
    evaluate_cross_family_conformal,
    evaluate_prequential_conformal,
    nonconformity_score,
    required_calibration_size,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    mean: float
    variance: float = 1.0
    horizon: int = 1


def _observations(
    values: tuple[float, ...],
    *,
    variance: float = 1.0,
    start: int = 1,
    horizon: int = 1,
) -> tuple[ForecastObservation, ...]:
    return tuple(
        ForecastObservation(
            target_index=start + index,
            actual=value,
            predictive=_Forecast(mean=0.0, variance=variance, horizon=horizon),
        )
        for index, value in enumerate(values)
    )


def _config(**kwargs: object) -> ConformalConfig:
    values: dict[str, object] = {
        "alpha": 0.20,
        "min_calibration": 4,
        "calibration_window": 8,
        "adaptive_rate": 0.05,
        "min_alpha": 0.05,
        "max_alpha": 0.45,
    }
    values.update(kwargs)
    return ConformalConfig(**values)


def test_conformal_quantile_uses_conservative_finite_sample_rank() -> None:
    scores = (0.1, 0.2, 0.3, 0.4, 0.5)

    assert conformal_quantile(scores, 0.20) == pytest.approx(0.5)
    assert conformal_quantile(scores, 0.50) == pytest.approx(0.3)


def test_unattainable_quantile_fails_instead_of_clipping_rank() -> None:
    scores = (0.1, 0.2, 0.3, 0.4)

    assert attainable_alpha_floor(4) == pytest.approx(0.20)
    with pytest.raises(StateSpaceError) as exc_info:
        conformal_quantile(scores, 0.10)

    assert exc_info.value.context["reason"] == "unattainable_conformal_alpha"
    assert exc_info.value.context["required_calibration_size"] == 9


def test_exact_attainable_alpha_floor_is_valid() -> None:
    scores = (0.1, 0.2, 0.3, 0.4)

    assert conformal_quantile(scores, 0.20) == pytest.approx(0.4)


def test_required_calibration_size_matches_finite_resolution() -> None:
    for alpha, expected in ((0.5, 1), (0.2, 4), (0.1, 9), (0.05, 19)):
        size = required_calibration_size(alpha)
        assert size == expected
        assert attainable_alpha_floor(size) <= alpha + 1e-15
        if size > 1:
            assert attainable_alpha_floor(size - 1) > alpha - 1e-15


def test_empty_generator_quantile_fails_cleanly() -> None:
    with pytest.raises(StateSpaceError) as exc_info:
        conformal_quantile((value for value in ()), 0.20)

    assert exc_info.value.context["reason"] == "empty_conformal_calibration"


def test_interval_uses_only_completed_calibration_scores() -> None:
    config = _config(adaptive_rate=0.0)
    interval = conformal_interval(
        _Forecast(mean=10.0, variance=4.0),
        (0.5, 1.0, 1.5, 2.0),
        config=config,
        target_index=10,
    )

    assert interval.quantile == pytest.approx(2.0)
    assert interval.scale == pytest.approx(2.0)
    assert interval.radius == pytest.approx(4.0)
    assert interval.lower == pytest.approx(6.0)
    assert interval.upper == pytest.approx(14.0)
    assert interval.calibration_size == 4


def test_interval_raises_alpha_to_finite_sample_floor() -> None:
    config = _config(
        alpha=0.10,
        min_alpha=0.01,
        adaptive_rate=0.0,
    )
    interval = conformal_interval(
        _Forecast(mean=0.0),
        (0.1, 0.2, 0.3, 0.4),
        config=config,
        target_index=10,
    )

    assert interval.effective_alpha == pytest.approx(0.20)
    assert interval.quantile == pytest.approx(0.4)


def test_interval_generator_scores_are_supported_and_validated() -> None:
    interval = conformal_interval(
        _Forecast(mean=0.0),
        (value for value in (0.1, 0.2, 0.3, 0.4)),
        config=_config(adaptive_rate=0.0),
        target_index=10,
    )

    assert interval.calibration_size == 4


def test_prequential_warmup_never_scores_the_target_into_its_own_interval() -> None:
    observations = _observations((0.1, 0.2, 0.3, 0.4, 10.0, 0.5))
    report = evaluate_prequential_conformal(
        observations,
        config=_config(adaptive_rate=0.0),
    )

    first = report.steps[0]
    assert first.interval.target_index == 5
    assert first.interval.calibration_size == 4
    assert first.interval.quantile == pytest.approx(0.4)
    assert first.missed
    assert first.nonconformity_score == pytest.approx(10.0)

    second = report.steps[1]
    assert second.interval.target_index == 6
    assert second.interval.quantile == pytest.approx(10.0)


def test_future_suffix_mutation_cannot_change_completed_conformal_steps() -> None:
    prefix = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
    left = prefix + (10.0, 11.0, 12.0)
    right = prefix + (-10.0, -11.0, -12.0)
    config = _config()

    left_report = evaluate_prequential_conformal(_observations(left), config=config)
    right_report = evaluate_prequential_conformal(_observations(right), config=config)

    left_completed = tuple(
        step for step in left_report.steps if step.interval.target_index <= len(prefix)
    )
    right_completed = tuple(
        step for step in right_report.steps if step.interval.target_index <= len(prefix)
    )
    assert left_completed == right_completed


def test_repeated_misses_reduce_alpha_but_never_below_window_resolution() -> None:
    observations = _observations(
        (0.1, 0.2, 0.3, 0.4, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0)
    )
    config = _config(
        adaptive_rate=0.50,
        min_alpha=0.01,
        calibration_window=4,
    )

    report = evaluate_prequential_conformal(observations, config=config)

    assert report.steps[0].missed
    assert report.final_effective_alpha >= attainable_alpha_floor(4)
    assert all(
        step.interval.effective_alpha
        >= attainable_alpha_floor(step.interval.calibration_size) - 1e-15
        for step in report.steps
    )


def test_hits_raise_alpha_but_respect_upper_bound() -> None:
    observations = _observations((1.0,) * 20)
    config = _config(
        alpha=0.20,
        adaptive_rate=0.20,
        max_alpha=0.30,
    )

    report = evaluate_prequential_conformal(observations, config=config)

    assert not any(step.missed for step in report.steps)
    assert report.final_effective_alpha == pytest.approx(config.max_alpha)


def test_normalized_nonconformity_respects_predictive_scale() -> None:
    actual = 4.0

    narrow = nonconformity_score(actual, _Forecast(mean=0.0, variance=1.0))
    wide = nonconformity_score(actual, _Forecast(mean=0.0, variance=16.0))
    raw = nonconformity_score(
        actual,
        _Forecast(mean=0.0, variance=16.0),
        normalized=False,
    )

    assert narrow == pytest.approx(4.0)
    assert wide == pytest.approx(1.0)
    assert raw == pytest.approx(4.0)


def test_finite_operands_that_overflow_residual_fail_closed() -> None:
    with pytest.raises(StateSpaceError) as exc_info:
        nonconformity_score(
            1e308,
            _Forecast(mean=-1e308, variance=1.0),
        )

    assert exc_info.value.context["reason"] == "conformal_numerical_instability"


def test_interval_radius_overflow_fails_closed() -> None:
    config = _config(
        alpha=0.50,
        min_alpha=0.10,
        max_alpha=0.90,
        adaptive_rate=0.0,
    )

    with pytest.raises(StateSpaceError) as exc_info:
        conformal_interval(
            _Forecast(mean=0.0, variance=4.0),
            (1e308, 1e308, 1e308, 1e308),
            config=config,
            target_index=10,
        )

    assert exc_info.value.context["reason"] == "conformal_numerical_instability"


def test_interval_width_overflow_fails_closed() -> None:
    interval = ConformalInterval(
        target_index=1,
        horizon=1,
        center=0.0,
        lower=-1e308,
        upper=1e308,
        radius=1e308,
        quantile=1e308,
        effective_alpha=0.50,
        calibration_size=4,
        scale=1.0,
    )

    with pytest.raises(StateSpaceError):
        _ = interval.width


def test_report_metrics_and_fingerprint_are_deterministic() -> None:
    observations = _observations((0.2, 0.4, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3))
    config = _config()

    first = evaluate_prequential_conformal(observations, config=config)
    second = evaluate_prequential_conformal(observations, config=config)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert 0.0 <= first.empirical_coverage <= 1.0
    assert first.mean_width >= 0.0
    assert first.median_width >= 0.0
    assert first.mean_interval_score >= first.mean_width
    assert first.coverage_gap == pytest.approx(
        first.empirical_coverage - (1.0 - config.alpha)
    )


def test_next_forecast_reuses_only_final_completed_calibration_state() -> None:
    observations = _observations((0.2, 0.3, 0.4, 0.5, 0.8, 0.7, 0.9, 1.0))
    report = evaluate_prequential_conformal(observations, config=_config())

    interval = conformalize_next_forecast(
        _Forecast(mean=3.0, variance=4.0, horizon=2),
        report,
        target_index=20,
    )

    assert interval.target_index == 20
    assert interval.horizon == 2
    assert interval.calibration_size == len(report.final_calibration_scores)
    assert interval.effective_alpha == pytest.approx(report.final_effective_alpha)
    assert interval.lower < interval.center < interval.upper


def test_next_forecast_rejects_tampered_report_state() -> None:
    observations = _observations((0.2, 0.3, 0.4, 0.5, 0.8, 0.7, 0.9, 1.0))
    report = evaluate_prequential_conformal(observations, config=_config())
    tampered = replace(
        report,
        final_calibration_scores=report.final_calibration_scores[:-1] + (99.0,),
    )

    with pytest.raises(StateSpaceError):
        conformalize_next_forecast(
            _Forecast(mean=3.0, variance=4.0),
            tampered,
            target_index=20,
        )


def test_next_forecast_rejects_tampered_aggregate_metrics() -> None:
    observations = _observations((0.2, 0.3, 0.4, 0.5, 0.8, 0.7, 0.9, 1.0))
    report = evaluate_prequential_conformal(observations, config=_config())

    for field in (
        "empirical_coverage",
        "mean_width",
        "median_width",
        "mean_interval_score",
        "mean_nonconformity",
    ):
        tampered = replace(report, **{field: getattr(report, field) + 0.01})
        with pytest.raises(StateSpaceError):
            conformalize_next_forecast(
                _Forecast(mean=3.0, variance=4.0),
                tampered,
                target_index=20,
            )


def test_cross_family_adapter_consumes_only_step_contract() -> None:
    steps = tuple(
        SimpleNamespace(
            target_index=index,
            actual=value,
            predictive=_Forecast(mean=0.0, variance=1.0),
        )
        for index, value in enumerate(
            (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7),
            start=10,
        )
    )
    report = SimpleNamespace(steps=steps)

    conformal = evaluate_cross_family_conformal(report, config=_config())

    assert conformal.warmup_count == 4
    assert len(conformal.steps) == 3
    assert conformal.steps[0].interval.target_index == 14


def test_cross_family_adapter_rejects_empty_noniterable_and_missing_steps() -> None:
    for report in (
        object(),
        SimpleNamespace(steps=()),
        SimpleNamespace(steps=1),
        SimpleNamespace(steps=(SimpleNamespace(target_index=1),)),
    ):
        with pytest.raises(StateSpaceError):
            evaluate_cross_family_conformal(report, config=_config())


def test_cross_family_adapter_does_not_coerce_bad_target_indices() -> None:
    for bad_index in (True, 1.0, "1"):
        report = SimpleNamespace(
            steps=(
                SimpleNamespace(
                    target_index=bad_index,
                    actual=0.1,
                    predictive=_Forecast(mean=0.0),
                ),
            )
        )
        with pytest.raises(StateSpaceError):
            evaluate_cross_family_conformal(report, config=_config())


def test_non_monotonic_targets_fail_closed() -> None:
    observations = (
        ForecastObservation(1, 0.1, _Forecast(0.0)),
        ForecastObservation(2, 0.2, _Forecast(0.0)),
        ForecastObservation(3, 0.3, _Forecast(0.0)),
        ForecastObservation(4, 0.4, _Forecast(0.0)),
        ForecastObservation(4, 0.5, _Forecast(0.0)),
        ForecastObservation(6, 0.6, _Forecast(0.0)),
    )

    with pytest.raises(StateSpaceError):
        evaluate_prequential_conformal(observations, config=_config())


def test_mixed_forecast_horizons_fail_closed() -> None:
    observations = list(_observations((0.1, 0.2, 0.3, 0.4, 0.5, 0.6)))
    observations[-1] = ForecastObservation(
        target_index=6,
        actual=0.6,
        predictive=_Forecast(mean=0.0, horizon=2),
    )

    with pytest.raises(StateSpaceError) as exc_info:
        evaluate_prequential_conformal(observations, config=_config())

    assert exc_info.value.context["reason"] == "conformal_horizon_mismatch"


def test_short_history_and_bad_predictive_variance_fail_closed() -> None:
    with pytest.raises(StateSpaceError):
        evaluate_prequential_conformal(
            _observations((0.1, 0.2, 0.3, 0.4)),
            config=_config(),
        )

    with pytest.raises(StateSpaceError):
        ForecastObservation(
            target_index=1,
            actual=0.0,
            predictive=_Forecast(mean=0.0, variance=0.0),
        )


def test_missing_predictive_attributes_fail_as_state_space_error() -> None:
    with pytest.raises(StateSpaceError):
        ForecastObservation(
            target_index=1,
            actual=0.0,
            predictive=object(),
        )


def test_bad_scores_fail_closed() -> None:
    for scores in (
        (0.1, float("nan"), 0.3, 0.4),
        (0.1, float("inf"), 0.3, 0.4),
        (0.1, -0.2, 0.3, 0.4),
        (0.1, True, 0.3, 0.4),
    ):
        with pytest.raises(StateSpaceError):
            conformal_quantile(scores, 0.20)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"alpha": True},
        {"min_calibration": 3},
        {"min_calibration": True},
        {"calibration_window": 3},
        {"calibration_window": True},
        {"adaptive_rate": -0.1},
        {"adaptive_rate": 1.1},
        {"min_alpha": 0.25},
        {"max_alpha": 0.15},
        {"min_scale": 0.0},
        {"min_scale": float("inf")},
        {"normalized": 1},
    ],
)
def test_invalid_configuration_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        _config(**kwargs)
