"""Fail-closed governance evidence for Jeeves stratified uncertainty.

This module evaluates calibration evidence only. It does not activate models,
route forecasts, place orders, mutate learning state, or override higher-level
policy. Decisions retain their report and gate identities so downstream
composition can verify provenance rather than trusting an eligibility boolean.

Evidence is evaluated globally, by calibration bucket, and independently by
forecast horizon. Horizon aggregation is deliberately separate from regime
strata so regime fragmentation cannot hide systematic long- or short-horizon
miscalibration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .probabilistic_conformal_stratified import (
    StratifiedConformalReport,
    validate_stratified_conformal_report,
)
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class ConformalGovernanceGate:
    """Minimum calibration evidence required for governance eligibility."""

    min_scored_steps: int = 20
    max_absolute_coverage_gap: float = 0.15
    max_bucket_coverage_gap: float = 0.25
    max_horizon_coverage_gap: float = 0.25
    max_fallback_rate: float = 0.50
    max_unevidenced_step_rate: float = 0.25
    max_unevidenced_horizon_step_rate: float = 0.25
    max_regime_switch_rate: float | None = None
    min_evidenced_buckets: int = 1
    min_regime_buckets: int = 0
    min_bucket_uses: int = 5
    min_evidenced_horizons: int = 1
    min_horizon_steps: int = 5
    max_mean_width: float | None = None
    max_mean_interval_score: float | None = None

    def __post_init__(self) -> None:
        _positive_integer("min_scored_steps", self.min_scored_steps)
        _unit("max_absolute_coverage_gap", self.max_absolute_coverage_gap)
        _unit("max_bucket_coverage_gap", self.max_bucket_coverage_gap)
        _unit("max_horizon_coverage_gap", self.max_horizon_coverage_gap)
        _unit("max_fallback_rate", self.max_fallback_rate)
        _unit("max_unevidenced_step_rate", self.max_unevidenced_step_rate)
        _unit(
            "max_unevidenced_horizon_step_rate",
            self.max_unevidenced_horizon_step_rate,
        )
        if self.max_regime_switch_rate is not None:
            _unit("max_regime_switch_rate", self.max_regime_switch_rate)
        _non_negative_integer("min_evidenced_buckets", self.min_evidenced_buckets)
        _non_negative_integer("min_regime_buckets", self.min_regime_buckets)
        _positive_integer("min_bucket_uses", self.min_bucket_uses)
        _non_negative_integer("min_evidenced_horizons", self.min_evidenced_horizons)
        _positive_integer("min_horizon_steps", self.min_horizon_steps)
        if self.max_mean_width is not None:
            _non_negative("max_mean_width", self.max_mean_width)
        if self.max_mean_interval_score is not None:
            _non_negative("max_mean_interval_score", self.max_mean_interval_score)


@dataclass(frozen=True, slots=True)
class ConformalGovernanceDecision:
    """Auditable numerical evidence decision with no activation authority."""

    eligible: bool
    reasons: tuple[str, ...]
    scored_steps: int
    target_coverage: float
    empirical_coverage: float
    absolute_coverage_gap: float
    worst_bucket_coverage_gap: float
    worst_horizon_coverage_gap: float
    mean_width: float
    mean_interval_score: float
    fallback_rate: float
    unevidenced_step_rate: float
    unevidenced_horizon_step_rate: float
    regime_switch_rate: float
    evidenced_buckets: int
    evidenced_regime_buckets: int
    observed_regime_buckets: int
    evidenced_horizons: int
    observed_horizons: int
    report_fingerprint: str
    gate_fingerprint: str
    fingerprint: str


def evaluate_conformal_governance(
    report: StratifiedConformalReport,
    *,
    gate: ConformalGovernanceGate | None = None,
) -> ConformalGovernanceDecision:
    """Evaluate stratified conformal evidence without activating anything."""

    actual_gate = gate or ConformalGovernanceGate()
    validate_stratified_conformal_report(report)

    scored_steps = len(report.steps)
    target = report.target_coverage
    absolute_gap = abs(report.empirical_coverage - target)
    evidenced = tuple(
        bucket
        for bucket in report.buckets
        if bucket.issued_intervals >= actual_gate.min_bucket_uses
    )
    evidenced_keys = {bucket.key for bucket in evidenced}
    regime_evidenced = tuple(
        bucket for bucket in evidenced if bucket.key.is_regime_specific
    )
    observed_regime_buckets = sum(
        1 for bucket in report.buckets if bucket.key.is_regime_specific
    )
    bucket_gaps = tuple(
        abs(bucket.empirical_coverage - target)
        for bucket in evidenced
        if bucket.empirical_coverage is not None
    )
    worst_bucket_gap = max(bucket_gaps, default=1.0)
    unevidenced_steps = sum(
        1 for step in report.steps if step.stratum not in evidenced_keys
    )
    unevidenced_step_rate = unevidenced_steps / max(1, scored_steps)

    horizon_counts: dict[int, int] = {}
    horizon_misses: dict[int, int] = {}
    for step in report.steps:
        horizon = step.interval.horizon
        horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1
        horizon_misses[horizon] = horizon_misses.get(horizon, 0) + int(step.missed)
    evidenced_horizon_keys = {
        horizon
        for horizon, count in horizon_counts.items()
        if count >= actual_gate.min_horizon_steps
    }
    horizon_gaps = tuple(
        abs((1.0 - horizon_misses[horizon] / horizon_counts[horizon]) - target)
        for horizon in sorted(evidenced_horizon_keys)
    )
    worst_horizon_gap = max(horizon_gaps, default=1.0)
    unevidenced_horizon_steps = sum(
        count
        for horizon, count in horizon_counts.items()
        if horizon not in evidenced_horizon_keys
    )
    unevidenced_horizon_step_rate = unevidenced_horizon_steps / max(1, scored_steps)
    regime_switch_rate = _regime_switch_rate(report)

    reasons: list[str] = []
    if scored_steps < actual_gate.min_scored_steps:
        reasons.append("insufficient_conformal_steps")
    if absolute_gap > actual_gate.max_absolute_coverage_gap:
        reasons.append("global_conformal_coverage_gap_above_gate")
    if worst_bucket_gap > actual_gate.max_bucket_coverage_gap:
        reasons.append("bucket_conformal_coverage_gap_above_gate")
    if worst_horizon_gap > actual_gate.max_horizon_coverage_gap:
        reasons.append("horizon_conformal_coverage_gap_above_gate")
    if report.fallback_rate > actual_gate.max_fallback_rate:
        reasons.append("conformal_fallback_rate_above_gate")
    if unevidenced_step_rate > actual_gate.max_unevidenced_step_rate:
        reasons.append("conformal_unevidenced_step_rate_above_gate")
    if (
        unevidenced_horizon_step_rate
        > actual_gate.max_unevidenced_horizon_step_rate
    ):
        reasons.append("conformal_unevidenced_horizon_step_rate_above_gate")
    if (
        actual_gate.max_regime_switch_rate is not None
        and regime_switch_rate > actual_gate.max_regime_switch_rate
    ):
        reasons.append("conformal_regime_switch_rate_above_gate")
    if len(evidenced) < actual_gate.min_evidenced_buckets:
        reasons.append("insufficient_evidenced_conformal_buckets")
    if len(regime_evidenced) < actual_gate.min_regime_buckets:
        reasons.append("insufficient_regime_conformal_buckets")
    if len(evidenced_horizon_keys) < actual_gate.min_evidenced_horizons:
        reasons.append("insufficient_evidenced_conformal_horizons")
    if (
        actual_gate.max_mean_width is not None
        and report.mean_width > actual_gate.max_mean_width
    ):
        reasons.append("conformal_mean_width_above_gate")
    if (
        actual_gate.max_mean_interval_score is not None
        and report.mean_interval_score > actual_gate.max_mean_interval_score
    ):
        reasons.append("conformal_interval_score_above_gate")

    eligible = not reasons
    if eligible:
        reasons.append("conformal_evidence_gate_passed")

    gate_fingerprint = _gate_fingerprint(actual_gate)
    fingerprint = _decision_fingerprint(
        eligible=eligible,
        reasons=tuple(reasons),
        scored_steps=scored_steps,
        target_coverage=target,
        empirical_coverage=report.empirical_coverage,
        absolute_coverage_gap=absolute_gap,
        worst_bucket_coverage_gap=worst_bucket_gap,
        worst_horizon_coverage_gap=worst_horizon_gap,
        mean_width=report.mean_width,
        mean_interval_score=report.mean_interval_score,
        fallback_rate=report.fallback_rate,
        unevidenced_step_rate=unevidenced_step_rate,
        unevidenced_horizon_step_rate=unevidenced_horizon_step_rate,
        regime_switch_rate=regime_switch_rate,
        evidenced_buckets=len(evidenced),
        evidenced_regime_buckets=len(regime_evidenced),
        observed_regime_buckets=observed_regime_buckets,
        evidenced_horizons=len(evidenced_horizon_keys),
        observed_horizons=len(horizon_counts),
        report_fingerprint=report.fingerprint,
        gate_fingerprint=gate_fingerprint,
    )

    return ConformalGovernanceDecision(
        eligible=eligible,
        reasons=tuple(reasons),
        scored_steps=scored_steps,
        target_coverage=target,
        empirical_coverage=report.empirical_coverage,
        absolute_coverage_gap=absolute_gap,
        worst_bucket_coverage_gap=worst_bucket_gap,
        worst_horizon_coverage_gap=worst_horizon_gap,
        mean_width=report.mean_width,
        mean_interval_score=report.mean_interval_score,
        fallback_rate=report.fallback_rate,
        unevidenced_step_rate=unevidenced_step_rate,
        unevidenced_horizon_step_rate=unevidenced_horizon_step_rate,
        regime_switch_rate=regime_switch_rate,
        evidenced_buckets=len(evidenced),
        evidenced_regime_buckets=len(regime_evidenced),
        observed_regime_buckets=observed_regime_buckets,
        evidenced_horizons=len(evidenced_horizon_keys),
        observed_horizons=len(horizon_counts),
        report_fingerprint=report.fingerprint,
        gate_fingerprint=gate_fingerprint,
        fingerprint=fingerprint,
    )


def validate_conformal_governance_decision(
    decision: ConformalGovernanceDecision,
) -> None:
    """Reject a malformed or tampered conformal governance artifact."""

    if not isinstance(decision, ConformalGovernanceDecision):
        raise StateSpaceError(
            "decision must be a ConformalGovernanceDecision",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    if not isinstance(decision.eligible, bool):
        raise StateSpaceError(
            "eligible must be a boolean",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    _positive_integer("scored_steps", decision.scored_steps)
    _unit("target_coverage", decision.target_coverage)
    _unit("empirical_coverage", decision.empirical_coverage)
    _unit("absolute_coverage_gap", decision.absolute_coverage_gap)
    _unit("worst_bucket_coverage_gap", decision.worst_bucket_coverage_gap)
    _unit("worst_horizon_coverage_gap", decision.worst_horizon_coverage_gap)
    _non_negative("mean_width", decision.mean_width)
    _non_negative("mean_interval_score", decision.mean_interval_score)
    _unit("fallback_rate", decision.fallback_rate)
    _unit("unevidenced_step_rate", decision.unevidenced_step_rate)
    _unit(
        "unevidenced_horizon_step_rate",
        decision.unevidenced_horizon_step_rate,
    )
    _unit("regime_switch_rate", decision.regime_switch_rate)
    _non_negative_integer("evidenced_buckets", decision.evidenced_buckets)
    _non_negative_integer(
        "evidenced_regime_buckets",
        decision.evidenced_regime_buckets,
    )
    _non_negative_integer("observed_regime_buckets", decision.observed_regime_buckets)
    _non_negative_integer("evidenced_horizons", decision.evidenced_horizons)
    _positive_integer("observed_horizons", decision.observed_horizons)
    if decision.evidenced_regime_buckets > decision.evidenced_buckets:
        raise StateSpaceError(
            "regime evidenced buckets cannot exceed total evidenced buckets",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    if decision.evidenced_regime_buckets > decision.observed_regime_buckets:
        raise StateSpaceError(
            "evidenced regime buckets cannot exceed observed regime buckets",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    if decision.evidenced_horizons > decision.observed_horizons:
        raise StateSpaceError(
            "evidenced horizons cannot exceed observed horizons",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    recomputed_gap = abs(decision.empirical_coverage - decision.target_coverage)
    if abs(recomputed_gap - decision.absolute_coverage_gap) > 1e-12:
        raise StateSpaceError(
            "coverage gap disagrees with coverage values",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    _validate_reasons(decision.reasons, eligible=decision.eligible)
    for name, value in (
        ("report_fingerprint", decision.report_fingerprint),
        ("gate_fingerprint", decision.gate_fingerprint),
        ("fingerprint", decision.fingerprint),
    ):
        _validate_digest(name, value)

    expected = _decision_fingerprint(
        eligible=decision.eligible,
        reasons=decision.reasons,
        scored_steps=decision.scored_steps,
        target_coverage=decision.target_coverage,
        empirical_coverage=decision.empirical_coverage,
        absolute_coverage_gap=decision.absolute_coverage_gap,
        worst_bucket_coverage_gap=decision.worst_bucket_coverage_gap,
        worst_horizon_coverage_gap=decision.worst_horizon_coverage_gap,
        mean_width=decision.mean_width,
        mean_interval_score=decision.mean_interval_score,
        fallback_rate=decision.fallback_rate,
        unevidenced_step_rate=decision.unevidenced_step_rate,
        unevidenced_horizon_step_rate=decision.unevidenced_horizon_step_rate,
        regime_switch_rate=decision.regime_switch_rate,
        evidenced_buckets=decision.evidenced_buckets,
        evidenced_regime_buckets=decision.evidenced_regime_buckets,
        observed_regime_buckets=decision.observed_regime_buckets,
        evidenced_horizons=decision.evidenced_horizons,
        observed_horizons=decision.observed_horizons,
        report_fingerprint=decision.report_fingerprint,
        gate_fingerprint=decision.gate_fingerprint,
    )
    if decision.fingerprint != expected:
        raise StateSpaceError(
            "conformal governance decision fingerprint mismatch",
            context={"reason": "conformal_governance_identity_mismatch"},
        )


def _gate_fingerprint(gate: ConformalGovernanceGate) -> str:
    return _digest(
        {
            "schema": "jeeves.conformal-governance-gate.v4",
            "min_scored_steps": gate.min_scored_steps,
            "max_absolute_coverage_gap": gate.max_absolute_coverage_gap,
            "max_bucket_coverage_gap": gate.max_bucket_coverage_gap,
            "max_horizon_coverage_gap": gate.max_horizon_coverage_gap,
            "max_fallback_rate": gate.max_fallback_rate,
            "max_unevidenced_step_rate": gate.max_unevidenced_step_rate,
            "max_unevidenced_horizon_step_rate": gate.max_unevidenced_horizon_step_rate,
            "max_regime_switch_rate": gate.max_regime_switch_rate,
            "min_evidenced_buckets": gate.min_evidenced_buckets,
            "min_regime_buckets": gate.min_regime_buckets,
            "min_bucket_uses": gate.min_bucket_uses,
            "min_evidenced_horizons": gate.min_evidenced_horizons,
            "min_horizon_steps": gate.min_horizon_steps,
            "max_mean_width": gate.max_mean_width,
            "max_mean_interval_score": gate.max_mean_interval_score,
        }
    )


def _decision_fingerprint(
    *,
    eligible: bool,
    reasons: tuple[str, ...],
    scored_steps: int,
    target_coverage: float,
    empirical_coverage: float,
    absolute_coverage_gap: float,
    worst_bucket_coverage_gap: float,
    worst_horizon_coverage_gap: float,
    mean_width: float,
    mean_interval_score: float,
    fallback_rate: float,
    unevidenced_step_rate: float,
    unevidenced_horizon_step_rate: float,
    regime_switch_rate: float,
    evidenced_buckets: int,
    evidenced_regime_buckets: int,
    observed_regime_buckets: int,
    evidenced_horizons: int,
    observed_horizons: int,
    report_fingerprint: str,
    gate_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.conformal-governance-decision.v4",
            "eligible": eligible,
            "reasons": list(reasons),
            "scored_steps": scored_steps,
            "target_coverage": target_coverage,
            "empirical_coverage": empirical_coverage,
            "absolute_coverage_gap": absolute_coverage_gap,
            "worst_bucket_coverage_gap": worst_bucket_coverage_gap,
            "worst_horizon_coverage_gap": worst_horizon_coverage_gap,
            "mean_width": mean_width,
            "mean_interval_score": mean_interval_score,
            "fallback_rate": fallback_rate,
            "unevidenced_step_rate": unevidenced_step_rate,
            "unevidenced_horizon_step_rate": unevidenced_horizon_step_rate,
            "regime_switch_rate": regime_switch_rate,
            "evidenced_buckets": evidenced_buckets,
            "evidenced_regime_buckets": evidenced_regime_buckets,
            "observed_regime_buckets": observed_regime_buckets,
            "evidenced_horizons": evidenced_horizons,
            "observed_horizons": observed_horizons,
            "report_fingerprint": report_fingerprint,
            "gate_fingerprint": gate_fingerprint,
        }
    )


def _validate_reasons(reasons: tuple[str, ...], *, eligible: bool) -> None:
    if not isinstance(reasons, tuple) or not reasons:
        raise StateSpaceError(
            "reasons must be a non-empty tuple",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        raise StateSpaceError(
            "reasons must contain non-empty strings",
            context={"reason": "invalid_conformal_governance_decision"},
        )
    passed = "conformal_evidence_gate_passed" in reasons
    if eligible != passed or (passed and len(reasons) != 1):
        raise StateSpaceError(
            "conformal reasons disagree with eligibility",
            context={"reason": "invalid_conformal_governance_decision"},
        )


def _validate_digest(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_conformal_governance_decision"},
        )


def _regime_switch_rate(report: StratifiedConformalReport) -> float:
    regimes = tuple(
        step.requested_regime
        for step in report.steps
        if step.requested_regime is not None
    )
    if len(regimes) < 2:
        return 0.0
    switches = sum(left != right for left, right in zip(regimes, regimes[1:]))
    return switches / (len(regimes) - 1)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    return number


def _non_negative(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise StateSpaceError(
            f"{name} must lie in [0, 1]",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    return number


def _positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateSpaceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    return value


def _non_negative_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StateSpaceError(
            f"{name} must be a non-negative integer",
            context={"reason": "invalid_conformal_governance_gate", "field": name},
        )
    return value


__all__ = [
    "ConformalGovernanceDecision",
    "ConformalGovernanceGate",
    "evaluate_conformal_governance",
    "validate_conformal_governance_decision",
]
