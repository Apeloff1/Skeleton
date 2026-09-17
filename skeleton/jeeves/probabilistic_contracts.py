"""Fail-closed promotion contracts for Jeeves probabilistic modeling.

This module does not promote or route a model by itself. It translates numerical
validation evidence into an explicit eligibility decision that higher-level Jeeves
governance may consume.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .probabilistic_calibration import CalibrationReport
from .probabilistic_ensemble import BayesianEnsembleReport
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class ProbabilisticPromotionGate:
    """Minimum evidence required before a probabilistic candidate is eligible."""

    min_folds: int = 20
    min_calibration_score: float = 0.65
    max_coverage_gap: float = 0.15
    min_mean_log_score: float | None = None
    max_mean_crps: float | None = None
    max_drift_events_per_100: float = 5.0
    min_effective_model_count: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.min_folds, bool) or not isinstance(self.min_folds, int) or self.min_folds <= 0:
            raise StateSpaceError(
                "min_folds must be a positive integer",
                context={"reason": "invalid_promotion_gate", "field": "min_folds"},
            )
        _unit("min_calibration_score", self.min_calibration_score)
        _unit("max_coverage_gap", self.max_coverage_gap)
        if self.min_mean_log_score is not None:
            _finite("min_mean_log_score", self.min_mean_log_score)
        if self.max_mean_crps is not None and _finite("max_mean_crps", self.max_mean_crps) < 0.0:
            raise StateSpaceError(
                "max_mean_crps must be non-negative",
                context={"reason": "invalid_promotion_gate", "field": "max_mean_crps"},
            )
        if _finite("max_drift_events_per_100", self.max_drift_events_per_100) < 0.0:
            raise StateSpaceError(
                "max_drift_events_per_100 must be non-negative",
                context={"reason": "invalid_promotion_gate", "field": "max_drift_events_per_100"},
            )
        if _finite("min_effective_model_count", self.min_effective_model_count) < 1.0:
            raise StateSpaceError(
                "min_effective_model_count must be at least 1",
                context={"reason": "invalid_promotion_gate", "field": "min_effective_model_count"},
            )


@dataclass(frozen=True, slots=True)
class ProbabilisticPromotionDecision:
    eligible: bool
    reasons: tuple[str, ...]
    folds: int
    calibration_score: float
    worst_coverage_gap: float
    mean_log_score: float
    mean_crps: float
    drift_events_per_100: float
    average_effective_model_count: float
    fingerprint: str


def evaluate_probabilistic_promotion(
    ensemble: BayesianEnsembleReport,
    calibration: CalibrationReport,
    *,
    gate: ProbabilisticPromotionGate | None = None,
) -> ProbabilisticPromotionDecision:
    """Evaluate numerical evidence without mutating or activating anything."""

    actual_gate = gate or ProbabilisticPromotionGate()
    if calibration.observations != len(ensemble.steps):
        raise StateSpaceError(
            "ensemble and calibration evidence must cover equal fold counts",
            context={
                "reason": "evidence_count_mismatch",
                "ensemble_folds": len(ensemble.steps),
                "calibration_observations": calibration.observations,
            },
        )

    reasons: list[str] = []
    folds = len(ensemble.steps)
    worst_coverage_gap = max((item.absolute_gap for item in calibration.coverage), default=1.0)
    drift_events_per_100 = 100.0 * len(calibration.drift_events) / max(1, calibration.observations)
    effective_model_count = ensemble.average_effective_model_count

    if folds < actual_gate.min_folds:
        reasons.append("insufficient_folds")
    if calibration.calibration_score < actual_gate.min_calibration_score:
        reasons.append("calibration_score_below_gate")
    if worst_coverage_gap > actual_gate.max_coverage_gap:
        reasons.append("coverage_gap_above_gate")
    if actual_gate.min_mean_log_score is not None and ensemble.mean_log_score < actual_gate.min_mean_log_score:
        reasons.append("log_score_below_gate")
    if actual_gate.max_mean_crps is not None and ensemble.mean_crps > actual_gate.max_mean_crps:
        reasons.append("crps_above_gate")
    if drift_events_per_100 > actual_gate.max_drift_events_per_100:
        reasons.append("calibration_drift_above_gate")
    if effective_model_count < actual_gate.min_effective_model_count:
        reasons.append("ensemble_diversity_below_gate")

    eligible = not reasons
    if eligible:
        reasons.append("probabilistic_evidence_gate_passed")

    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-probabilistic-promotion-v1",
                ensemble.fingerprint,
                calibration.fingerprint,
                repr(actual_gate),
                str(eligible),
                ",".join(reasons),
                str(folds),
                format(calibration.calibration_score, ".17g"),
                format(worst_coverage_gap, ".17g"),
                format(ensemble.mean_log_score, ".17g"),
                format(ensemble.mean_crps, ".17g"),
                format(drift_events_per_100, ".17g"),
                format(effective_model_count, ".17g"),
            )
        ).encode("utf-8")
    ).hexdigest()

    return ProbabilisticPromotionDecision(
        eligible=eligible,
        reasons=tuple(reasons),
        folds=folds,
        calibration_score=calibration.calibration_score,
        worst_coverage_gap=worst_coverage_gap,
        mean_log_score=ensemble.mean_log_score,
        mean_crps=ensemble.mean_crps,
        drift_events_per_100=drift_events_per_100,
        average_effective_model_count=effective_model_count,
        fingerprint=fingerprint,
    )


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_promotion_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_promotion_gate", "field": name},
        )
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise StateSpaceError(
            f"{name} must be between 0 and 1",
            context={"reason": "invalid_promotion_gate", "field": name},
        )
    return number


__all__ = [
    "ProbabilisticPromotionDecision",
    "ProbabilisticPromotionGate",
    "evaluate_probabilistic_promotion",
]
