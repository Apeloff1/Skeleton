"""Fail-closed governance evidence for Jeeves stratified uncertainty.

This module evaluates calibration evidence only.  It does not activate models,
route forecasts, place orders, mutate learning state, or override higher-level
policy.  The resulting decision is an immutable evidence artifact that a
separate governance layer may consume.
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
    max_fallback_rate: float = 0.50
    min_evidenced_buckets: int = 1
    min_regime_buckets: int = 0
    min_bucket_uses: int = 5
    max_mean_width: float | None = None
    max_mean_interval_score: float | None = None

    def __post_init__(self) -> None:
        _positive_integer("min_scored_steps", self.min_scored_steps)
        _unit("max_absolute_coverage_gap", self.max_absolute_coverage_gap)
        _unit("max_bucket_coverage_gap", self.max_bucket_coverage_gap)
        _unit("max_fallback_rate", self.max_fallback_rate)
        _non_negative_integer("min_evidenced_buckets", self.min_evidenced_buckets)
        _non_negative_integer("min_regime_buckets", self.min_regime_buckets)
        _positive_integer("min_bucket_uses", self.min_bucket_uses)
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
    mean_width: float
    mean_interval_score: float
    fallback_rate: float
    evidenced_buckets: int
    evidenced_regime_buckets: int
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
    regime_evidenced = tuple(
        bucket for bucket in evidenced if bucket.key.is_regime_specific
    )
    bucket_gaps = tuple(
        abs(bucket.empirical_coverage - target)
        for bucket in evidenced
        if bucket.empirical_coverage is not None
    )
    worst_bucket_gap = max(bucket_gaps, default=1.0)

    reasons: list[str] = []
    if scored_steps < actual_gate.min_scored_steps:
        reasons.append("insufficient_conformal_steps")
    if absolute_gap > actual_gate.max_absolute_coverage_gap:
        reasons.append("global_conformal_coverage_gap_above_gate")
    if worst_bucket_gap > actual_gate.max_bucket_coverage_gap:
        reasons.append("bucket_conformal_coverage_gap_above_gate")
    if report.fallback_rate > actual_gate.max_fallback_rate:
        reasons.append("conformal_fallback_rate_above_gate")
    if len(evidenced) < actual_gate.min_evidenced_buckets:
        reasons.append("insufficient_evidenced_conformal_buckets")
    if len(regime_evidenced) < actual_gate.min_regime_buckets:
        reasons.append("insufficient_regime_conformal_buckets")
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

    fingerprint = _digest(
        {
            "schema": "jeeves.conformal-governance.v1",
            "report_fingerprint": report.fingerprint,
            "gate": {
                "min_scored_steps": actual_gate.min_scored_steps,
                "max_absolute_coverage_gap": actual_gate.max_absolute_coverage_gap,
                "max_bucket_coverage_gap": actual_gate.max_bucket_coverage_gap,
                "max_fallback_rate": actual_gate.max_fallback_rate,
                "min_evidenced_buckets": actual_gate.min_evidenced_buckets,
                "min_regime_buckets": actual_gate.min_regime_buckets,
                "min_bucket_uses": actual_gate.min_bucket_uses,
                "max_mean_width": actual_gate.max_mean_width,
                "max_mean_interval_score": actual_gate.max_mean_interval_score,
            },
            "eligible": eligible,
            "reasons": reasons,
            "scored_steps": scored_steps,
            "target_coverage": target,
            "empirical_coverage": report.empirical_coverage,
            "absolute_coverage_gap": absolute_gap,
            "worst_bucket_coverage_gap": worst_bucket_gap,
            "mean_width": report.mean_width,
            "mean_interval_score": report.mean_interval_score,
            "fallback_rate": report.fallback_rate,
            "evidenced_buckets": len(evidenced),
            "evidenced_regime_buckets": len(regime_evidenced),
        }
    )

    return ConformalGovernanceDecision(
        eligible=eligible,
        reasons=tuple(reasons),
        scored_steps=scored_steps,
        target_coverage=target,
        empirical_coverage=report.empirical_coverage,
        absolute_coverage_gap=absolute_gap,
        worst_bucket_coverage_gap=worst_bucket_gap,
        mean_width=report.mean_width,
        mean_interval_score=report.mean_interval_score,
        fallback_rate=report.fallback_rate,
        evidenced_buckets=len(evidenced),
        evidenced_regime_buckets=len(regime_evidenced),
        fingerprint=fingerprint,
    )


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
]
