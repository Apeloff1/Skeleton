from __future__ import annotations

import math
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from skeleton.jeeves.probabilistic_conformal import (
    ConformalCalibrationState,
    ConformalConfig,
    ConformalObservation,
    attainable_miscoverage_floor,
    conformal_interval_from_scores,
    evaluate_conformal_observations,
    finite_sample_conformal_quantile,
    nonconformity_score,
    observations_from_cross_family_report,
    required_calibration_size,
    state_from_report,
    verify_report_integrity,
    verify_state_integrity,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    mean: float
    variance: float = 1.0
    horizon: int = 1


def _observations(count: int, *, horizon: int = 1) -> tuple[ConformalObservation, ...]:
    observations = []
    for index in range(count):
        mean = 10.0 + 0.05 * index
        error = 0.6 * math.sin(0.73 * index) + 0.15 * math.cos(0.19 * index)
        observations.append(
            ConformalObservation(
                target_index=index,
                actual=mean + error,
                forecast=_Forecast(mean=mean, variance=0.64, horizon=horizon),
            )
        )
    return tuple(observations)


def test_finite_sample_quantile_uses_correct_order_statistic() -> None:
    scores = tuple(float(value) for value in range(1, 10))

    assert finite_sample_conformal_quantile(scores, miscoverage=0.20) == 8.0
    assert finite_sample_conformal_quantile(scores, miscoverage=0.50) == 5.0


def test_finite_sample_quantile_fails_when_requested_coverage_is_unattainable() -> None:
    scores = (1.0, 2.0, 3.0, 4.0)

    assert attainable_miscoverage_floor(len(scores)) == pytest.approx(0.20)
    with pytest.raises(StateSpaceError) as exc_info:
        finite_sample_conformal_quantile(scores, miscoverage=0.10)

    assert exc_info.value.context["reason"] == "unattainable_conformal_miscoverage"
    assert exc_info.value.context["required_calibration_size"] == 9


def test_exact_finite_sample_floor_is_allowed() -> None:
    scores = (1.0, 2.0, 3.0, 4.0)

    assert finite_sample_conformal_quantile(scores, miscoverage=0.20) == 4.0


def test_required_calibration_size_matches_attainable_floor_boundary() -> None:
    for alpha, expected in ((0.50, 1), (0.20, 4), (0.10, 9), (0.05, 19)):
        required = required_calibration_size(alpha)
        assert required == expected
        assert attainable_miscoverage_floor(required) <= alpha + 1e-15
        if required > 1:
            assert attainable_miscoverage_floor(required - 1) > alpha - 1e-15


def test_direct_interval_fails_closed_on_unattainable_alpha() -> None:
    config = ConformalConfig(
        miscoverage=0.10,
        min_calibration_size=4,
        adaptive=False,
    )

    with pytest.raises(StateSpaceError) as exc_info:
        conformal_interval_from_scores(
            _Forecast(mean=0.0),
            (1.0, 2.0, 3.0, 4.0),
            target_index=4,
            miscoverage=0.10,
            config=config,
        )

    assert exc_info.value.context["reason"] == "unattainable_conformal_miscoverage"


def test_streaming_evaluator_records_finite_sample_coverage_limit() -> None:
    report = evaluate_conformal_observations(
        _observations(7),
        config=ConformalConfig(
            miscoverage=0.10,
            min_calibration_size=4,
            calibration_window=8,
            adaptive=False,
        ),
    )

    first = report.steps[4]
    assert first.interval is not None
    assert first.prior_miscoverage == pytest.approx(0.10)
    assert first.effective_miscoverage == pytest.approx(0.20)
    assert first.interval.requested_miscoverage == pytest.approx(0.10)
    assert first.interval.miscoverage == pytest.approx(0.20)
    assert first.interval.coverage_limited
    assert report.finite_sample_limited_intervals >= 1


def test_rolling_window_imposes_permanent_attainable_alpha_floor() -> None:
    report = evaluate_conformal_observations(
        _observations(30),
        config=ConformalConfig(
            miscoverage=0.01,
            min_calibration_size=4,
            calibration_window=9,
            adaptive=False,
            min_miscoverage=0.005,
            max_miscoverage=0.50,
        ),
    )

    mature = tuple(step for step in report.steps if step.calibration_size_before == 9)
    assert mature
    assert all(step.interval is not None for step in mature)
    assert all(step.effective_miscoverage == pytest.approx(0.10) for step in mature)
    assert all(step.interval.coverage_limited for step in mature if step.interval is not None)


def test_warmup_targets_never_receive_retroactive_intervals() -> None:
    report = evaluate_conformal_observations(
        _observations(9),
        config=ConformalConfig(
            miscoverage=0.20,
            min_calibration_size=4,
            calibration_window=8,
            adaptive=False,
        ),
    )

    assert report.warmup_observations == 4
    assert report.evaluated_intervals == 5
    assert all(step.interval is None for step in report.steps[:4])
    assert all(step.interval is not None for step in report.steps[4:])
    assert report.steps[4].calibration_size_before == 4


def test_future_tail_mutation_cannot_change_completed_conformal_steps() -> None:
    prefix = list(_observations(12))
    left = prefix + [
        ConformalObservation(
            target_index=12 + index,
            actual=100.0 + index,
            forecast=_Forecast(mean=10.6 + 0.05 * index, variance=0.64),
        )
        for index in range(6)
    ]
    right = prefix + [
        ConformalObservation(
            target_index=12 + index,
            actual=-100.0 - index,
            forecast=_Forecast(mean=10.6 + 0.05 * index, variance=0.64),
        )
        for index in range(6)
    ]
    config = ConformalConfig(
        min_calibration_size=5,
        calibration_window=10,
        adaptive=True,
        adaptation_rate=0.03,
    )

    left_report = evaluate_conformal_observations(left, config=config)
    right_report = evaluate_conformal_observations(right, config=config)

    assert left_report.steps[:12] == right_report.steps[:12]


def test_normalized_conformal_radius_scales_with_predictive_uncertainty() -> None:
    scores = (0.5, 0.7, 0.8, 0.9, 1.0, 1.1)
    config = ConformalConfig(
        miscoverage=0.20,
        min_calibration_size=4,
        adaptive=False,
    )

    narrow = conformal_interval_from_scores(
        _Forecast(mean=5.0, variance=1.0),
        scores,
        target_index=10,
        miscoverage=0.20,
        config=config,
    )
    wide = conformal_interval_from_scores(
        _Forecast(mean=5.0, variance=4.0),
        scores,
        target_index=10,
        miscoverage=0.20,
        config=config,
    )

    assert wide.score_quantile == pytest.approx(narrow.score_quantile)
    assert wide.radius == pytest.approx(2.0 * narrow.radius)


def test_raw_nonconformity_does_not_depend_on_predictive_variance() -> None:
    config = ConformalConfig(
        normalized_scores=False,
        min_calibration_size=2,
    )
    actual = 7.5

    left = nonconformity_score(_Forecast(mean=5.0, variance=1.0), actual, config=config)
    right = nonconformity_score(_Forecast(mean=5.0, variance=100.0), actual, config=config)

    assert left == pytest.approx(2.5)
    assert right == pytest.approx(left)


def test_adaptive_miscoverage_tightens_after_a_miss_then_recovers_on_hit() -> None:
    observations = (
        ConformalObservation(0, 1.0, _Forecast(0.0)),
        ConformalObservation(1, 1.0, _Forecast(0.0)),
        ConformalObservation(2, 10.0, _Forecast(0.0)),
        ConformalObservation(3, 0.0, _Forecast(0.0)),
    )
    config = ConformalConfig(
        miscoverage=0.20,
        min_calibration_size=2,
        calibration_window=8,
        adaptive=True,
        adaptation_rate=0.10,
        min_miscoverage=0.01,
        max_miscoverage=0.50,
    )

    report = evaluate_conformal_observations(observations, config=config)
    miss_step = report.steps[2]
    hit_step = report.steps[3]

    assert miss_step.covered is False
    assert miss_step.posterior_miscoverage < miss_step.prior_miscoverage
    assert miss_step.effective_miscoverage == pytest.approx(1.0 / 3.0)
    assert hit_step.prior_miscoverage == pytest.approx(miss_step.posterior_miscoverage)
    assert hit_step.covered is True
    assert hit_step.posterior_miscoverage > hit_step.prior_miscoverage


def test_adaptive_alpha_can_hit_lower_bound_without_creating_impossible_interval() -> None:
    observations = tuple(
        ConformalObservation(index, 100.0 + index, _Forecast(0.0))
        for index in range(15)
    )
    config = ConformalConfig(
        miscoverage=0.20,
        min_calibration_size=2,
        calibration_window=5,
        adaptive=True,
        adaptation_rate=1.0,
        min_miscoverage=0.01,
        max_miscoverage=0.50,
    )

    report = evaluate_conformal_observations(observations, config=config)

    assert report.final_miscoverage == pytest.approx(config.min_miscoverage)
    mature = [step for step in report.steps if step.interval is not None]
    assert mature
    assert all(step.effective_miscoverage is not None for step in mature)
    assert all(
        step.effective_miscoverage
        >= attainable_miscoverage_floor(step.calibration_size_before) - 1e-15
        for step in mature
    )


def test_adaptive_alpha_can_hit_upper_bound() -> None:
    observations = tuple(
        ConformalObservation(index, 0.0, _Forecast(0.0))
        for index in range(20)
    )
    config = ConformalConfig(
        miscoverage=0.20,
        min_calibration_size=2,
        calibration_window=10,
        adaptive=True,
        adaptation_rate=1.0,
        min_miscoverage=0.01,
        max_miscoverage=0.30,
    )

    report = evaluate_conformal_observations(observations, config=config)

    assert report.final_miscoverage == pytest.approx(config.max_miscoverage)


def test_fixed_mode_keeps_nominal_miscoverage_constant() -> None:
    config = ConformalConfig(
        miscoverage=0.15,
        min_calibration_size=3,
        adaptive=False,
    )
    report = evaluate_conformal_observations(_observations(12), config=config)

    assert all(step.prior_miscoverage == pytest.approx(0.15) for step in report.steps)
    assert all(step.posterior_miscoverage == pytest.approx(0.15) for step in report.steps)
    assert report.final_miscoverage == pytest.approx(0.15)


def test_rolling_window_is_preserved_in_next_target_state() -> None:
    config = ConformalConfig(
        min_calibration_size=4,
        calibration_window=6,
        adaptive=False,
    )
    report = evaluate_conformal_observations(_observations(20), config=config)
    state = state_from_report(report)

    assert len(state.scores) == 6
    assert state.ready
    assert state.scores == tuple(
        step.nonconformity_score for step in report.steps[-6:]
    )


def test_state_builds_next_interval_without_consuming_next_actual() -> None:
    report = evaluate_conformal_observations(
        _observations(12),
        config=ConformalConfig(min_calibration_size=4, adaptive=False),
    )
    state = state_from_report(report)
    interval = state.interval_for(
        _Forecast(mean=11.0, variance=0.81),
        target_index=12,
    )

    assert interval is not None
    assert interval.target_index == 12
    assert interval.center == pytest.approx(11.0)
    assert interval.calibration_size == len(state.scores)


def test_state_uses_attainable_floor_instead_of_overclaiming_coverage() -> None:
    report = evaluate_conformal_observations(
        _observations(7),
        config=ConformalConfig(
            miscoverage=0.05,
            min_calibration_size=4,
            calibration_window=4,
            adaptive=False,
            min_miscoverage=0.005,
        ),
    )
    state = state_from_report(report)
    interval = state.interval_for(_Forecast(mean=11.0), target_index=7)

    assert interval is not None
    assert interval.requested_miscoverage == pytest.approx(0.05)
    assert interval.miscoverage == pytest.approx(0.20)
    assert interval.coverage_limited


def test_state_rejects_cross_horizon_reuse() -> None:
    report = evaluate_conformal_observations(
        _observations(10, horizon=1),
        config=ConformalConfig(min_calibration_size=4),
    )
    state = state_from_report(report)

    with pytest.raises(StateSpaceError):
        state.interval_for(_Forecast(mean=1.0, variance=1.0, horizon=2), target_index=10)


def test_report_and_state_integrity_detect_tampering() -> None:
    report = evaluate_conformal_observations(
        _observations(12),
        config=ConformalConfig(min_calibration_size=4),
    )
    state = state_from_report(report)

    verify_report_integrity(report)
    verify_state_integrity(state, report_fingerprint=report.fingerprint)

    tampered_report = replace(report, fingerprint="0" * 64)
    with pytest.raises(StateSpaceError) as report_exc:
        verify_report_integrity(tampered_report)
    assert report_exc.value.context["reason"] == "conformal_report_integrity_failure"

    tampered_state = replace(state, fingerprint="f" * 64)
    with pytest.raises(StateSpaceError) as state_exc:
        verify_state_integrity(tampered_state, report_fingerprint=report.fingerprint)
    assert state_exc.value.context["reason"] == "conformal_state_integrity_failure"


def test_state_constructor_rejects_window_overflow_and_nonfinite_scores() -> None:
    config = ConformalConfig(min_calibration_size=2, calibration_window=3)

    with pytest.raises(StateSpaceError):
        ConformalCalibrationState(
            horizon=1,
            scores=(1.0, 2.0, 3.0, 4.0),
            current_miscoverage=0.1,
            config=config,
            fingerprint="0" * 64,
        )

    with pytest.raises(StateSpaceError):
        ConformalCalibrationState(
            horizon=1,
            scores=(1.0, float("nan")),
            current_miscoverage=0.1,
            config=config,
            fingerprint="0" * 64,
        )


def test_mixed_horizons_fail_closed() -> None:
    observations = list(_observations(6, horizon=1))
    observations.append(
        ConformalObservation(
            target_index=6,
            actual=1.0,
            forecast=_Forecast(mean=1.0, variance=1.0, horizon=2),
        )
    )

    with pytest.raises(StateSpaceError):
        evaluate_conformal_observations(observations)


def test_non_monotonic_and_duplicate_target_indices_fail_closed() -> None:
    non_monotonic = (
        ConformalObservation(0, 1.0, _Forecast(1.0)),
        ConformalObservation(2, 1.0, _Forecast(1.0)),
        ConformalObservation(1, 1.0, _Forecast(1.0)),
    )
    duplicate = (
        ConformalObservation(0, 1.0, _Forecast(1.0)),
        ConformalObservation(0, 1.0, _Forecast(1.0)),
    )

    with pytest.raises(StateSpaceError):
        evaluate_conformal_observations(non_monotonic)
    with pytest.raises(StateSpaceError):
        evaluate_conformal_observations(duplicate)


def test_report_is_deterministic_and_fingerprint_binds_realizations() -> None:
    config = ConformalConfig(
        min_calibration_size=4,
        calibration_window=8,
        adaptive=True,
    )
    observations = _observations(14)
    first = evaluate_conformal_observations(observations, config=config)
    second = evaluate_conformal_observations(observations, config=config)
    changed = list(observations)
    original = changed[-1]
    changed[-1] = ConformalObservation(
        target_index=original.target_index,
        actual=original.actual + 0.01,
        forecast=original.forecast,
    )
    changed_report = evaluate_conformal_observations(changed, config=config)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed_report.fingerprint


def test_interval_score_penalizes_misses_more_than_equal_width_hits() -> None:
    interval = conformal_interval_from_scores(
        _Forecast(mean=0.0, variance=1.0),
        (1.0, 1.0, 1.0, 1.0),
        target_index=5,
        miscoverage=0.20,
        config=ConformalConfig(
            miscoverage=0.20,
            min_calibration_size=4,
            adaptive=False,
        ),
    )

    hit_score = interval.interval_score(0.0)
    miss_score = interval.interval_score(3.0)
    assert hit_score == pytest.approx(interval.width)
    assert miss_score > hit_score


def test_interval_geometry_fails_closed_on_float_overflow() -> None:
    config = ConformalConfig(
        miscoverage=0.50,
        min_calibration_size=1,
        normalized_scores=True,
        adaptive=False,
    )

    with pytest.raises(StateSpaceError) as exc_info:
        conformal_interval_from_scores(
            _Forecast(mean=1e308, variance=4.0),
            (1e308,),
            target_index=1,
            miscoverage=0.50,
            config=config,
        )
    assert exc_info.value.context["reason"] == "numerical_instability"


def test_nonconformity_fails_closed_when_finite_operands_overflow_residual() -> None:
    with pytest.raises(StateSpaceError) as exc_info:
        nonconformity_score(
            _Forecast(mean=-1e308, variance=1.0),
            1e308,
        )
    assert exc_info.value.context["reason"] == "numerical_instability"


def test_nonfinite_negative_and_boolean_scores_fail_closed() -> None:
    for scores in (
        (1.0, float("nan")),
        (1.0, float("inf")),
        (1.0, -1.0),
        (1.0, True),
    ):
        with pytest.raises(StateSpaceError):
            finite_sample_conformal_quantile(scores, miscoverage=0.50)


def test_report_metrics_are_computed_only_after_warmup() -> None:
    report = evaluate_conformal_observations(
        _observations(18),
        config=ConformalConfig(
            miscoverage=0.20,
            min_calibration_size=5,
            calibration_window=10,
            adaptive=False,
        ),
    )

    assert report.evaluated_intervals == 13
    assert report.warmup_observations == 5
    assert report.empirical_coverage is not None
    assert 0.0 <= report.empirical_coverage <= 1.0
    assert report.coverage_gap is not None
    assert report.average_width is not None and report.average_width >= 0.0
    assert report.average_interval_score is not None
    assert report.average_interval_score >= report.average_width


def test_short_history_returns_evidence_without_fabricating_coverage() -> None:
    report = evaluate_conformal_observations(
        _observations(3),
        config=ConformalConfig(min_calibration_size=4),
    )

    assert report.evaluated_intervals == 0
    assert report.warmup_observations == 3
    assert report.finite_sample_limited_intervals == 0
    assert report.empirical_coverage is None
    assert report.coverage_gap is None
    assert report.average_width is None
    assert report.average_interval_score is None
    assert report.last_interval is None


def test_cross_family_adapter_uses_preissued_predictive_objects() -> None:
    forecast_a = _Forecast(mean=1.0, variance=2.0)
    forecast_b = _Forecast(mean=2.0, variance=3.0)
    report = SimpleNamespace(
        steps=(
            SimpleNamespace(target_index=4, actual=1.5, predictive=forecast_a),
            SimpleNamespace(target_index=5, actual=2.5, predictive=forecast_b),
        )
    )

    observations = observations_from_cross_family_report(report)

    assert observations[0].forecast is forecast_a
    assert observations[1].forecast is forecast_b
    assert observations[0].actual == pytest.approx(1.5)


def test_cross_family_adapter_rejects_malformed_empty_and_noniterable_reports() -> None:
    with pytest.raises(StateSpaceError):
        observations_from_cross_family_report(object())

    with pytest.raises(StateSpaceError):
        observations_from_cross_family_report(SimpleNamespace(steps=()))

    with pytest.raises(StateSpaceError):
        observations_from_cross_family_report(SimpleNamespace(steps=1))

    with pytest.raises(StateSpaceError):
        observations_from_cross_family_report(
            SimpleNamespace(steps=(SimpleNamespace(target_index=1),))
        )


def test_cross_family_adapter_does_not_coerce_target_identity() -> None:
    forecast = _Forecast(mean=1.0)
    for bad_index in (True, 1.0, "1"):
        report = SimpleNamespace(
            steps=(
                SimpleNamespace(
                    target_index=bad_index,
                    actual=1.0,
                    predictive=forecast,
                ),
            )
        )
        with pytest.raises(StateSpaceError):
            observations_from_cross_family_report(report)


def test_normalized_score_respects_minimum_scale_floor() -> None:
    config = ConformalConfig(
        min_calibration_size=2,
        min_scale=0.5,
        normalized_scores=True,
    )
    forecast = _Forecast(mean=0.0, variance=1e-8)

    assert nonconformity_score(forecast, 1.0, config=config) == pytest.approx(2.0)


def test_conformal_quantile_is_monotone_as_coverage_increases() -> None:
    scores = tuple(float(value) for value in range(1, 31))

    q80 = finite_sample_conformal_quantile(scores, miscoverage=0.20)
    q90 = finite_sample_conformal_quantile(scores, miscoverage=0.10)

    assert q90 >= q80


def test_observation_rejects_nonfinite_actual_invalid_index_and_invalid_forecast() -> None:
    with pytest.raises(StateSpaceError):
        ConformalObservation(0, float("nan"), _Forecast(0.0))

    for bad_index in (-1, True, 1.0):
        with pytest.raises(StateSpaceError):
            ConformalObservation(bad_index, 0.0, _Forecast(0.0))

    with pytest.raises(StateSpaceError):
        ConformalObservation(0, 0.0, _Forecast(0.0, variance=0.0))

    with pytest.raises(StateSpaceError):
        ConformalObservation(0, 0.0, _Forecast(0.0, horizon=0))

    with pytest.raises(StateSpaceError):
        ConformalObservation(0, 0.0, object())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"miscoverage": 0.0},
        {"miscoverage": 1.0},
        {"miscoverage": True},
        {"min_calibration_size": 0},
        {"min_calibration_size": True},
        {"calibration_window": 3, "min_calibration_size": 4},
        {"calibration_window": True},
        {"normalized_scores": 1},
        {"adaptive": 1},
        {"adaptation_rate": -0.1},
        {"adaptation_rate": 1.1},
        {"min_miscoverage": 0.0},
        {"max_miscoverage": 1.0},
        {"min_miscoverage": 0.4, "max_miscoverage": 0.2},
        {"miscoverage": 0.1, "min_miscoverage": 0.2},
        {"min_scale": 0.0},
        {"min_scale": float("inf")},
    ],
)
def test_invalid_conformal_configuration_fails_closed(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(StateSpaceError):
        ConformalConfig(**kwargs)


def test_empty_observations_and_scores_fail_closed() -> None:
    with pytest.raises(StateSpaceError):
        evaluate_conformal_observations(())

    with pytest.raises(StateSpaceError):
        finite_sample_conformal_quantile((), miscoverage=0.1)


def test_interval_requires_enough_prior_scores() -> None:
    with pytest.raises(StateSpaceError):
        conformal_interval_from_scores(
            _Forecast(mean=0.0),
            (1.0, 2.0),
            target_index=3,
            miscoverage=0.1,
            config=ConformalConfig(min_calibration_size=4),
        )


def test_interval_rejects_invalid_target_index() -> None:
    for bad_index in (-1, True, 1.0):
        with pytest.raises(StateSpaceError):
            conformal_interval_from_scores(
                _Forecast(mean=0.0),
                tuple(float(index) for index in range(1, 10)),
                target_index=bad_index,
                miscoverage=0.1,
                config=ConformalConfig(min_calibration_size=4),
            )
