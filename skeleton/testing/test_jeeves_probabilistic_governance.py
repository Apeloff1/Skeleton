from __future__ import annotations

from dataclasses import dataclass, replace

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
    validate_conformal_governance_decision,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class _Forecast:
    mean: float = 0.0
    variance: float = 1.0
    horizon: int = 1


def _report(count: int = 30):
    observations = []
    for index in range(1, count + 1):
        calm = index % 2 == 1
        observations.append(
            StratifiedForecastObservation(
                target_index=index,
                actual=1.0 if calm else 2.0,
                predictive=_Forecast(),
                regime="calm" if calm else "volatile",
            )
        )
    return evaluate_stratified_conformal(
        tuple(observations),
        config=StratifiedConformalConfig(
            conformal=ConformalConfig(
                alpha=0.20,
                min_calibration=4,
                calibration_window=20,
                adaptive_rate=0.0,
                min_alpha=0.05,
                max_alpha=0.45,
            ),
            condition_on_regime=True,
            fallback_to_horizon=True,
        ),
    )


def _permissive_gate(**kwargs: object) -> ConformalGovernanceGate:
    values: dict[str, object] = {
        "min_scored_steps": 1,
        "max_absolute_coverage_gap": 1.0,
        "max_bucket_coverage_gap": 1.0,
        "max_horizon_coverage_gap": 1.0,
        "max_fallback_rate": 1.0,
        "max_unevidenced_step_rate": 1.0,
        "max_unevidenced_horizon_step_rate": 1.0,
        "min_evidenced_buckets": 1,
        "min_regime_buckets": 1,
        "min_bucket_uses": 1,
        "min_evidenced_horizons": 1,
        "min_horizon_steps": 1,
    }
    values.update(kwargs)
    return ConformalGovernanceGate(**values)


def test_permissive_governance_gate_can_mark_evidence_eligible() -> None:
    report = _report()
    decision = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(),
    )

    assert decision.eligible
    assert decision.reasons == ("conformal_evidence_gate_passed",)
    assert decision.scored_steps == len(report.steps)
    assert decision.evidenced_regime_buckets >= 2
    assert decision.evidenced_horizons == 1
    assert decision.observed_horizons == 1
    validate_conformal_governance_decision(decision)


def test_governance_decision_is_deterministic() -> None:
    report = _report()
    gate = _permissive_gate()

    left = evaluate_conformal_governance(report, gate=gate)
    right = evaluate_conformal_governance(report, gate=gate)

    assert left == right
    assert left.fingerprint == right.fingerprint


def test_step_floor_can_veto_thin_evidence() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(min_scored_steps=1000),
    )

    assert not decision.eligible
    assert "insufficient_conformal_steps" in decision.reasons


def test_global_coverage_gap_can_veto() -> None:
    report = _report()
    assert abs(report.coverage_gap) > 0.0

    decision = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(max_absolute_coverage_gap=0.0),
    )

    assert not decision.eligible
    assert "global_conformal_coverage_gap_above_gate" in decision.reasons


def test_bucket_coverage_gap_can_veto() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(max_bucket_coverage_gap=0.0),
    )

    assert not decision.eligible
    assert "bucket_conformal_coverage_gap_above_gate" in decision.reasons


def test_horizon_coverage_gap_can_veto() -> None:
    report = _report()
    permissive = evaluate_conformal_governance(report, gate=_permissive_gate())
    assert permissive.worst_horizon_coverage_gap > 0.0

    decision = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(max_horizon_coverage_gap=0.0),
    )

    assert not decision.eligible
    assert "horizon_conformal_coverage_gap_above_gate" in decision.reasons


def test_horizon_evidence_depth_can_veto() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(
            min_horizon_steps=1000,
            min_evidenced_horizons=1,
            max_unevidenced_horizon_step_rate=1.0,
        ),
    )

    assert not decision.eligible
    assert "insufficient_evidenced_conformal_horizons" in decision.reasons


def test_unevidenced_horizon_mass_can_veto() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(
            min_horizon_steps=1000,
            min_evidenced_horizons=0,
            max_unevidenced_horizon_step_rate=0.0,
        ),
    )

    assert not decision.eligible
    assert "conformal_unevidenced_horizon_step_rate_above_gate" in decision.reasons


def test_fallback_rate_can_veto() -> None:
    report = _report()
    assert report.fallback_rate > 0.0

    decision = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(max_fallback_rate=0.0),
    )

    assert not decision.eligible
    assert "conformal_fallback_rate_above_gate" in decision.reasons


def test_regime_bucket_evidence_can_be_required() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(min_regime_buckets=3),
    )

    assert not decision.eligible
    assert "insufficient_regime_conformal_buckets" in decision.reasons


def test_bucket_use_floor_can_remove_thin_buckets_from_evidence() -> None:
    decision = evaluate_conformal_governance(
        _report(),
        gate=_permissive_gate(
            min_bucket_uses=100,
            min_evidenced_buckets=1,
            min_regime_buckets=0,
        ),
    )

    assert not decision.eligible
    assert "insufficient_evidenced_conformal_buckets" in decision.reasons


def test_width_and_interval_score_caps_can_veto() -> None:
    report = _report()
    assert report.mean_width > 0.0
    assert report.mean_interval_score > 0.0

    width = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(max_mean_width=report.mean_width - 1e-9),
    )
    score = evaluate_conformal_governance(
        report,
        gate=_permissive_gate(
            max_mean_interval_score=report.mean_interval_score - 1e-9
        ),
    )

    assert not width.eligible
    assert "conformal_mean_width_above_gate" in width.reasons
    assert not score.eligible
    assert "conformal_interval_score_above_gate" in score.reasons


def test_governance_rejects_tampered_report_before_scoring_gate() -> None:
    report = _report()
    first = report.buckets[0]
    tampered = replace(
        report,
        buckets=(replace(first, misses=first.issued_intervals),) + report.buckets[1:],
    )

    with pytest.raises(StateSpaceError):
        evaluate_conformal_governance(tampered, gate=_permissive_gate())


def test_governance_rejects_tampered_decision() -> None:
    decision = evaluate_conformal_governance(_report(), gate=_permissive_gate())
    tampered = replace(
        decision,
        worst_horizon_coverage_gap=min(
            1.0,
            decision.worst_horizon_coverage_gap + 0.1,
        ),
    )

    with pytest.raises(StateSpaceError):
        validate_conformal_governance_decision(tampered)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_scored_steps": 0},
        {"max_absolute_coverage_gap": -0.1},
        {"max_bucket_coverage_gap": 1.1},
        {"max_horizon_coverage_gap": 1.1},
        {"max_fallback_rate": -0.1},
        {"max_unevidenced_horizon_step_rate": 1.1},
        {"min_evidenced_buckets": -1},
        {"min_regime_buckets": -1},
        {"min_bucket_uses": 0},
        {"min_evidenced_horizons": -1},
        {"min_horizon_steps": 0},
        {"max_mean_width": -1.0},
        {"max_mean_interval_score": -1.0},
    ],
)
def test_invalid_governance_gate_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(StateSpaceError):
        _permissive_gate(**kwargs)
