from __future__ import annotations

import math

import pytest

from skeleton.jeeves.probabilistic_ensemble import (
    BayesianEnsembleConfig,
    MixtureForecast,
    OnlineBayesianEnsemble,
    WeightedForecast,
    gaussian_mixture_crps,
    probability_integral_transform,
)
from skeleton.jeeves.probabilistic_state_space import (
    GaussianForecast,
    InnovationRegime,
    StateSpaceConfig,
    StateSpaceError,
    StateSpaceFamily,
    evaluate_state_space_families,
    fit_state_space,
)


def _trend(count: int = 80, slope: float = 0.75) -> tuple[float, ...]:
    return tuple(10.0 + slope * index for index in range(count))


def _oscillating(count: int = 80) -> tuple[float, ...]:
    return tuple(100.0 + 4.0 * math.sin(index / 2.0) for index in range(count))


def _shock_series() -> tuple[float, ...]:
    values = [100.0 + 0.2 * index for index in range(50)]
    values.extend([111.0, 160.0, 112.0, 113.0, 114.0])
    return tuple(values)


def test_fit_is_deterministic_and_fingerprinted() -> None:
    values = _trend()
    left = fit_state_space(values)
    right = fit_state_space(values)

    assert left.fingerprint == right.fingerprint
    assert left.posterior_level == pytest.approx(right.posterior_level)
    assert left.posterior_trend == pytest.approx(right.posterior_trend)
    assert left.regime.as_mapping() == pytest.approx(right.regime.as_mapping())


def test_accepts_structural_values_container_without_hard_dependency() -> None:
    class Container:
        values = _trend(30)

    fit = fit_state_space(Container())
    assert fit.sample_count == 30
    assert fit.observations == Container.values


def test_rejects_empty_nonfinite_and_boolean_series() -> None:
    with pytest.raises(StateSpaceError):
        fit_state_space(())
    with pytest.raises(StateSpaceError):
        fit_state_space((1.0, float("nan")))
    with pytest.raises(StateSpaceError):
        fit_state_space((1.0, True))


def test_config_rejects_invalid_variances_and_clip() -> None:
    with pytest.raises(StateSpaceError):
        StateSpaceConfig(observation_variance=0.0)
    with pytest.raises(StateSpaceError):
        StateSpaceConfig(level_variance=-1.0)
    with pytest.raises(StateSpaceError):
        StateSpaceConfig(robust_clip_sigma=0.5)
    with pytest.raises(StateSpaceError):
        StateSpaceConfig(regime_window=2)


def test_local_level_forecast_mean_is_horizon_invariant() -> None:
    fit = fit_state_space(
        _oscillating(),
        config=StateSpaceConfig(family=StateSpaceFamily.LOCAL_LEVEL),
    )
    one = fit.forecast(1)
    ten = fit.forecast(10)
    assert ten.mean == pytest.approx(one.mean)
    assert ten.variance >= one.variance


def test_local_trend_projects_mean_and_uncertainty_forward() -> None:
    fit = fit_state_space(
        _trend(),
        config=StateSpaceConfig(family=StateSpaceFamily.LOCAL_LINEAR_TREND),
    )
    one = fit.forecast(1)
    five = fit.forecast(5)
    assert five.mean > one.mean
    assert five.variance > one.variance
    assert five.standard_deviation > one.standard_deviation


def test_forecast_path_rejects_duplicate_horizons() -> None:
    fit = fit_state_space(_trend())
    with pytest.raises(StateSpaceError):
        fit.forecast_path((1, 1, 3))


def test_robust_family_clips_large_standardized_innovation() -> None:
    fit = fit_state_space(
        _shock_series(),
        config=StateSpaceConfig(
            family=StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND,
            robust_clip_sigma=2.0,
        ),
    )
    clipped = [
        step
        for step in fit.steps
        if abs(step.standardized_innovation) > fit.config.robust_clip_sigma
    ]
    assert clipped
    assert all(abs(step.effective_innovation) < abs(step.innovation) for step in clipped)


def test_nonrobust_family_uses_full_innovation() -> None:
    fit = fit_state_space(
        _shock_series(),
        config=StateSpaceConfig(family=StateSpaceFamily.LOCAL_LINEAR_TREND),
    )
    assert all(step.effective_innovation == pytest.approx(step.innovation) for step in fit.steps)


def test_regime_probabilities_are_normalized() -> None:
    for values in (_trend(), _oscillating(), _shock_series()):
        fit = fit_state_space(values)
        probabilities = fit.regime.as_mapping()
        assert sum(probabilities.values()) == pytest.approx(1.0)
        assert all(0.0 <= value <= 1.0 for value in probabilities.values())
        assert fit.regime.dominant in set(InnovationRegime)


def test_shock_history_increases_shock_posterior_over_smooth_trend() -> None:
    smooth = fit_state_space(_trend())
    shocked = fit_state_space(_shock_series())
    assert shocked.regime.shock > smooth.regime.shock


