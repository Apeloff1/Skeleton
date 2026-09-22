"""Multi-horizon consistency validation for Jeeves historical forecasting.

A model can dominate at one-step prediction and degrade badly at longer
forecast distances.  This module runs the complete uncertainty-aware historical
stack independently at multiple horizons and treats horizon consistency as
another falsification axis.

The smallest configured horizon is the anchor.  Its candidate must pass there,
and the same candidate must retain sufficient accepted support across the other
valid horizons with bounded MAE variation.  No result from one horizon is used
to train or calibrate another horizon.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass, replace
from typing import Sequence

from .bidirectional_calibration import CrossDirectionConfig
from .bidirectional_modes import BidirectionalConfig
from .historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)
from .historical_robustness import TemporalJackknifeConfig
from .historical_uncertainty import (
    ConformalConfig,
    HistoricalUncertaintyModeLab,
    HistoricalUncertaintyReport,
)

_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class HorizonGridConfig:
    """Configured horizons and fail-closed consistency thresholds."""

    horizons: tuple[int, ...] = (1, 2, 3, 5)
    min_horizons: int = 3
    min_acceptance_rate: float = 0.75
    min_candidate_support_rate: float = 0.75
    max_candidate_mae_spread: float = 1.50
    max_coverage_spread: float = 0.35

    def __post_init__(self) -> None:
        if not self.horizons:
            raise HistoricalModeError(
                "at least one forecast horizon is required",
                context={"reason": "invalid_horizon_grid", "field": "horizons"},
            )
        clean = tuple(_positive_int("horizon", horizon) for horizon in self.horizons)
        if len(set(clean)) != len(clean):
            raise HistoricalModeError(
                "forecast horizons must be unique",
                context={"reason": "invalid_horizon_grid", "field": "horizons"},
            )
        if tuple(sorted(clean)) != clean:
            raise HistoricalModeError(
                "forecast horizons must be strictly increasing",
                context={"reason": "invalid_horizon_grid", "field": "horizons"},
            )
        object.__setattr__(self, "horizons", clean)
        _positive_int("min_horizons", self.min_horizons)
        if self.min_horizons > len(clean):
            raise HistoricalModeError(
                "min_horizons cannot exceed configured horizons",
                context={"reason": "invalid_horizon_grid", "field": "min_horizons"},
            )
        _closed_interval("min_acceptance_rate", self.min_acceptance_rate, 0.0, 1.0)
        _closed_interval(
            "min_candidate_support_rate",
            self.min_candidate_support_rate,
            0.0,
            1.0,
        )
        _non_negative("max_candidate_mae_spread", self.max_candidate_mae_spread)
        _closed_interval("max_coverage_spread", self.max_coverage_spread, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class HorizonEvaluation:
    horizon: int
    report: HistoricalUncertaintyReport

    @property
    def accepted(self) -> bool:
        return self.report.decision.accepted

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.report.selected_mode


@dataclass(frozen=True, slots=True)
class HorizonConsistencyDecision:
    candidate: HistoricalMode
    baseline: HistoricalMode
    anchor_horizon: int
    anchor_accepted: bool
    accepted: bool
    reasons: tuple[str, ...]
    configured_horizons: int
    evaluated_horizons: int
    accepted_horizons: int
    candidate_supported_horizons: int
    acceptance_rate: float
    candidate_support_rate: float
    candidate_mae_spread: float
    empirical_coverage_spread: float | None


@dataclass(frozen=True, slots=True)
class MultiHorizonReport:
    evaluations: tuple[HorizonEvaluation, ...]
    decision: HorizonConsistencyDecision
    fingerprint: str

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.decision.candidate if self.decision.accepted else self.decision.baseline

    def by_horizon(self, horizon: int) -> HorizonEvaluation:
        for evaluation in self.evaluations:
            if evaluation.horizon == horizon:
                return evaluation
        raise HistoricalModeError(
            "requested forecast horizon was not evaluated",
            context={"reason": "unknown_horizon", "horizon": horizon},
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "selected_mode": self.selected_mode.value,
            "multi_horizon_accepted": self.decision.accepted,
            "anchor_horizon": self.decision.anchor_horizon,
            "evaluated_horizons": self.decision.evaluated_horizons,
            "accepted_horizons": self.decision.accepted_horizons,
            "candidate_supported_horizons": self.decision.candidate_supported_horizons,
            "acceptance_rate": self.decision.acceptance_rate,
            "candidate_support_rate": self.decision.candidate_support_rate,
            "candidate_mae_spread": self.decision.candidate_mae_spread,
            "empirical_coverage_spread": self.decision.empirical_coverage_spread,
            "fingerprint": self.fingerprint,
        }


class MultiHorizonModeLab:
    """Run the full uncertainty-aware evaluator independently by horizon."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        bidirectional: BidirectionalConfig | None = None,
        calibration: CrossDirectionConfig | None = None,
        jackknife: TemporalJackknifeConfig | None = None,
        conformal: ConformalConfig | None = None,
        horizons: HorizonGridConfig | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.config = config or WalkForwardConfig()
        self.gate = gate or SelectionGate()
        self.bidirectional = bidirectional
        self.calibration = calibration
        self.jackknife = jackknife
        self.conformal = conformal
        self.horizons = horizons or HorizonGridConfig()
        self.modes = None if modes is None else tuple(modes)

    def evaluate(self, series: HistoricalSeries) -> MultiHorizonReport:
        evaluations: list[HorizonEvaluation] = []
        for horizon in self.horizons.horizons:
            if not _can_evaluate(series, self.config, horizon):
                continue
            horizon_config = replace(self.config, horizon=horizon)
            lab = HistoricalUncertaintyModeLab(
                config=horizon_config,
                gate=self.gate,
                bidirectional=self.bidirectional,
                calibration=self.calibration,
                jackknife=self.jackknife,
                conformal=self.conformal,
                modes=self.modes,
            )
            evaluations.append(HorizonEvaluation(horizon=horizon, report=lab.evaluate(series)))

        if not evaluations:
            raise HistoricalModeError(
                "series is too short for every configured forecast horizon",
                context={"reason": "insufficient_history"},
            )

        evaluations_tuple = tuple(evaluations)
        decision = _decision(evaluations_tuple, self.horizons)
        fingerprint = _fingerprint(evaluations_tuple, decision, self.horizons)
        return MultiHorizonReport(
            evaluations=evaluations_tuple,
            decision=decision,
            fingerprint=fingerprint,
        )


