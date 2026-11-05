"""Behavioral regression tests for hardware.thermal_throttle."""
from __future__ import annotations

import pytest

from skeleton.ai.assurance.operational_planes.policies.thermal_throttle import (
    IDENTITY, POLICY, PRIMARY_SIGNAL, SECONDARY_SIGNAL, admission_allowed,
    breach_example, evaluate, limits, nominal_example, required_signals,
)


def test_identity_and_required_metric_contract() -> None:
    assert POLICY.identity == IDENTITY
    assert len(POLICY.signals) == 2
    assert required_signals() == (PRIMARY_SIGNAL, SECONDARY_SIGNAL)
    assert set(limits()) == set(required_signals())


def test_complete_fresh_nominal_snapshot() -> None:
    observation = nominal_example()
    result = evaluate(observation, observed_at=1000, now=1050)
    assert result.status == "nominal"
    assert result.allowed
    assert result.violations == ()
    assert admission_allowed(observation, observed_at=1000, now=1050)


def test_primary_threshold_breach_blocks_admission() -> None:
    result = evaluate(breach_example(), observed_at=1000, now=1000)
    assert result.status == "blocked"
    assert result.reason == "threshold-breach"
    assert PRIMARY_SIGNAL in result.violations
    assert not result.allowed


def test_secondary_threshold_breach_blocks_admission() -> None:
    observation = nominal_example()
    observation[SECONDARY_SIGNAL] = int(POLICY.signals[1].maximum) + 1
    result = evaluate(observation, observed_at=1000, now=1000)
    assert result.reason == "threshold-breach"
    assert SECONDARY_SIGNAL in result.violations


def test_missing_measurements_are_not_inferred() -> None:
    result = evaluate({PRIMARY_SIGNAL: 0}, observed_at=1000, now=1000)
    assert result.reason == "missing-measurement"
    assert SECONDARY_SIGNAL in result.violations


@pytest.mark.parametrize("invalid", [True, None, "-1", "NaN", "Infinity", [], {}])
def test_invalid_values_fail_closed(invalid: object) -> None:
    observation = nominal_example()
    observation[PRIMARY_SIGNAL] = invalid
    result = evaluate(observation, observed_at=1000, now=1000)
    assert result.status == "blocked"
    assert result.reason == "invalid-measurement"


def test_stale_and_future_snapshots_fail_closed() -> None:
    observation = nominal_example()
    stale = evaluate(observation, observed_at=1000, now=1061)
    future = evaluate(observation, observed_at=1001, now=1000)
    assert stale.reason == "stale-observation"
    assert future.reason == "future-observation"


def test_clock_types_must_be_real_integers() -> None:
    observation = nominal_example()
    assert evaluate(observation, observed_at=True, now=1000).reason == "invalid-clock"
    assert evaluate(observation, observed_at=1000, now=1000.0).reason == "invalid-clock"


def test_unknown_fields_cannot_replace_missing_required_signal() -> None:
    observation = {PRIMARY_SIGNAL: 0, "unverified_metric": 0}
    result = evaluate(observation, observed_at=1000, now=1000)
    assert result.reason == "missing-measurement"
    assert not result.allowed