def test_gaussian_forecast_interval_contains_mean_and_is_symmetric() -> None:
    forecast = GaussianForecast(horizon=3, mean=12.5, variance=4.0)
    lower, upper = forecast.interval()
    assert lower < forecast.mean < upper
    assert forecast.mean - lower == pytest.approx(upper - forecast.mean)


def test_log_density_prefers_realizations_near_mean() -> None:
    forecast = GaussianForecast(horizon=1, mean=0.0, variance=1.0)
    assert forecast.log_density(0.0) > forecast.log_density(4.0)


def test_state_space_tournament_is_deterministic() -> None:
    values = _trend(55)
    left = evaluate_state_space_families(values, min_train_size=18, step=3)
    right = evaluate_state_space_families(values, min_train_size=18, step=3)
    assert left.fingerprint == right.fingerprint
    assert left.ranking == right.ranking
    assert left.selected in set(StateSpaceFamily)
    assert all(score.folds > 0 for score in left.scores)


def test_tournament_scores_have_finite_probabilistic_metrics() -> None:
    report = evaluate_state_space_families(_oscillating(60), min_train_size=18, step=4)
    for score in report.scores:
        assert math.isfinite(score.mean_log_score)
        assert math.isfinite(score.rmse)
        assert math.isfinite(score.mae)
        assert 0.0 <= score.coverage_95 <= 1.0
        assert score.average_interval_width_95 > 0.0


def test_tournament_rejects_bad_configuration() -> None:
    with pytest.raises(StateSpaceError):
        evaluate_state_space_families(_trend(20), min_train_size=2)
    with pytest.raises(StateSpaceError):
        evaluate_state_space_families(_trend(20), step=0)
    with pytest.raises(StateSpaceError):
        evaluate_state_space_families(_trend(20), min_train_size=20)


def test_single_component_mixture_matches_component_mean_variance() -> None:
    component = WeightedForecast(
        family=StateSpaceFamily.LOCAL_LEVEL,
        weight=1.0,
        forecast=GaussianForecast(horizon=1, mean=2.0, variance=9.0),
    )
    mixture = MixtureForecast(horizon=1, components=(component,))
    assert mixture.mean == pytest.approx(2.0)
    assert mixture.variance == pytest.approx(9.0)
    assert mixture.effective_model_count == pytest.approx(1.0)


def test_mixture_variance_includes_between_model_disagreement() -> None:
    components = (
        WeightedForecast(
            family=StateSpaceFamily.LOCAL_LEVEL,
            weight=0.5,
            forecast=GaussianForecast(horizon=1, mean=-5.0, variance=1.0),
        ),
        WeightedForecast(
            family=StateSpaceFamily.LOCAL_LINEAR_TREND,
            weight=0.5,
            forecast=GaussianForecast(horizon=1, mean=5.0, variance=1.0),
        ),
    )
    mixture = MixtureForecast(horizon=1, components=components)
    assert mixture.mean == pytest.approx(0.0)
    assert mixture.variance == pytest.approx(26.0)


def test_mixture_rejects_weight_mass_errors() -> None:
    with pytest.raises(StateSpaceError):
        MixtureForecast(
            horizon=1,
            components=(
                WeightedForecast(
                    family=StateSpaceFamily.LOCAL_LEVEL,
                    weight=0.4,
                    forecast=GaussianForecast(horizon=1, mean=0.0, variance=1.0),
                ),
            ),
        )


def test_crps_is_nonnegative_and_best_near_realization() -> None:
    near = MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=1.0,
                forecast=GaussianForecast(horizon=1, mean=0.0, variance=1.0),
            ),
        ),
    )
    far = MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=1.0,
                forecast=GaussianForecast(horizon=1, mean=5.0, variance=1.0),
            ),
        ),
    )
    assert gaussian_mixture_crps(near, 0.0) >= 0.0
    assert gaussian_mixture_crps(near, 0.0) < gaussian_mixture_crps(far, 0.0)


def test_probability_integral_transform_is_bounded_and_monotone() -> None:
    mixture = MixtureForecast(
        horizon=1,
        components=(
            WeightedForecast(
                family=StateSpaceFamily.LOCAL_LEVEL,
                weight=1.0,
                forecast=GaussianForecast(horizon=1, mean=0.0, variance=1.0),
            ),
        ),
    )
    low = probability_integral_transform(mixture, -2.0)
    center = probability_integral_transform(mixture, 0.0)
    high = probability_integral_transform(mixture, 2.0)
    assert 0.0 <= low < center < high <= 1.0
    assert center == pytest.approx(0.5)


def test_online_ensemble_report_weights_are_normalized() -> None:
    report = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=14, step=3),
    ).evaluate(_trend(65))
    assert report.steps
    assert sum(weight for _, weight in report.final_weights) == pytest.approx(1.0)
    for step in report.steps:
        assert sum(weight for _, weight in step.prior_weights) == pytest.approx(1.0)
        assert sum(weight for _, weight in step.posterior_weights) == pytest.approx(1.0)
        assert step.predictive.effective_model_count >= 1.0
        assert step.predictive.effective_model_count <= len(report.families) + 1e-9


