from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_conformal_stratified import (
    StratifiedConformalConfig,
    StratifiedForecastObservation,
    evaluate_stratified_conformal,
)
from skeleton.jeeves.probabilistic_governance import (
    ConformalGovernanceGate,
    evaluate_conformal_governance,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    mean: float = 0.0
    variance: float = 1.0
    horizon: int = 1


def _report(*, regimes: int, count: int = 60):
    observations = tuple(
        StratifiedForecastObservation(
            target_index=index,
            actual=1.0 + float((index - 1) % regimes),
            predictive=_Forecast(),
            regime=f"r{(index - 1) % regimes}",
        )
        for index in range(1, count + 1)
    )
    return evaluate_stratified_conformal(
        observations,
        config=StratifiedConformalConfig(
            conformal=ConformalConfig(
                alpha=0.20,
                min_calibration=4,
                calibration_window=32,
                adaptive_rate=0.0,
                min_alpha=0.05,
                max_alpha=0.45,
            ),
            condition_on_regime=True,
            fallback_to_horizon=True,
            max_regimes=16,
        ),
    )


def _gate(**kwargs: object) -> ConformalGovernanceGate:
    values: dict[str, object] = {
        "min_scored_steps": 1,
        "max_absolute_coverage_gap": 1.0,
        "max_bucket_coverage_gap": 1.0,
        "max_fallback_rate": 1.0,
        "max_unevidenced_step_rate": 1.0,
        "max_regime_switch_rate": None,
        "min_evidenced_buckets": 0,
        "min_regime_buckets": 0,
        "min_bucket_uses": 3,
    }
    values.update(kwargs)
    return ConformalGovernanceGate(**values)


def test_many_thin_regime_buckets_are_visible_as_unevidenced_step_mass() -> None:
    report = _report(regimes=10)
    decision = evaluate_conformal_governance(
        report,
        gate=_gate(max_unevidenced_step_rate=0.10),
    )

    assert decision.observed_regime_buckets == 10
    assert decision.unevidenced_step_rate > 0.10
    assert not decision.eligible
    assert "conformal_unevidenced_step_rate_above_gate" in decision.reasons


def test_regime_churn_is_measured_without_being_assumed_invalid() -> None:
    report = _report(regimes=10)
    permissive = evaluate_conformal_governance(report, gate=_gate())
    constrained = evaluate_conformal_governance(
        report,
        gate=_gate(max_regime_switch_rate=0.50),
    )

    assert permissive.regime_switch_rate == pytest.approx(1.0)
    assert permissive.eligible
    assert not constrained.eligible
    assert "conformal_regime_switch_rate_above_gate" in constrained.reasons


def test_stable_regime_has_zero_switch_rate() -> None:
    report = _report(regimes=1, count=30)
    decision = evaluate_conformal_governance(
        report,
        gate=_gate(max_regime_switch_rate=0.0, min_bucket_uses=1),
    )

    assert decision.regime_switch_rate == pytest.approx(0.0)
    assert decision.observed_regime_buckets == 1
    assert decision.eligible


def test_fragmentation_diagnostic_is_deterministic() -> None:
    report = _report(regimes=10)
    gate = _gate()

    left = evaluate_conformal_governance(report, gate=gate)
    right = evaluate_conformal_governance(report, gate=gate)

    assert left == right
    assert left.fingerprint == right.fingerprint


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_unevidenced_step_rate": -0.1},
        {"max_unevidenced_step_rate": 1.1},
        {"max_regime_switch_rate": -0.1},
        {"max_regime_switch_rate": 1.1},
    ],
)
def test_fragmentation_gate_configuration_fails_closed(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(StateSpaceError):
        _gate(**kwargs)
