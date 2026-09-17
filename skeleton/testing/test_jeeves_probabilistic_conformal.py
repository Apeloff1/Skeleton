from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from skeleton.jeeves.probabilistic_conformal import (
    ConformalConfig,
    ForecastObservation,
    conformal_interval,
    conformal_quantile,
    conformalize_next_forecast,
    evaluate_cross_family_conformal,
    evaluate_prequential_conformal,
    nonconformity_score,
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
) -> tuple[ForecastObservation, ...]:
    return tuple(
        ForecastObservation(
            target_index=start + index,
            actual=value,
            predictive=_Forecast(mean=0.0, variance=variance),
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


def test_repeated_misses_reduce_effective_alpha() -> None:
    observations = _observations((0.1, 0.2, 0.3, 0.4, 10.0, 11.0, 12.0, 13.0))
    config = _config(adaptive_rate=0.10)

    report = evaluate_prequential_conformal(observations, config=config)

    assert report.steps[0].missed
    assert report.final_effective_alpha < config.alpha
    assert report.final_effective_alpha >= config.min_alpha


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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"min_calibration": 3},
        {"calibration_window": 3},
        {"adaptive_rate": -0.1},
        {"adaptive_rate": 1.1},
        {"min_alpha": 0.25},
        {"max_alpha": 0.15},
        {"min_scale": 0.0},
        {"normalized": 1},
    ],
)
def test_invalid_configuration_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        _config(**kwargs)