def test_online_ensemble_is_deterministic() -> None:
    engine = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=12, step=2),
    )
    left = engine.evaluate(_oscillating(58))
    right = engine.evaluate(_oscillating(58))
    assert left.fingerprint == right.fingerprint
    assert left.final_weights == right.final_weights
    assert left.mean_log_score == pytest.approx(right.mean_log_score)
    assert left.mean_crps == pytest.approx(right.mean_crps)


def test_future_tail_mutation_cannot_change_earlier_ensemble_forecasts() -> None:
    common = list(_trend(55))
    left = tuple(common + [52.0, 52.5, 53.0, 53.5])
    right = tuple(common + [5000.0, -3000.0, 8000.0, -9000.0])
    engine = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=2),
    )
    left_report = engine.evaluate(left)
    right_report = engine.evaluate(right)

    shared_steps = [step for step in left_report.steps if step.target_index < len(common)]
    other_shared = [step for step in right_report.steps if step.target_index < len(common)]
    assert len(shared_steps) == len(other_shared)
    for first, second in zip(shared_steps, other_shared):
        assert first.target_index == second.target_index
        assert first.predictive.mean == pytest.approx(second.predictive.mean)
        assert first.predictive.variance == pytest.approx(second.predictive.variance)
        assert first.prior_weights == second.prior_weights
        assert first.posterior_weights == second.posterior_weights


def test_posterior_for_current_target_does_not_rewrite_current_predictive_weights() -> None:
    report = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=12, step=1),
    ).evaluate(_shock_series())
    changed = [
        step
        for step in report.steps
        if any(
            abs(prior_weight - posterior_weight) > 1e-12
            for (_, prior_weight), (_, posterior_weight) in zip(
                step.prior_weights,
                step.posterior_weights,
            )
        )
    ]
    assert changed
    for step in changed:
        component_weights = tuple(
            sorted(
                ((component.family, component.weight) for component in step.predictive.components),
                key=lambda item: item[0].value,
            )
        )
        assert component_weights == step.prior_weights


def test_min_weight_prevents_exact_component_extinction() -> None:
    floor = 0.03
    report = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(
            min_train_size=12,
            step=1,
            learning_rate=4.0,
            min_weight=floor,
        )
    ).evaluate(_trend(50))
    assert all(weight >= floor - 1e-12 for _, weight in report.final_weights)
    assert all(
        weight >= floor - 1e-12
        for step in report.steps
        for _, weight in step.posterior_weights
    )


def test_custom_prior_must_exactly_cover_family_set() -> None:
    with pytest.raises(StateSpaceError):
        OnlineBayesianEnsemble(
            families=(StateSpaceFamily.LOCAL_LEVEL, StateSpaceFamily.LOCAL_LINEAR_TREND),
            prior_weights={StateSpaceFamily.LOCAL_LEVEL: 1.0},
        )


def test_custom_prior_is_normalized() -> None:
    engine = OnlineBayesianEnsemble(
        families=(StateSpaceFamily.LOCAL_LEVEL, StateSpaceFamily.LOCAL_LINEAR_TREND),
        prior_weights={
            StateSpaceFamily.LOCAL_LEVEL: 2.0,
            StateSpaceFamily.LOCAL_LINEAR_TREND: 1.0,
        },
    )
    forecast = engine.forecast(_trend(30))
    weights = {component.family: component.weight for component in forecast.components}
    assert weights[StateSpaceFamily.LOCAL_LEVEL] == pytest.approx(2.0 / 3.0)
    assert weights[StateSpaceFamily.LOCAL_LINEAR_TREND] == pytest.approx(1.0 / 3.0)


def test_forecast_with_report_weights_supports_multi_step_distribution() -> None:
    engine = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=12, step=2),
    )
    values = _trend(55)
    report = engine.evaluate(values)
    weights = dict(report.final_weights)
    one = engine.forecast(values, horizon=1, weights=weights)
    five = engine.forecast(values, horizon=5, weights=weights)
    assert five.mean > one.mean
    assert five.variance > one.variance


def test_ensemble_report_metrics_are_finite() -> None:
    report = OnlineBayesianEnsemble(
        config=BayesianEnsembleConfig(min_train_size=15, step=3),
    ).evaluate(_oscillating(65))
    assert math.isfinite(report.mean_log_score)
    assert math.isfinite(report.mean_crps)
    assert math.isfinite(report.mae)
    assert math.isfinite(report.rmse)
    assert report.mean_crps >= 0.0
    assert report.mae >= 0.0
    assert report.rmse >= 0.0
    assert 1.0 <= report.average_effective_model_count <= len(report.families) + 1e-9


def test_invalid_ensemble_configuration_fails_closed() -> None:
    with pytest.raises(StateSpaceError):
        BayesianEnsembleConfig(min_train_size=2)
    with pytest.raises(StateSpaceError):
        BayesianEnsembleConfig(step=0)
    with pytest.raises(StateSpaceError):
        BayesianEnsembleConfig(forgetting_factor=0.0)
    with pytest.raises(StateSpaceError):
        BayesianEnsembleConfig(min_weight=0.5)
