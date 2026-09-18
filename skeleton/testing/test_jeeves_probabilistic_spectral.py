import math

import pytest

from skeleton.jeeves.probabilistic_spectral import (
    SpectralConfig,
    discover_spectral_peaks,
    evaluate_spectral_complexities,
    fit_spectral_model,
    forecast_spectral,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _periodic_series(
    count: int,
    *,
    period: float = 12.0,
    amplitude: float = 2.0,
    slope: float = 0.04,
    offset: float = 10.0,
) -> tuple[float, ...]:
    return tuple(
        offset + slope * index + amplitude * math.sin(2.0 * math.pi * index / period)
        for index in range(count)
    )


def _multiscale_series(count: int) -> tuple[float, ...]:
    return tuple(
        20.0
        + 0.025 * index
        + 1.6 * math.sin(2.0 * math.pi * index / 12.0)
        + 0.55 * math.sin(2.0 * math.pi * index / 5.0 + 0.4)
        for index in range(count)
    )


def test_spectral_discovery_recovers_dominant_period() -> None:
    values = _periodic_series(120, period=12.0)
    peaks = discover_spectral_peaks(
        values,
        config=SpectralConfig(
            max_harmonics=3,
            min_period=4.0,
            max_period_fraction=0.75,
        ),
    )

    strongest = max(peaks, key=lambda peak: peak.normalized_power)
    assert strongest.period == pytest.approx(12.0)
    assert strongest.normalized_power > 0.45


def test_spectral_fit_forecasts_clean_periodic_signal() -> None:
    values = _periodic_series(120, period=12.0)
    fit = fit_spectral_model(
        values,
        config=SpectralConfig(
            max_harmonics=3,
            min_period=4.0,
            max_period_fraction=0.75,
        ),
    )
    forecast = fit.forecast(1)
    expected = 10.0 + 0.04 * 120 + 2.0 * math.sin(2.0 * math.pi * 120 / 12.0)

    assert forecast.mean == pytest.approx(expected, abs=1e-3)
    assert forecast.variance > 0.0
    assert fit.harmonic_count == 3
    assert any(component.period == pytest.approx(12.0) for component in fit.components)


def test_robust_iterations_resist_single_extreme_outlier() -> None:
    clean = list(_periodic_series(80, period=10.0, amplitude=1.8, slope=0.02, offset=5.0))
    contaminated = clean.copy()
    contaminated[30] += 25.0
    expected = 5.0 + 0.02 * 80 + 1.8 * math.sin(2.0 * math.pi * 80 / 10.0)

    ordinary = fit_spectral_model(
        contaminated,
        config=SpectralConfig(
            max_harmonics=2,
            min_period=4.0,
            max_period_fraction=0.75,
            robust_iterations=1,
        ),
    )
    robust = fit_spectral_model(
        contaminated,
        config=SpectralConfig(
            max_harmonics=2,
            min_period=4.0,
            max_period_fraction=0.75,
            robust_iterations=5,
            huber_delta=1.5,
        ),
    )

    ordinary_error = abs(ordinary.forecast(1).mean - expected)
    robust_error = abs(robust.forecast(1).mean - expected)
    assert robust_error < ordinary_error * 0.05
    assert robust.effective_sample_size < len(contaminated)


def test_forecast_parameter_uncertainty_is_positive_and_horizon_sensitive() -> None:
    values = _periodic_series(72, period=9.0)
    fit = fit_spectral_model(
        values,
        config=SpectralConfig(
            max_harmonics=2,
            min_period=3.0,
            max_period_fraction=0.75,
        ),
    )

    one = forecast_spectral(fit, horizon=1)
    twelve = forecast_spectral(fit, horizon=12)

    assert math.isfinite(one.mean)
    assert math.isfinite(twelve.mean)
    assert one.variance > 0.0
    assert twelve.variance > 0.0
    lower, upper = twelve.interval()
    assert lower < twelve.mean < upper


def test_fit_is_deterministic_and_fingerprint_binds_observations() -> None:
    values = _multiscale_series(90)
    config = SpectralConfig(
        max_harmonics=3,
        min_period=3.0,
        max_period_fraction=0.75,
    )

    left = fit_spectral_model(values, config=config)
    right = fit_spectral_model(values, config=config)
    changed = fit_spectral_model(values[:-1] + (values[-1] + 0.01,), config=config)

    assert left == right
    assert left.fingerprint == right.fingerprint
    assert left.fingerprint != changed.fingerprint


def test_frequency_discovery_is_prefix_causal() -> None:
    prefix = _multiscale_series(72)
    suffix_a = tuple(1000.0 + index for index in range(20))
    suffix_b = tuple(-1000.0 - index for index in range(20))
    config = SpectralConfig(
        max_harmonics=3,
        min_period=3.0,
        max_period_fraction=0.75,
    )

    model_a = fit_spectral_model((prefix + suffix_a)[: len(prefix)], config=config)
    model_b = fit_spectral_model((prefix + suffix_b)[: len(prefix)], config=config)

    assert model_a == model_b
    assert model_a.forecast(1) == model_b.forecast(1)


def test_tournament_prefers_harmonics_on_multiscale_signal() -> None:
    values = _multiscale_series(90)
    report = evaluate_spectral_complexities(
        values,
        min_train_size=48,
        step=3,
        max_harmonics=4,
        base_config=SpectralConfig(
            max_harmonics=4,
            min_period=3.0,
            max_period_fraction=0.75,
            robust_iterations=3,
        ),
    )

    assert report.selected_harmonics > 0
    assert report.by_harmonics(report.selected_harmonics).mean_log_score > report.by_harmonics(0).mean_log_score
    assert sorted(report.ranking) == [0, 1, 2, 3, 4]
    assert all(score.folds == 14 for score in report.scores)


def test_tournament_is_deterministic() -> None:
    values = _multiscale_series(78)
    config = SpectralConfig(
        max_harmonics=3,
        min_period=3.0,
        max_period_fraction=0.75,
        robust_iterations=2,
    )

    first = evaluate_spectral_complexities(
        values,
        min_train_size=42,
        step=4,
        max_harmonics=3,
        base_config=config,
    )
    second = evaluate_spectral_complexities(
        values,
        min_train_size=42,
        step=4,
        max_harmonics=3,
        base_config=config,
    )

    assert first == second
    assert first.fingerprint == second.fingerprint


def test_zero_harmonics_reduces_to_robust_trend_model() -> None:
    values = tuple(3.0 + 0.25 * index for index in range(40))
    fit = fit_spectral_model(
        values,
        config=SpectralConfig(max_harmonics=0, robust_iterations=3),
    )

    assert fit.peaks == ()
    assert fit.components == ()
    assert fit.trend == pytest.approx(0.25, abs=1e-6)
    assert fit.forecast(1).mean == pytest.approx(3.0 + 0.25 * 40, abs=1e-5)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_harmonics": -1},
        {"max_harmonics": 17},
        {"min_period": 1.5},
        {"max_period_fraction": 0.01},
        {"frequency_separation_bins": -1},
        {"ridge_penalty": -1.0},
        {"robust_iterations": 0},
        {"robust_iterations": 21},
        {"huber_delta": 0.0},
        {"min_variance": 0.0},
        {"include_trend": 1},
    ],
)
def test_invalid_spectral_configuration_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        SpectralConfig(**kwargs)


def test_short_or_nonfinite_series_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        fit_spectral_model([1.0] * 7)

    with pytest.raises(StateSpaceError):
        fit_spectral_model([1.0] * 7 + [float("nan")])


def test_duplicate_or_empty_forecast_path_fails_closed() -> None:
    fit = fit_spectral_model(_periodic_series(48))

    with pytest.raises(StateSpaceError):
        fit.forecast_path([])

    with pytest.raises(StateSpaceError):
        fit.forecast_path([1, 1])


def test_invalid_tournament_geometry_fails_closed() -> None:
    values = _multiscale_series(40)

    with pytest.raises(StateSpaceError):
        evaluate_spectral_complexities(values, min_train_size=7)

    with pytest.raises(StateSpaceError):
        evaluate_spectral_complexities(values, min_train_size=20, step=0)

    with pytest.raises(StateSpaceError):
        evaluate_spectral_complexities(values[:20], min_train_size=20)
