"""Fail-closed promotion contracts for Jeeves probabilistic modeling.

This module does not promote or route a model by itself. It translates numerical
validation evidence into an explicit eligibility decision that higher-level Jeeves
governance may consume. Decisions retain source and policy identities so they can
be independently integrity-checked downstream.

Promotion requires exact evidence identity between the ensemble backtest and its
calibration report: target indices, realized values, predictive mixture weights,
means, variances, horizons, and component families must all match. Equal counts
alone are never sufficient evidence custody.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .probabilistic_calibration import (
    CalibrationReport,
    DistributionObservation,
    calibration_observation_fingerprint,
    validate_calibration_report,
)
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
        if (
            isinstance(self.min_folds, bool)
            or not isinstance(self.min_folds, int)
            or self.min_folds <= 0
        ):
            raise StateSpaceError(
                "min_folds must be a positive integer",
                context={"reason": "invalid_promotion_gate", "field": "min_folds"},
            )
        _unit("min_calibration_score", self.min_calibration_score)
        _unit("max_coverage_gap", self.max_coverage_gap)
        if self.min_mean_log_score is not None:
            _finite("min_mean_log_score", self.min_mean_log_score)
        if (
            self.max_mean_crps is not None
            and _finite("max_mean_crps", self.max_mean_crps) < 0.0
        ):
            raise StateSpaceError(
                "max_mean_crps must be non-negative",
                context={"reason": "invalid_promotion_gate", "field": "max_mean_crps"},
            )
        if _finite("max_drift_events_per_100", self.max_drift_events_per_100) < 0.0:
            raise StateSpaceError(
                "max_drift_events_per_100 must be non-negative",
                context={
                    "reason": "invalid_promotion_gate",
                    "field": "max_drift_events_per_100",
                },
            )
        if _finite("min_effective_model_count", self.min_effective_model_count) < 1.0:
            raise StateSpaceError(
                "min_effective_model_count must be at least 1",
                context={
                    "reason": "invalid_promotion_gate",
                    "field": "min_effective_model_count",
                },
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
    ensemble_fingerprint: str
    calibration_fingerprint: str
    calibration_target_fingerprint: str
    evidence_observation_fingerprint: str
    gate_fingerprint: str
    fingerprint: str


def evaluate_probabilistic_promotion(
    ensemble: BayesianEnsembleReport,
    calibration: CalibrationReport,
    *,
    gate: ProbabilisticPromotionGate | None = None,
) -> ProbabilisticPromotionDecision:
    """Evaluate numerical evidence without mutating or activating anything."""

    actual_gate = gate or ProbabilisticPromotionGate()
    validate_calibration_report(calibration)
    ensemble_observations = tuple(
        DistributionObservation(
            forecast=step.predictive,
            actual=step.actual,
            target_index=step.target_index,
        )
        for step in ensemble.steps
    )
    ensemble_pairs = tuple(
        (observation.target_index, float(observation.actual))
        for observation in ensemble_observations
    )
    if calibration.observations != len(ensemble_observations):
        raise StateSpaceError(
            "ensemble and calibration evidence must cover equal fold counts",
            context={
                "reason": "evidence_count_mismatch",
                "ensemble_folds": len(ensemble.steps),
                "calibration_observations": calibration.observations,
            },
        )
    if calibration.target_pairs != ensemble_pairs:
        raise StateSpaceError(
            "ensemble and calibration targets must match exactly",
            context={"reason": "promotion_target_identity_mismatch"},
        )
    ensemble_observation_fingerprint = calibration_observation_fingerprint(
        ensemble_observations
    )
    if calibration.observation_fingerprint != ensemble_observation_fingerprint:
        raise StateSpaceError(
            "calibration forecasts must be the exact ensemble predictive evidence",
            context={"reason": "promotion_forecast_identity_mismatch"},
        )

    reasons: list[str] = []
    folds = len(ensemble.steps)
    worst_coverage_gap = max(
        (item.absolute_gap for item in calibration.coverage),
        default=1.0,
    )
    drift_events_per_100 = (
        100.0 * len(calibration.drift_events) / max(1, calibration.observations)
    )
    effective_model_count = ensemble.average_effective_model_count

    if folds < actual_gate.min_folds:
        reasons.append("insufficient_folds")
    if calibration.calibration_score < actual_gate.min_calibration_score:
        reasons.append("calibration_score_below_gate")
    if worst_coverage_gap > actual_gate.max_coverage_gap:
        reasons.append("coverage_gap_above_gate")
    if (
        actual_gate.min_mean_log_score is not None
        and ensemble.mean_log_score < actual_gate.min_mean_log_score
    ):
        reasons.append("log_score_below_gate")
    if (
        actual_gate.max_mean_crps is not None
        and ensemble.mean_crps > actual_gate.max_mean_crps
    ):
        reasons.append("crps_above_gate")
    if drift_events_per_100 > actual_gate.max_drift_events_per_100:
        reasons.append("calibration_drift_above_gate")
    if effective_model_count < actual_gate.min_effective_model_count:
        reasons.append("ensemble_diversity_below_gate")

    eligible = not reasons
    if eligible:
        reasons.append("probabilistic_evidence_gate_passed")

    gate_fingerprint = _gate_fingerprint(actual_gate)
    fingerprint = _decision_fingerprint(
        eligible=eligible,
        reasons=tuple(reasons),
        folds=folds,
        calibration_score=calibration.calibration_score,
        worst_coverage_gap=worst_coverage_gap,
        mean_log_score=ensemble.mean_log_score,
        mean_crps=ensemble.mean_crps,
        drift_events_per_100=drift_events_per_100,
        average_effective_model_count=effective_model_count,
        ensemble_fingerprint=ensemble.fingerprint,
        calibration_fingerprint=calibration.fingerprint,
        calibration_target_fingerprint=calibration.target_fingerprint,
        evidence_observation_fingerprint=ensemble_observation_fingerprint,
        gate_fingerprint=gate_fingerprint,
    )

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
        ensemble_fingerprint=ensemble.fingerprint,
        calibration_fingerprint=calibration.fingerprint,
        calibration_target_fingerprint=calibration.target_fingerprint,
        evidence_observation_fingerprint=ensemble_observation_fingerprint,
        gate_fingerprint=gate_fingerprint,
        fingerprint=fingerprint,
    )


def validate_probabilistic_promotion_decision(
    decision: ProbabilisticPromotionDecision,
) -> None:
    """Reject a malformed or tampered promotion evidence artifact."""

    if not isinstance(decision, ProbabilisticPromotionDecision):
        raise StateSpaceError(
            "decision must be a ProbabilisticPromotionDecision",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    if not isinstance(decision.eligible, bool):
        raise StateSpaceError(
            "eligible must be a boolean",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    if (
        isinstance(decision.folds, bool)
        or not isinstance(decision.folds, int)
        or decision.folds < 1
    ):
        raise StateSpaceError(
            "folds must be a positive integer",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    _unit("calibration_score", decision.calibration_score)
    _unit("worst_coverage_gap", decision.worst_coverage_gap)
    _finite("mean_log_score", decision.mean_log_score)
    if _finite("mean_crps", decision.mean_crps) < 0.0:
        raise StateSpaceError(
            "mean_crps must be non-negative",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    if _finite("drift_events_per_100", decision.drift_events_per_100) < 0.0:
        raise StateSpaceError(
            "drift_events_per_100 must be non-negative",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    if (
        _finite(
            "average_effective_model_count",
            decision.average_effective_model_count,
        )
        < 1.0
    ):
        raise StateSpaceError(
            "average_effective_model_count must be at least 1",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    _validate_reasons(decision.reasons, eligible=decision.eligible)
    for name, value in (
        ("ensemble_fingerprint", decision.ensemble_fingerprint),
        ("calibration_fingerprint", decision.calibration_fingerprint),
        ("calibration_target_fingerprint", decision.calibration_target_fingerprint),
        (
            "evidence_observation_fingerprint",
            decision.evidence_observation_fingerprint,
        ),
        ("gate_fingerprint", decision.gate_fingerprint),
        ("fingerprint", decision.fingerprint),
    ):
        _validate_digest(name, value)

    expected = _decision_fingerprint(
        eligible=decision.eligible,
        reasons=decision.reasons,
        folds=decision.folds,
        calibration_score=decision.calibration_score,
        worst_coverage_gap=decision.worst_coverage_gap,
        mean_log_score=decision.mean_log_score,
        mean_crps=decision.mean_crps,
        drift_events_per_100=decision.drift_events_per_100,
        average_effective_model_count=decision.average_effective_model_count,
        ensemble_fingerprint=decision.ensemble_fingerprint,
        calibration_fingerprint=decision.calibration_fingerprint,
        calibration_target_fingerprint=decision.calibration_target_fingerprint,
        evidence_observation_fingerprint=decision.evidence_observation_fingerprint,
        gate_fingerprint=decision.gate_fingerprint,
    )
    if decision.fingerprint != expected:
        raise StateSpaceError(
            "probabilistic promotion decision fingerprint mismatch",
            context={"reason": "probabilistic_promotion_identity_mismatch"},
        )


def _gate_fingerprint(gate: ProbabilisticPromotionGate) -> str:
    return _digest(
        {
            "schema": "jeeves.probabilistic-promotion-gate.v3",
            "min_folds": gate.min_folds,
            "min_calibration_score": gate.min_calibration_score,
            "max_coverage_gap": gate.max_coverage_gap,
            "min_mean_log_score": gate.min_mean_log_score,
            "max_mean_crps": gate.max_mean_crps,
            "max_drift_events_per_100": gate.max_drift_events_per_100,
            "min_effective_model_count": gate.min_effective_model_count,
        }
    )


def _decision_fingerprint(
    *,
    eligible: bool,
    reasons: tuple[str, ...],
    folds: int,
    calibration_score: float,
    worst_coverage_gap: float,
    mean_log_score: float,
    mean_crps: float,
    drift_events_per_100: float,
    average_effective_model_count: float,
    ensemble_fingerprint: str,
    calibration_fingerprint: str,
    calibration_target_fingerprint: str,
    evidence_observation_fingerprint: str,
    gate_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.probabilistic-promotion-decision.v3",
            "eligible": eligible,
            "reasons": list(reasons),
            "folds": folds,
            "calibration_score": calibration_score,
            "worst_coverage_gap": worst_coverage_gap,
            "mean_log_score": mean_log_score,
            "mean_crps": mean_crps,
            "drift_events_per_100": drift_events_per_100,
            "average_effective_model_count": average_effective_model_count,
            "ensemble_fingerprint": ensemble_fingerprint,
            "calibration_fingerprint": calibration_fingerprint,
            "calibration_target_fingerprint": calibration_target_fingerprint,
            "evidence_observation_fingerprint": evidence_observation_fingerprint,
            "gate_fingerprint": gate_fingerprint,
        }
    )


def _validate_reasons(reasons: tuple[str, ...], *, eligible: bool) -> None:
    if not isinstance(reasons, tuple) or not reasons:
        raise StateSpaceError(
            "reasons must be a non-empty tuple",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        raise StateSpaceError(
            "reasons must contain non-empty strings",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )
    passed = "probabilistic_evidence_gate_passed" in reasons
    if eligible != passed or (passed and len(reasons) != 1):
        raise StateSpaceError(
            "promotion reasons disagree with eligibility",
            context={"reason": "invalid_probabilistic_promotion_decision"},
        )


def _validate_digest(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_probabilistic_promotion_decision"},
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
    "validate_probabilistic_promotion_decision",
]
