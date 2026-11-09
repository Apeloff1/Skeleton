import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    CrossFamilyArbitrator,
    CrossFamilyConfig,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_horizon_integrity import validate_multihorizon_report
from skeleton.jeeves.probabilistic_horizons import MultiHorizonArbitrator, MultiHorizonConfig
from skeleton.jeeves.probabilistic_joint_paths import (
    JointPathConfig,
    energy_score,
    evaluate_joint_paths,
    forecast_joint_path,
    validate_joint_path_report,
    variogram_score,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _series(count: int) -> tuple[float, ...]:
    return tuple(
        30.0
        + 0.055 * index
        + 1.1 * math.sin(2.0 * math.pi * index / 11.0)
        + 0.35 * math.sin(2.0 * math.pi * index / 5.0 + 0.4)
        for index in range(count)
    )


def _engine(*, horizons: tuple[int, ...] = (1, 2, 4)) -> MultiHorizonArbitrator:
    cross = CrossFamilyArbitrator(
        experts=(
            ExpertKind.LOCAL_LEVEL,
            ExpertKind.LOCAL_LINEAR_TREND,
        ),
        config=CrossFamilyConfig(
            min_train_size=12,
            step=1,
            learning_rate=0.7,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )
    return MultiHorizonArbitrator(
        cross,
        config=MultiHorizonConfig(
            horizons=horizons,
            min_train_size=12,
            learning_rate=0.7,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )


def _config(**overrides) -> JointPathConfig:
    values = {
        "min_history": 6,
        "history_window": 14,
        "recency_decay": 0.96,
        "center_residuals": True,
        "normalize_residual_dispersion": True,
        "standardized_clip": 6.0,
        "min_scale": 1e-8,
        "variogram_power": 0.5,
    }
    values.update(overrides)
    return JointPathConfig(**values)


def test_joint_path_report_is_deterministic_and_integrity_validated() -> None:
    report = _engine().evaluate(_series(64))
    config = _config()

    first = evaluate_joint_paths(report, config=config)
    second = evaluate_joint_paths(report, config=config)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert validate_joint_path_report(first) is first


def test_residual_library_obeys_latest_target_maturity_custody() -> None:
    source = _engine().evaluate(_series(64))
    joint = evaluate_joint_paths(source, config=_config())
    maximum_horizon = max(source.config.horizons)

    for step in joint.steps:
        assert step.forecast.scenarios
        for scenario in step.forecast.scenarios:
            assert (
                scenario.source_origin_cutoff + maximum_horizon - 1
                < step.origin_cutoff
            )


def test_default_transport_preserves_current_marginal_first_two_moments() -> None:
    source = _engine().evaluate(_series(64))
    joint = evaluate_joint_paths(source, config=_config())

    for step in joint.steps:
        forecast = step.forecast
        assert forecast.expected_path == pytest.approx(
            forecast.marginal_means,
            rel=1e-9,
            abs=1e-9,
        )
        for index, variance in enumerate(forecast.marginal_variances):
            assert forecast.covariance[index][index] == pytest.approx(
                variance,
                rel=1e-8,
                abs=1e-8,
            )


def test_scenario_weights_are_recency_ordered_and_normalized() -> None:
    source = _engine().evaluate(_series(64))
    joint = evaluate_joint_paths(source, config=_config(recency_decay=0.90))
    forecast = joint.steps[-1].forecast
    weights = tuple(item.weight for item in forecast.scenarios)

    assert sum(weights) == pytest.approx(1.0)
    assert all(left < right for left, right in zip(weights, weights[1:]))
    assert forecast.effective_history_size <= forecast.scenario_count
    assert forecast.scenario_count == 14


def test_energy_and_variogram_scores_are_finite_and_nonnegative() -> None:
    source = _engine().evaluate(_series(60))
    joint = evaluate_joint_paths(source, config=_config())

    assert joint.mean_energy_score >= 0.0
    assert joint.mean_variogram_score >= 0.0
    for step in joint.steps:
        assert math.isfinite(step.energy_score)
        assert math.isfinite(step.variogram_score)
        assert step.energy_score == pytest.approx(
            energy_score(step.forecast, step.actuals)
        )
        assert step.variogram_score == pytest.approx(
            variogram_score(
                step.forecast,
                step.actuals,
                power=joint.config.variogram_power,
            )
        )


def test_joint_scenario_covariance_is_symmetric_and_correlation_bounded() -> None:
    source = _engine().evaluate(_series(60))
    forecast = evaluate_joint_paths(source, config=_config()).steps[-1].forecast
    dimensions = len(forecast.horizons)

    for left in range(dimensions):
        assert forecast.covariance[left][left] >= 0.0
        assert forecast.correlation[left][left] == pytest.approx(1.0)
        for right in range(dimensions):
            assert forecast.covariance[left][right] == pytest.approx(
                forecast.covariance[right][left]
            )
            assert -1.0 <= forecast.correlation[left][right] <= 1.0


def test_future_joint_forecast_uses_only_fully_matured_residual_vectors() -> None:
    values = _series(64)
    engine = _engine()
    report = engine.evaluate(values)
    ladder = engine.forecast_ladder(values, report)
    forecast = forecast_joint_path(ladder, report, config=_config())
    maximum_horizon = max(report.config.horizons)

    assert forecast.source_report_fingerprint == report.fingerprint
    assert forecast.origin_cutoff == len(values)
    assert forecast.horizons == report.config.horizons
    for scenario in forecast.scenarios:
        assert (
            scenario.source_origin_cutoff + maximum_horizon - 1
            < forecast.origin_cutoff
        )


def test_future_joint_forecast_rejects_historical_ladder_using_future_report_state() -> None:
    values = _series(64)
    engine = _engine()
    report = engine.evaluate(values)

    # The canonical marginal ladder can technically be requested for a shorter
    # series while reusing the report's final weights.  The joint path layer
    # refuses that chronology because those weights include targets not mature
    # at the shorter cutoff.
    historical_ladder = engine.forecast_ladder(values[:40], report)
    with pytest.raises(StateSpaceError) as exc:
        forecast_joint_path(historical_ladder, report, config=_config())
    assert exc.value.context["reason"] == "joint_path_ladder_temporal_leakage"


def test_future_suffix_mutation_cannot_change_completed_joint_scenarios() -> None:
    prefix = _series(52)
    suffix_left = tuple(100.0 + index for index in range(14))
    suffix_right = tuple(-100.0 - 2.0 * index for index in range(14))
    engine = _engine()
    config = _config()

    left = evaluate_joint_paths(engine.evaluate(prefix + suffix_left), config=config)
    right = evaluate_joint_paths(engine.evaluate(prefix + suffix_right), config=config)
    left_steps = {
        step.origin_cutoff: step
        for step in left.steps
        if step.forecast.target_indices[-1] < len(prefix)
    }
    right_steps = {
        step.origin_cutoff: step
        for step in right.steps
        if step.forecast.target_indices[-1] < len(prefix)
    }

    assert left_steps.keys() == right_steps.keys()
    for origin in left_steps:
        first = left_steps[origin]
        second = right_steps[origin]
        assert first.actuals == second.actuals
        assert first.energy_score == second.energy_score
        assert first.variogram_score == second.variogram_score
        assert first.forecast.scenarios == second.forecast.scenarios
        assert first.forecast.covariance == second.forecast.covariance
        assert first.forecast.correlation == second.forecast.correlation
        assert first.forecast.fingerprint == second.forecast.fingerprint


def test_source_multihorizon_tampering_is_rejected_before_joint_evaluation() -> None:
    source = _engine().evaluate(_series(60))
    first = source.summaries[0]
    tampered = replace(
        source,
        summaries=(replace(first, mae=first.mae + 1.0), *source.summaries[1:]),
    )

    with pytest.raises(StateSpaceError):
        evaluate_joint_paths(tampered, config=_config())


def test_joint_report_validator_rejects_derived_metric_tampering() -> None:
    source = _engine().evaluate(_series(60))
    report = evaluate_joint_paths(source, config=_config())
    tampered = replace(report, mean_energy_score=report.mean_energy_score + 0.5)

    with pytest.raises(StateSpaceError) as exc:
        validate_joint_path_report(tampered)
    assert exc.value.context["reason"] == "joint_path_summary_mismatch"


def test_joint_report_validator_rejects_scenario_covariance_tampering() -> None:
    source = _engine().evaluate(_series(60))
    report = evaluate_joint_paths(source, config=_config())
    first = report.steps[0]
    covariance = [list(row) for row in first.forecast.covariance]
    covariance[0][0] += 1.0
    forged_forecast = replace(
        first.forecast,
        covariance=tuple(tuple(row) for row in covariance),
    )
    forged_step = replace(first, forecast=forged_forecast)
    tampered = replace(report, steps=(forged_step, *report.steps[1:]))

    with pytest.raises(StateSpaceError) as exc:
        validate_joint_path_report(tampered)
    assert exc.value.context["reason"] == "joint_path_covariance_mismatch"


def test_single_horizon_source_is_not_misrepresented_as_joint_distribution() -> None:
    source = _engine(horizons=(1,)).evaluate(_series(50))

    with pytest.raises(StateSpaceError) as exc:
        evaluate_joint_paths(source, config=_config())
    assert exc.value.context["reason"] == "insufficient_joint_dimensions"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_history": 3},
        {"min_history": True},
        {"history_window": 5, "min_history": 6},
        {"recency_decay": 0.0},
        {"recency_decay": 1.1},
        {"center_residuals": 1},
        {"normalize_residual_dispersion": 1},
        {"standardized_clip": 0.0},
        {"min_scale": 0.0},
        {"variogram_power": 0.0},
        {"variogram_power": 2.1},
    ],
)
def test_invalid_joint_path_configuration_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        JointPathConfig(**kwargs)


def test_variogram_rejects_invalid_power() -> None:
    source = _engine().evaluate(_series(60))
    forecast = evaluate_joint_paths(source, config=_config()).steps[-1].forecast
    actuals = tuple(item for item in forecast.marginal_means)

    with pytest.raises(StateSpaceError):
        variogram_score(forecast, actuals, power=0.0)
    with pytest.raises(StateSpaceError):
        variogram_score(forecast, actuals, power=2.1)


def test_integrity_validator_remains_authoritative_for_source_report() -> None:
    source = _engine().evaluate(_series(60))

    assert validate_multihorizon_report(source) is source
    joint = evaluate_joint_paths(source, config=_config())
    assert joint.source_report_fingerprint == source.fingerprint
