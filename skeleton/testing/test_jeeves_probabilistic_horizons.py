import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    CrossFamilyArbitrator,
    CrossFamilyConfig,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_horizons import (
    MultiHorizonArbitrator,
    MultiHorizonConfig,
    evaluate_multihorizon_conformal,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _series(count: int) -> tuple[float, ...]:
    return tuple(
        12.0
        + 0.08 * index
        + 0.7 * math.sin(2.0 * math.pi * index / 9.0)
        + 0.15 * math.sin(2.0 * math.pi * index / 4.0 + 0.2)
        for index in range(count)
    )


def _fast_cross_family() -> CrossFamilyArbitrator:
    return CrossFamilyArbitrator(
        experts=(
            ExpertKind.LOCAL_LEVEL,
            ExpertKind.LOCAL_LINEAR_TREND,
        ),
        config=CrossFamilyConfig(
            min_train_size=12,
            step=2,
            learning_rate=0.7,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )


def _engine(
    *,
    horizons: tuple[int, ...] = (1, 2, 4),
    learning_rate: float = 0.75,
) -> MultiHorizonArbitrator:
    return MultiHorizonArbitrator(
        _fast_cross_family(),
        config=MultiHorizonConfig(
            horizons=horizons,
            min_train_size=12,
            learning_rate=learning_rate,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )


def test_multi_horizon_counts_and_target_geometry_are_exact() -> None:
    values = _series(40)
    report = _engine().evaluate(values)

    expected = {1: 28, 2: 27, 4: 25}
    assert tuple(summary.horizon for summary in report.summaries) == (1, 2, 4)

    for summary in report.summaries:
        assert len(summary.settlements) == expected[summary.horizon]
        for step in summary.settlements:
            assert step.target_index == (
                step.origin_cutoff + step.horizon - 1
            )
            assert step.forecast.predictive.horizon == step.horizon
            assert step.target_index < len(values)


def test_long_horizon_feedback_is_delayed_until_target_matures() -> None:
    report = _engine().evaluate(_series(36))
    one = report.summary_for(1)
    four = report.summary_for(4)

    initial_one = one.settlements[0].forecast.issue_weights
    initial_four = four.settlements[0].forecast.issue_weights

    assert one.settlements[1].forecast.issue_weights == (
        one.settlements[0].posterior_weights
    )

    # Four forecasts are issued before the first horizon-4 target is observable.
    assert all(
        step.forecast.issue_weights == initial_four
        for step in four.settlements[:4]
    )

    assert initial_one == initial_four
    assert four.settlements[4].forecast.issue_weights == (
        four.settlements[0].posterior_weights
    )


def test_issue_weights_are_not_retroactively_rewritten_at_settlement() -> None:
    report = _engine().evaluate(_series(38))
    four = report.summary_for(4)

    first = four.settlements[0]
    later = four.settlements[3]

    assert first.forecast.issue_weights == later.forecast.issue_weights
    assert first.update_prior_weights == first.forecast.issue_weights
    assert four.settlements[4].forecast.issue_weights == first.posterior_weights


def test_update_prior_can_include_only_earlier_matured_same_horizon_evidence() -> None:
    report = _engine().evaluate(_series(40))
    four = report.summary_for(4)

    for previous, current in zip(four.settlements, four.settlements[1:]):
        assert current.update_prior_weights == previous.posterior_weights

    # For horizon 4, the forecast issued four settlements later is the first
    # one allowed to consume this settlement's posterior.
    for index, step in enumerate(four.settlements[4:], start=4):
        assert step.forecast.issue_weights == (
            four.settlements[index - 4].posterior_weights
        )


def test_future_suffix_mutation_cannot_change_completed_horizon_evidence() -> None:
    prefix = _series(30)
    suffix_a = tuple(80.0 + index for index in range(10))
    suffix_b = tuple(-80.0 - 2.0 * index for index in range(10))
    engine = _engine()

    left = engine.evaluate(prefix + suffix_a)
    right = engine.evaluate(prefix + suffix_b)

    for horizon in engine.config.horizons:
        left_completed = tuple(
            step
            for step in left.summary_for(horizon).settlements
            if step.target_index < len(prefix)
        )
        right_completed = tuple(
            step
            for step in right.summary_for(horizon).settlements
            if step.target_index < len(prefix)
        )
        assert left_completed == right_completed


def test_each_horizon_maintains_normalized_recoverable_weights() -> None:
    engine = _engine()
    report = engine.evaluate(_series(40))

    for summary in report.summaries:
        assert sum(weight for _, weight in summary.final_weights) == pytest.approx(1.0)
        assert all(
            weight >= engine.config.min_weight
            for _, weight in summary.final_weights
        )
        for step in summary.settlements:
            assert sum(
                weight for _, weight in step.forecast.issue_weights
            ) == pytest.approx(1.0)
            assert sum(
                weight for _, weight in step.update_prior_weights
            ) == pytest.approx(1.0)
            assert sum(
                weight for _, weight in step.posterior_weights
            ) == pytest.approx(1.0)


def test_multi_horizon_evaluation_is_deterministic() -> None:
    values = _series(36)
    engine = _engine()

    first = engine.evaluate(values)
    second = engine.evaluate(values)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.configuration_fingerprint == engine.configuration_fingerprint


def test_dependence_report_aligns_only_common_forecast_origins() -> None:
    report = _engine().evaluate(_series(40))
    dependence = report.dependence

    assert dependence is not None
    assert dependence.horizons == (1, 2, 4)
    assert dependence.sample_size == len(report.summary_for(4).settlements)
    assert dependence.aligned_origins[0] == 12
    assert dependence.aligned_origins[-1] == 36


def test_error_covariance_is_symmetric_and_correlation_is_bounded() -> None:
    dependence = _engine().evaluate(_series(40)).dependence
    assert dependence is not None

    size = len(dependence.horizons)
    for left in range(size):
        assert dependence.covariance[left][left] > 0.0
        assert dependence.correlation[left][left] == 1.0
        for right in range(size):
            assert dependence.covariance[left][right] == pytest.approx(
                dependence.covariance[right][left]
            )
            assert -1.0 <= dependence.correlation[left][right] <= 1.0


def test_forecast_ladder_uses_horizon_specific_final_weights() -> None:
    values = _series(40)
    engine = _engine()
    report = engine.evaluate(values)
    ladder = engine.forecast_ladder(values, report)

    assert ladder.origin_cutoff == len(values)
    assert tuple(forecast.horizon for forecast in ladder.forecasts) == (1, 2, 4)

    for forecast in ladder.forecasts:
        summary = report.summary_for(forecast.horizon)
        assert forecast.issue_weights == summary.final_weights
        assert forecast.target_index == len(values) + forecast.horizon - 1
        actual_component_weights = {
            component.expert: component.weight
            for component in forecast.predictive.components
        }
        assert actual_component_weights == pytest.approx(
            dict(summary.final_weights)
        )


def test_forecast_ladder_fails_closed_on_configuration_mismatch() -> None:
    values = _series(38)
    source = _engine()
    report = source.evaluate(values)
    changed = _engine(learning_rate=0.25)

    assert source.configuration_fingerprint != changed.configuration_fingerprint
    with pytest.raises(StateSpaceError):
        changed.forecast_ladder(values, report)


def test_forecast_ladder_rejects_tampered_summary_fingerprint() -> None:
    values = _series(38)
    engine = _engine()
    report = engine.evaluate(values)
    first = report.summaries[0]
    tampered = replace(
        report,
        summaries=(
            replace(first, fingerprint="0" * 64),
            *report.summaries[1:],
        ),
    )

    with pytest.raises(StateSpaceError):
        engine.forecast_ladder(values, tampered)


def test_per_horizon_conformal_keeps_calibration_streams_separate() -> None:
    report = _engine().evaluate(_series(42))
    conformal = evaluate_multihorizon_conformal(
        report,
        config=ConformalConfig(
            alpha=0.10,
            min_calibration=4,
            calibration_window=12,
            adaptive_rate=0.0,
        ),
    )

    assert tuple(item.horizon for item in conformal.reports) == (1, 2, 4)
    for item in conformal.reports:
        source = report.summary_for(item.horizon)
        assert item.report.steps
        assert all(
            step.interval.horizon == item.horizon
            for step in item.report.steps
        )
        assert item.report.steps[-1].interval.target_index <= (
            source.settlements[-1].target_index
        )


def test_per_horizon_conformal_is_deterministic() -> None:
    report = _engine().evaluate(_series(40))
    config = ConformalConfig(
        min_calibration=4,
        calibration_window=10,
        adaptive_rate=0.01,
    )

    left = evaluate_multihorizon_conformal(report, config=config)
    right = evaluate_multihorizon_conformal(report, config=config)

    assert left == right
    assert left.fingerprint == right.fingerprint


def test_horizon_prior_must_cover_every_horizon_and_expert() -> None:
    arbitrator = _fast_cross_family()
    config = MultiHorizonConfig(horizons=(1, 3), min_train_size=12)

    with pytest.raises(StateSpaceError):
        MultiHorizonArbitrator(
            arbitrator,
            config=config,
            prior_weights={
                1: {
                    ExpertKind.LOCAL_LEVEL: 0.5,
                    ExpertKind.LOCAL_LINEAR_TREND: 0.5,
                }
            },
        )

    with pytest.raises(StateSpaceError):
        MultiHorizonArbitrator(
            arbitrator,
            config=config,
            prior_weights={
                1: {
                    ExpertKind.LOCAL_LEVEL: 1.0,
                    ExpertKind.LOCAL_LINEAR_TREND: 0.0,
                },
                3: {ExpertKind.LOCAL_LEVEL: 1.0},
            },
        )


def test_custom_horizon_priors_are_bound_into_configuration_identity() -> None:
    arbitrator = _fast_cross_family()
    config = MultiHorizonConfig(horizons=(1, 3), min_train_size=12)
    left = MultiHorizonArbitrator(arbitrator, config=config)
    right = MultiHorizonArbitrator(
        arbitrator,
        config=config,
        prior_weights={
            1: {
                ExpertKind.LOCAL_LEVEL: 0.8,
                ExpertKind.LOCAL_LINEAR_TREND: 0.2,
            },
            3: {
                ExpertKind.LOCAL_LEVEL: 0.2,
                ExpertKind.LOCAL_LINEAR_TREND: 0.8,
            },
        },
    )

    assert left.config == right.config
    assert left.configuration_fingerprint != right.configuration_fingerprint


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizons": ()},
        {"horizons": (0, 1)},
        {"horizons": (1, 1)},
        {"horizons": (2, 1)},
        {"min_train_size": 7},
        {"learning_rate": -0.1},
        {"learning_rate": 8.1},
        {"forgetting_factor": 0.0},
        {"forgetting_factor": 1.1},
        {"prior_strength": -0.1},
        {"prior_strength": 1.1},
        {"min_weight": -0.1},
        {"max_log_score_gap": 0.0},
        {"max_log_score_gap": 1001.0},
        {"covariance_floor": 0.0},
    ],
)
def test_invalid_multihorizon_configuration_fails_closed(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(StateSpaceError):
        MultiHorizonConfig(**kwargs)


def test_short_or_nonfinite_series_fail_closed() -> None:
    engine = _engine()

    with pytest.raises(StateSpaceError):
        engine.evaluate(_series(15))

    malformed = list(_series(24))
    malformed[17] = float("nan")
    with pytest.raises(StateSpaceError):
        engine.evaluate(malformed)


def test_summary_scores_are_finite_and_metrics_are_nonnegative() -> None:
    report = _engine().evaluate(_series(38))

    for summary in report.summaries:
        assert math.isfinite(summary.mean_log_score)
        assert summary.mae >= 0.0
        assert summary.rmse >= 0.0
        assert 1.0 <= summary.average_effective_expert_count <= len(report.experts)
        assert 0.0 <= summary.average_epistemic_share <= 1.0
        for step in summary.settlements:
            assert math.isfinite(step.mixture_log_score)
            assert all(
                math.isfinite(score)
                for _, score in step.component_log_scores
            )
