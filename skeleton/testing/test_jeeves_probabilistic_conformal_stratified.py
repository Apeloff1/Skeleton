from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_conformal_stratified import (
    ConformalStratumKey,
    StratifiedConformalConfig,
    StratifiedForecastObservation,
    conformalize_next_stratified_forecast,
    evaluate_stratified_conformal,
    validate_stratified_conformal_report,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    mean: float = 0.0
    variance: float = 1.0
    horizon: int = 1


def _base_config(**kwargs: object) -> ConformalConfig:
    values: dict[str, object] = {
        "alpha": 0.20,
        "min_calibration": 4,
        "calibration_window": 12,
        "adaptive_rate": 0.0,
        "min_alpha": 0.05,
        "max_alpha": 0.45,
    }
    values.update(kwargs)
    return ConformalConfig(**values)


def _stratified_config(**kwargs: object) -> StratifiedConformalConfig:
    values: dict[str, object] = {
        "conformal": _base_config(),
        "condition_on_regime": True,
        "fallback_to_horizon": True,
        "max_regimes": 8,
    }
    values.update(kwargs)
    return StratifiedConformalConfig(**values)


def _regime_observations(
    suffix: tuple[float, ...] = (),
) -> tuple[StratifiedForecastObservation, ...]:
    base = (0.1, 1.0, 0.2, 1.1, 0.3, 1.2, 0.4, 1.3, 0.5, 1.4)
    values = base + suffix
    result = []
    for index, value in enumerate(values, start=1):
        regime = "calm" if index % 2 else "volatile"
        result.append(
            StratifiedForecastObservation(
                target_index=index,
                actual=value,
                predictive=_Forecast(horizon=1),
                regime=regime,
            )
        )
    return tuple(result)


def test_horizons_keep_independent_calibration_sequences() -> None:
    values = (0.1, 10.0, 0.2, 20.0, 0.3, 30.0, 0.4, 40.0, 0.5, 50.0)
    observations = tuple(
        StratifiedForecastObservation(
            target_index=index,
            actual=value,
            predictive=_Forecast(horizon=1 if index % 2 else 2),
        )
        for index, value in enumerate(values, start=1)
    )
    report = evaluate_stratified_conformal(
        observations,
        config=_stratified_config(condition_on_regime=False),
    )

    assert [step.interval.target_index for step in report.steps] == [9, 10]
    assert report.steps[0].stratum == ConformalStratumKey(horizon=1)
    assert report.steps[1].stratum == ConformalStratumKey(horizon=2)
    assert report.steps[0].interval.quantile == pytest.approx(0.4)
    assert report.steps[1].interval.quantile == pytest.approx(40.0)
    assert report.steps[0].interval.calibration_size == 4
    assert report.steps[1].interval.calibration_size == 4


def test_regime_conditioning_falls_back_then_promotes_to_fine_bucket() -> None:
    report = evaluate_stratified_conformal(
        _regime_observations(),
        config=_stratified_config(),
    )

    assert [step.interval.target_index for step in report.steps] == [5, 6, 7, 8, 9, 10]
    assert all(step.used_fallback for step in report.steps[:4])
    assert not report.steps[4].used_fallback
    assert not report.steps[5].used_fallback
    assert report.steps[4].stratum.regime == "calm"
    assert report.steps[5].stratum.regime == "volatile"
    assert report.fallback_rate == pytest.approx(4.0 / 6.0)

    horizon = report.bucket(horizon=1)
    calm = report.bucket(horizon=1, regime="calm")
    volatile = report.bucket(horizon=1, regime="volatile")
    assert horizon.issued_intervals == 4
    assert calm.issued_intervals == 1
    assert volatile.issued_intervals == 1


def test_target_score_enters_fine_bucket_only_after_target_interval() -> None:
    observations = _regime_observations()
    report = evaluate_stratified_conformal(
        observations,
        config=_stratified_config(),
    )

    first_calm = next(
        step
        for step in report.steps
        if step.stratum.regime == "calm"
    )
    assert first_calm.interval.target_index == 9
    assert first_calm.interval.calibration_size == 4
    assert first_calm.interval.quantile == pytest.approx(0.4)
    assert first_calm.nonconformity_score == pytest.approx(0.5)


def test_future_suffix_mutation_cannot_change_completed_stratified_steps() -> None:
    left = evaluate_stratified_conformal(
        _regime_observations((100.0, 101.0, 102.0, 103.0)),
        config=_stratified_config(),
    )
    right = evaluate_stratified_conformal(
        _regime_observations((-100.0, -101.0, -102.0, -103.0)),
        config=_stratified_config(),
    )

    left_prefix = tuple(step for step in left.steps if step.interval.target_index <= 10)
    right_prefix = tuple(step for step in right.steps if step.interval.target_index <= 10)
    assert left_prefix == right_prefix


def test_next_forecast_prefers_regime_bucket_and_can_fallback_for_new_regime() -> None:
    report = evaluate_stratified_conformal(
        _regime_observations(),
        config=_stratified_config(),
    )

    known = conformalize_next_stratified_forecast(
        _Forecast(horizon=1),
        report,
        target_index=20,
        regime="calm",
    )
    novel = conformalize_next_stratified_forecast(
        _Forecast(horizon=1),
        report,
        target_index=21,
        regime="new-regime",
    )

    assert known.stratum == ConformalStratumKey(horizon=1, regime="calm")
    assert not known.used_fallback
    assert novel.stratum == ConformalStratumKey(horizon=1)
    assert novel.used_fallback


def test_next_forecast_rejects_unknown_horizon_without_calibration() -> None:
    report = evaluate_stratified_conformal(
        _regime_observations(),
        config=_stratified_config(),
    )

    with pytest.raises(StateSpaceError):
        conformalize_next_stratified_forecast(
            _Forecast(horizon=9),
            report,
            target_index=20,
            regime="calm",
        )


def test_report_validation_rejects_tampered_bucket_state() -> None:
    report = evaluate_stratified_conformal(
        _regime_observations(),
        config=_stratified_config(),
    )
    first = report.buckets[0]
    tampered_bucket = replace(
        first,
        calibration_scores=first.calibration_scores[:-1] + (99.0,),
    )
    tampered = replace(report, buckets=(tampered_bucket,) + report.buckets[1:])

    with pytest.raises(StateSpaceError):
        validate_stratified_conformal_report(tampered)
    with pytest.raises(StateSpaceError):
        conformalize_next_stratified_forecast(
            _Forecast(horizon=1),
            tampered,
            target_index=30,
            regime="calm",
        )


def test_report_is_deterministic_and_integrity_validates() -> None:
    config = _stratified_config()
    left = evaluate_stratified_conformal(_regime_observations(), config=config)
    right = evaluate_stratified_conformal(_regime_observations(), config=config)

    assert left == right
    assert left.fingerprint == right.fingerprint
    validate_stratified_conformal_report(left)


def test_conditioning_disabled_ignores_supplied_regime_without_fallback_accounting() -> None:
    observations = _regime_observations()
    report = evaluate_stratified_conformal(
        observations,
        config=_stratified_config(condition_on_regime=False),
    )

    assert report.fallback_rate == pytest.approx(0.0)
    assert all(step.stratum.regime is None for step in report.steps)
    assert all(step.requested_regime is None for step in report.steps)


def test_missing_regime_fails_when_fallback_is_disabled() -> None:
    observations = tuple(
        StratifiedForecastObservation(
            target_index=index,
            actual=float(index),
            predictive=_Forecast(),
        )
        for index in range(1, 7)
    )

    with pytest.raises(StateSpaceError):
        evaluate_stratified_conformal(
            observations,
            config=_stratified_config(fallback_to_horizon=False),
        )


def test_regime_cardinality_is_bounded() -> None:
    observations = tuple(
        StratifiedForecastObservation(
            target_index=index,
            actual=float(index),
            predictive=_Forecast(),
            regime=f"r{index}",
        )
        for index in range(1, 8)
    )

    with pytest.raises(StateSpaceError):
        evaluate_stratified_conformal(
            observations,
            config=_stratified_config(max_regimes=3),
        )


def test_non_monotonic_targets_fail_closed() -> None:
    observations = (
        StratifiedForecastObservation(1, 0.1, _Forecast(), "calm"),
        StratifiedForecastObservation(2, 0.2, _Forecast(), "calm"),
        StratifiedForecastObservation(3, 0.3, _Forecast(), "calm"),
        StratifiedForecastObservation(4, 0.4, _Forecast(), "calm"),
        StratifiedForecastObservation(4, 0.5, _Forecast(), "calm"),
    )

    with pytest.raises(StateSpaceError):
        evaluate_stratified_conformal(observations, config=_stratified_config())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"condition_on_regime": 1},
        {"fallback_to_horizon": 1},
        {"max_regimes": 0},
    ],
)
def test_invalid_stratified_configuration_fails_closed(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(StateSpaceError):
        _stratified_config(**kwargs)