def _can_evaluate(series: HistoricalSeries, config: WalkForwardConfig, horizon: int) -> bool:
    return len(series.values) > config.min_train_size + horizon - 1


def _decision(
    evaluations: Sequence[HorizonEvaluation],
    config: HorizonGridConfig,
) -> HorizonConsistencyDecision:
    anchor = evaluations[0]
    candidate = anchor.report.decision.candidate
    baseline = anchor.report.decision.baseline
    total = len(evaluations)
    accepted_count = sum(1 for evaluation in evaluations if evaluation.accepted)
    support_count = sum(
        1
        for evaluation in evaluations
        if evaluation.accepted and evaluation.report.decision.candidate is candidate
    )
    acceptance_rate = accepted_count / total
    support_rate = support_count / total

    candidate_maes: list[float] = []
    coverages: list[float] = []
    for evaluation in evaluations:
        diagnostics = evaluation.report.robustness.full.by_mode(candidate)
        candidate_maes.append(0.5 * (diagnostics.forward_mae + diagnostics.backward_mae))
        for coverage in (
            evaluation.report.forward.empirical_coverage,
            evaluation.report.backward.empirical_coverage,
        ):
            if coverage is not None:
                coverages.append(coverage)

    mae_spread = _relative_spread(candidate_maes)
    coverage_spread = None if not coverages else max(coverages) - min(coverages)

    reasons: list[str] = []
    if not anchor.accepted:
        reasons.append("anchor_horizon_rejected")
    if total < config.min_horizons:
        reasons.append("insufficient_horizon_coverage")
    if acceptance_rate < config.min_acceptance_rate:
        reasons.append("unstable_horizon_acceptance")
    if support_rate < config.min_candidate_support_rate:
        reasons.append("unstable_candidate_across_horizons")
    if mae_spread > config.max_candidate_mae_spread:
        reasons.append("candidate_mae_horizon_instability")
    if coverage_spread is not None and coverage_spread > config.max_coverage_spread:
        reasons.append("empirical_coverage_horizon_instability")

    accepted = anchor.accepted and not reasons
    if accepted:
        reasons.append("multi_horizon_gate_passed")

    return HorizonConsistencyDecision(
        candidate=candidate,
        baseline=baseline,
        anchor_horizon=anchor.horizon,
        anchor_accepted=anchor.accepted,
        accepted=accepted,
        reasons=tuple(reasons),
        configured_horizons=len(config.horizons),
        evaluated_horizons=total,
        accepted_horizons=accepted_count,
        candidate_supported_horizons=support_count,
        acceptance_rate=acceptance_rate,
        candidate_support_rate=support_rate,
        candidate_mae_spread=mae_spread,
        empirical_coverage_spread=coverage_spread,
    )


def _relative_spread(values: Sequence[float]) -> float:
    if not values:
        return math.inf
    mean = statistics.fmean(abs(value) for value in values)
    if mean <= _EPSILON:
        return 0.0
    return (max(values) - min(values)) / mean


def _fingerprint(
    evaluations: Sequence[HorizonEvaluation],
    decision: HorizonConsistencyDecision,
    config: HorizonGridConfig,
) -> str:
    parts = [
        "multi-horizon-v1",
        repr(config),
        decision.candidate.value,
        str(decision.accepted),
        format(decision.acceptance_rate, ".17g"),
        format(decision.candidate_support_rate, ".17g"),
        format(decision.candidate_mae_spread, ".17g"),
        _format_optional(decision.empirical_coverage_spread),
        ",".join(decision.reasons),
    ]
    for evaluation in evaluations:
        parts.extend(
            (
                str(evaluation.horizon),
                evaluation.report.fingerprint,
                evaluation.report.selected_mode.value,
                str(evaluation.accepted),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _format_optional(value: float | None) -> str:
    return "none" if value is None else format(value, ".17g")


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_horizon_grid", "field": name},
        )
    return value


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_horizon_grid", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise HistoricalModeError(
            f"{name} must be a non-negative finite number",
            context={"reason": "invalid_horizon_grid", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_horizon_grid", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HistoricalModeError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_horizon_grid", "field": name},
        )
    return number
