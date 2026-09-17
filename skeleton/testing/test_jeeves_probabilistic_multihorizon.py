from __future__ import annotations

import math
from dataclasses import dataclass, replace

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    ArbitratedForecast,
    CrossFamilyConfig,
    ExpertComponent,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_multihorizon import (
    MultiHorizonArbitrator,
    MultiHorizonConfig,
    conformalize_forecast_ladder,
    evaluate_multihorizon_conformal,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    horizon: int
    mean: float
    variance: float = 1.0

    def log_density(self, actual: float) -> float:
        error = actual - self.mean
        return -0.5 * (math.log(2.0 * math.pi * self.variance) + error * error / self.variance)


class _FakeArbitrator:
    experts = (ExpertKind.LOCAL_LEVEL, ExpertKind.SPECTRAL)
    config = CrossFamilyConfig(
        min_train_size=8,
        learning_rate=1.0,
        forgetting_factor=1.0,
        prior_strength=0.0,
        min_weight=1e-4,
        max_log_score_gap=20.0,
    )
    configuration_fingerprint = "fake-arbitrator-v1"

    def forecast(
        self,
        series: tuple[float, ...],
        *,
        horizon: int = 1,
        weights: dict[ExpertKind, float] | None = None,
    ) -> ArbitratedForecast:
        values = tuple(series)
        anchor = values[-1]
        actual_weights = weights or {
            ExpertKind.LOCAL_LEVEL: 0.5,
            ExpertKind.SPECTRAL: 0.5,
        }
        return ArbitratedForecast(
            horizon=horizon,
            components=(
                ExpertComponent(
                    expert=ExpertKind.LOCAL_LEVEL,
                    weight=actual_weights[ExpertKind.LOCAL_LEVEL],
                    predictive=_Forecast(horizon=horizon, mean=anchor),
                ),
                ExpertComponent(
                    expert=ExpertKind.SPECTRAL,
                    weight=actual_weights[ExpertKind.SPECTRAL],
                    predictive=_Forecast(horizon=horizon, mean=anchor + 3.0),
                ),
            ),
        )


def _engine(*, horizons: tuple[int, ...] = (1, 3)) -> MultiHorizonArbitrator:
    return MultiHorizonArbitrator(
        _FakeArbitrator(),
        config=MultiHorizonConfig(
            horizons=horizons,
            min_train_size=8,
            step=1,
        ),
    )


def _weight(step, expert: ExpertKind) -> float:
    return dict(step.prior_weights)[expert]


def test_config_rejects_duplicate_or_unsorted_horizons() -> None:
    with pytest.raises(StateSpaceError):
        MultiHorizonConfig(horizons=(1, 1, 3))
    with pytest.raises(StateSpaceError):
        MultiHorizonConfig(horizons=(3, 1))
    with pytest.raises(StateSpaceError):
        MultiHorizonConfig(horizons=(0, 1))


def test_long_horizon_weights_do_not_update_before_target_matures() -> None:
    report = _engine().evaluate((0.0,) * 28)
    horizon_three = report.report_for(3)
    by_origin = {step.origin_index: step for step in horizon_three.steps}

    # Forecasts issued at origins 8, 9 and 10 are all in flight before the
    # origin-8 / target-10 forecast can settle.  They must share the same prior.
    for origin in (8, 9, 10):
        assert _weight(by_origin[origin], ExpertKind.LOCAL_LEVEL) == pytest.approx(0.5)
        assert _weight(by_origin[origin], ExpertKind.SPECTRAL) == pytest.approx(0.5)

    # Settlement of target 10 occurs only after the origin-10 forecasts are
    # issued, so origin 11 is the first horizon-3 forecast allowed to learn it.
    assert _weight(by_origin[11], ExpertKind.LOCAL_LEVEL) > 0.5
    assert _weight(by_origin[11], ExpertKind.SPECTRAL) < 0.5


def test_horizon_states_learn_independently() -> None:
    report = _engine().evaluate((0.0,) * 28)
    horizon_one = {step.origin_index: step for step in report.report_for(1).steps}
    horizon_three = {step.origin_index: step for step in report.report_for(3).steps}

    # Horizon 1 has already observed target 8 before origin 9 is issued.
    assert _weight(horizon_one[9], ExpertKind.LOCAL_LEVEL) > 0.5

    # Horizon 3 has no matured evidence at origin 9 and must remain at prior.
    assert _weight(horizon_three[9], ExpertKind.LOCAL_LEVEL) == pytest.approx(0.5)


def test_suffix_mutation_cannot_rewrite_completed_horizon_evidence() -> None:
    engine = _engine()
    baseline = (0.0,) * 34
    mutated = baseline[:19] + (50.0,) * (len(baseline) - 19)

    left = engine.evaluate(baseline)
    right = engine.evaluate(mutated)

    for horizon in left.horizons:
        left_steps = [
            step for step in left.report_for(horizon).steps if step.target_index <= 18
        ]
        right_steps = [
            step for step in right.report_for(horizon).steps if step.target_index <= 18
        ]
        assert len(left_steps) == len(right_steps)
        for first, second in zip(left_steps, right_steps):
            assert first.origin_index == second.origin_index
            assert first.target_index == second.target_index
            assert first.actual == second.actual
            assert first.prior_weights == second.prior_weights
            assert first.posterior_weights == second.posterior_weights
            assert first.component_log_scores == second.component_log_scores
            assert first.predictive.mean == second.predictive.mean
            assert first.predictive.variance == second.predictive.variance
            assert first.mixture_log_score == second.mixture_log_score


def test_dependence_aligns_only_common_issue_origins() -> None:
    report = _engine(horizons=(1, 2, 4)).evaluate((0.0,) * 34)
    dependence = report.dependence

    assert dependence.horizons == (1, 2, 4)
    assert dependence.sample_size == len(report.report_for(4).steps)
    assert len(dependence.covariance) == 3
    assert all(len(row) == 3 for row in dependence.covariance)
    assert len(dependence.correlation) == 3
    assert all(len(row) == 3 for row in dependence.correlation)


def test_report_is_deterministic() -> None:
    engine = _engine(horizons=(1, 2, 3))
    values = tuple(0.1 * math.sin(index / 3.0) for index in range(36))

    first = engine.evaluate(values)
    second = engine.evaluate(values)

    assert first.configuration_fingerprint == second.configuration_fingerprint
    assert first.fingerprint == second.fingerprint
    assert tuple(item.fingerprint for item in first.horizon_reports) == tuple(
        item.fingerprint for item in second.horizon_reports
    )


def test_forecast_ladder_uses_each_horizons_final_weights() -> None:
    engine = _engine(horizons=(1, 3))
    values = (0.0,) * 30
    report = engine.evaluate(values)
    ladder = engine.forecast_from_report(values, report)

    assert ladder.origin_index == len(values)
    assert ladder.source_report_fingerprint == report.fingerprint
    for horizon in report.horizons:
        forecast = ladder.forecast_for(horizon)
        expected = dict(report.report_for(horizon).final_weights)
        actual = {component.expert: component.weight for component in forecast.components}
        assert actual == pytest.approx(expected)


def test_report_tampering_is_rejected_before_reuse() -> None:
    engine = _engine(horizons=(1, 3))
    values = (0.0,) * 30
    report = engine.evaluate(values)
    first = report.report_for(1)
    tampered_horizon = replace(
        first,
        final_weights=tuple(reversed(first.final_weights)),
    )
    tampered = replace(
        report,
        horizon_reports=(tampered_horizon, report.report_for(3)),
    )

    with pytest.raises(StateSpaceError):
        engine.forecast_from_report(values, tampered)


def test_multihorizon_conformal_uses_separate_calibration_streams() -> None:
    engine = _engine(horizons=(1, 3))
    values = tuple(0.05 * math.sin(index / 2.0) for index in range(38))
    report = engine.evaluate(values)
    conformal = evaluate_multihorizon_conformal(
        report,
        config=ConformalConfig(
            alpha=0.2,
            min_calibration=4,
            calibration_window=12,
            adaptive_rate=0.01,
            min_alpha=0.01,
            max_alpha=0.4,
            normalized=True,
        ),
    )

    assert tuple(item.horizon for item in conformal.horizons) == (1, 3)
    one = conformal.evidence_for(1).report
    three = conformal.evidence_for(3).report
    assert one.fingerprint != three.fingerprint
    assert one.steps[0].interval.horizon == 1
    assert three.steps[0].interval.horizon == 3


def test_conformal_ladder_targets_each_horizon_maturity_index() -> None:
    engine = _engine(horizons=(1, 3))
    values = tuple(0.05 * math.sin(index / 2.0) for index in range(38))
    report = engine.evaluate(values)
    evidence = evaluate_multihorizon_conformal(
        report,
        config=ConformalConfig(
            alpha=0.2,
            min_calibration=4,
            calibration_window=12,
            adaptive_rate=0.0,
            min_alpha=0.01,
            max_alpha=0.4,
            normalized=True,
        ),
    )
    ladder = engine.forecast_from_report(values, report)
    calibrated = conformalize_forecast_ladder(ladder, evidence)

    assert calibrated.interval_for(1).target_index == len(values)
    assert calibrated.interval_for(3).target_index == len(values) + 2
    assert calibrated.interval_for(1).horizon == 1
    assert calibrated.interval_for(3).horizon == 3


def test_conformal_evidence_rejects_forecast_ladder_from_different_report() -> None:
    engine = _engine(horizons=(1, 3))
    first_values = (0.0,) * 38
    second_values = tuple(0.02 * index for index in range(38))
    first_report = engine.evaluate(first_values)
    second_report = engine.evaluate(second_values)
    evidence = evaluate_multihorizon_conformal(
        first_report,
        config=ConformalConfig(
            alpha=0.2,
            min_calibration=4,
            calibration_window=12,
            adaptive_rate=0.0,
            min_alpha=0.01,
            max_alpha=0.4,
            normalized=True,
        ),
    )
    second_ladder = engine.forecast_from_report(second_values, second_report)

    with pytest.raises(StateSpaceError):
        conformalize_forecast_ladder(second_ladder, evidence)
