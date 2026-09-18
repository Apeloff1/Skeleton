import math

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    CrossFamilyArbitrator,
    CrossFamilyConfig,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_bayes import BayesianTrendConfig
from skeleton.jeeves.probabilistic_regimes import RegimeHMMConfig
from skeleton.jeeves.probabilistic_spectral import SpectralConfig
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _series(count: int) -> tuple[float, ...]:
    return tuple(
        20.0
        + 0.025 * index
        + 1.6 * math.sin(2.0 * math.pi * index / 12.0)
        + 0.45 * math.sin(2.0 * math.pi * index / 5.0 + 0.3)
        for index in range(count)
    )


def _fast_arbitrator() -> CrossFamilyArbitrator:
    return CrossFamilyArbitrator(
        config=CrossFamilyConfig(
            min_train_size=32,
            step=5,
            learning_rate=0.75,
            forgetting_factor=0.99,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
        spectral_config=SpectralConfig(
            max_harmonics=2,
            min_period=3.0,
            max_period_fraction=0.75,
            robust_iterations=2,
        ),
        regime_config=RegimeHMMConfig(
            states=2,
            max_iterations=12,
        ),
    )


def test_arbitrated_forecast_separates_aleatoric_and_epistemic_variance() -> None:
    arbitrator = _fast_arbitrator()
    forecast = arbitrator.forecast(_series(48))

    assert sum(component.weight for component in forecast.components) == pytest.approx(1.0)
    assert forecast.aleatoric_variance > 0.0
    assert forecast.epistemic_variance >= 0.0
    assert forecast.variance == pytest.approx(
        forecast.aleatoric_variance + forecast.epistemic_variance
    )
    assert 1.0 <= forecast.effective_expert_count <= len(forecast.components)
    assert forecast.dominant_expert in arbitrator.experts


def test_prequential_weights_update_only_after_target_score() -> None:
    arbitrator = _fast_arbitrator()
    report = arbitrator.evaluate(_series(72))

    first = report.steps[0]
    assert all(weight == pytest.approx(0.25) for _, weight in first.prior_weights)
    assert first.prior_weights != first.posterior_weights

    for previous, current in zip(report.steps, report.steps[1:]):
        assert current.prior_weights == previous.posterior_weights


def test_report_weights_stay_normalized_and_above_floor() -> None:
    arbitrator = _fast_arbitrator()
    report = arbitrator.evaluate(_series(72))

    assert sum(weight for _, weight in report.final_weights) == pytest.approx(1.0)
    assert all(weight >= arbitrator.config.min_weight for _, weight in report.final_weights)
    for step in report.steps:
        assert sum(weight for _, weight in step.prior_weights) == pytest.approx(1.0)
        assert sum(weight for _, weight in step.posterior_weights) == pytest.approx(1.0)
        assert 0.0 <= step.epistemic_share <= 1.0


def test_future_suffix_mutation_cannot_change_completed_steps() -> None:
    prefix = _series(62)
    suffix_a = tuple(200.0 + index for index in range(12))
    suffix_b = tuple(-200.0 - 2.0 * index for index in range(12))
    arbitrator = _fast_arbitrator()

    left = arbitrator.evaluate(prefix + suffix_a)
    right = arbitrator.evaluate(prefix + suffix_b)

    left_completed = tuple(step for step in left.steps if step.target_index < len(prefix))
    right_completed = tuple(step for step in right.steps if step.target_index < len(prefix))
    assert left_completed == right_completed


def test_cross_family_evaluation_is_deterministic() -> None:
    arbitrator = _fast_arbitrator()
    values = _series(67)

    first = arbitrator.evaluate(values)
    second = arbitrator.evaluate(values)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.configuration_fingerprint == arbitrator.configuration_fingerprint


def test_forecast_from_report_uses_completed_posterior_weights() -> None:
    arbitrator = _fast_arbitrator()
    values = _series(70)
    report = arbitrator.evaluate(values)
    forecast = arbitrator.forecast_from_report(values, report, horizon=3)

    expected = dict(report.final_weights)
    assert forecast.horizon == 3
    assert {
        component.expert: component.weight
        for component in forecast.components
    } == pytest.approx(expected)
    assert math.isfinite(forecast.mean)
    assert forecast.variance > 0.0
    lower, upper = forecast.moment_interval()
    assert lower < forecast.mean < upper


def test_all_builtin_expert_kinds_can_be_arbitrated() -> None:
    experts = tuple(ExpertKind)
    arbitrator = CrossFamilyArbitrator(
        experts=experts,
        config=CrossFamilyConfig(min_train_size=32, step=8),
        spectral_config=SpectralConfig(max_harmonics=1, robust_iterations=2),
        regime_config=RegimeHMMConfig(states=2, max_iterations=8),
    )
    forecast = arbitrator.forecast(_series(48))

    assert {component.expert for component in forecast.components} == set(experts)
    assert len(forecast.components) == len(experts)


def test_exact_bayesian_trend_is_a_first_class_expert() -> None:
    arbitrator = CrossFamilyArbitrator(
        experts=(ExpertKind.BAYESIAN_TREND, ExpertKind.SPECTRAL),
        bayesian_config=BayesianTrendConfig(window=36),
        spectral_config=SpectralConfig(max_harmonics=2, robust_iterations=2),
    )
    forecast = arbitrator.forecast(_series(48), horizon=4)

    components = {component.expert: component for component in forecast.components}
    bayesian = components[ExpertKind.BAYESIAN_TREND].predictive
    assert bayesian.horizon == 4
    assert math.isfinite(bayesian.mean)
    assert bayesian.variance > 0.0
    assert math.isfinite(bayesian.log_density(_series(52)[-1]))


def test_report_identity_mismatch_fails_closed() -> None:
    values = _series(64)
    source = _fast_arbitrator()
    report = source.evaluate(values)
    mismatched = CrossFamilyArbitrator(
        config=CrossFamilyConfig(
            min_train_size=32,
            step=5,
            learning_rate=0.25,
        ),
        spectral_config=SpectralConfig(max_harmonics=2),
        regime_config=RegimeHMMConfig(states=2, max_iterations=12),
    )

    with pytest.raises(StateSpaceError):
        mismatched.forecast_from_report(values, report)


def test_report_binds_underlying_expert_model_configs() -> None:
    values = _series(64)
    source = _fast_arbitrator()
    report = source.evaluate(values)
    mismatched = CrossFamilyArbitrator(
        config=source.config,
        spectral_config=SpectralConfig(
            max_harmonics=1,
            min_period=3.0,
            max_period_fraction=0.75,
            robust_iterations=2,
        ),
        regime_config=source.regime_config,
    )

    assert mismatched.config == source.config
    assert mismatched.experts == source.experts
    assert mismatched.configuration_fingerprint != source.configuration_fingerprint
    with pytest.raises(StateSpaceError):
        mismatched.forecast_from_report(values, report)


def test_configuration_identity_binds_bayesian_assumptions() -> None:
    left = CrossFamilyArbitrator(
        experts=(ExpertKind.BAYESIAN_TREND, ExpertKind.LOCAL_LEVEL),
        bayesian_config=BayesianTrendConfig(window=24),
    )
    right = CrossFamilyArbitrator(
        experts=(ExpertKind.BAYESIAN_TREND, ExpertKind.LOCAL_LEVEL),
        bayesian_config=BayesianTrendConfig(window=48),
    )

    assert left.config == right.config
    assert left.experts == right.experts
    assert left.configuration_fingerprint != right.configuration_fingerprint


def test_prior_must_exactly_cover_experts() -> None:
    with pytest.raises(StateSpaceError):
        CrossFamilyArbitrator(
            experts=(ExpertKind.SPECTRAL, ExpertKind.LOCAL_LEVEL),
            prior_weights={ExpertKind.SPECTRAL: 1.0},
        )

    with pytest.raises(StateSpaceError):
        CrossFamilyArbitrator(
            experts=(ExpertKind.SPECTRAL, ExpertKind.LOCAL_LEVEL),
            prior_weights={
                ExpertKind.SPECTRAL: 0.0,
                ExpertKind.LOCAL_LEVEL: 0.0,
            },
        )


def test_duplicate_experts_fail_closed() -> None:
    with pytest.raises(StateSpaceError):
        CrossFamilyArbitrator(
            experts=(ExpertKind.SPECTRAL, ExpertKind.SPECTRAL),
        )


def test_weight_floor_must_leave_free_probability_mass() -> None:
    with pytest.raises(StateSpaceError):
        CrossFamilyArbitrator(
            experts=tuple(ExpertKind),
            config=CrossFamilyConfig(min_weight=0.20),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_train_size": 7},
        {"step": 0},
        {"learning_rate": -0.1},
        {"learning_rate": 8.1},
        {"forgetting_factor": 0.0},
        {"forgetting_factor": 1.1},
        {"prior_strength": -0.1},
        {"prior_strength": 1.1},
        {"min_weight": -0.1},
        {"max_log_score_gap": 0.0},
        {"max_log_score_gap": 1001.0},
    ],
)
def test_invalid_cross_family_configuration_fails_closed(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(StateSpaceError):
        CrossFamilyConfig(**kwargs)


def test_short_series_and_invalid_horizon_fail_closed() -> None:
    arbitrator = _fast_arbitrator()

    with pytest.raises(StateSpaceError):
        arbitrator.evaluate(_series(32))

    with pytest.raises(StateSpaceError):
        arbitrator.forecast(_series(40), horizon=0)


def test_component_log_scores_and_mixture_score_are_finite() -> None:
    report = _fast_arbitrator().evaluate(_series(67))

    for step in report.steps:
        assert math.isfinite(step.mixture_log_score)
        assert len(step.component_log_scores) == len(report.experts)
        assert all(math.isfinite(score) for _, score in step.component_log_scores)
    assert math.isfinite(report.mean_log_score)
    assert report.rmse >= 0.0
    assert report.mae >= 0.0
