"""Leakage-safe empirical uncertainty bands for Jeeves historical forecasts.

Point forecasts are not uncertainty estimates.  This module adds a deterministic
sequential conformal layer over completed walk-forward folds.  Every historical
interval is calibrated only from residuals belonging to *earlier* completed
folds, so a target can never help choose its own interval width.

The uncertainty layer sits after temporal jackknife robustness.  It does not
change point predictions, fetch data, call a model, or mutate learning state.
It may only preserve or veto a robust historical promotion.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .bidirectional_calibration import CrossDirectionConfig
from .bidirectional_modes import BidirectionalConfig
from .historical_modes import (
    FoldResult,
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    ModeReport,
    SelectionGate,
    WalkForwardConfig,
)
from .historical_robustness import (
    TemporalJackknifeConfig,
    TemporalJackknifeModeLab,
    TemporalJackknifeReport,
)

_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class ConformalConfig:
    """Configuration for sequential absolute-residual conformal intervals."""

    alpha: float = 0.20
    min_calibration_folds: int = 8
    calibration_window: int | None = 32
    min_empirical_coverage: float = 0.70
    max_direction_coverage_gap: float = 0.25
    max_direction_width_asymmetry: float = 1.50

    def __post_init__(self) -> None:
        _open_interval("alpha", self.alpha, 0.0, 1.0)
        _positive_int("min_calibration_folds", self.min_calibration_folds)
        if self.calibration_window is not None:
            _positive_int("calibration_window", self.calibration_window)
            if self.calibration_window < self.min_calibration_folds:
                raise HistoricalModeError(
                    "calibration_window cannot be smaller than min_calibration_folds",
                    context={"reason": "invalid_conformal_config", "field": "calibration_window"},
                )
        _closed_interval("min_empirical_coverage", self.min_empirical_coverage, 0.0, 1.0)
        _closed_interval(
            "max_direction_coverage_gap", self.max_direction_coverage_gap, 0.0, 1.0
        )
        _non_negative("max_direction_width_asymmetry", self.max_direction_width_asymmetry)

    @property
    def nominal_coverage(self) -> float:
        return 1.0 - self.alpha


@dataclass(frozen=True, slots=True)
class ConformalIntervalFold:
    """One out-of-sample interval whose radius used earlier residuals only."""

    train_end: int
    target_index: int
    predicted: float
    actual: float
    lower: float
    upper: float
    radius: float
    calibration_count: int
    covered: bool

    def __post_init__(self) -> None:
        if self.target_index <= self.train_end:
            raise HistoricalModeError(
                "interval target must be after its training boundary",
                context={"reason": "leakage_boundary"},
            )
        if self.calibration_count <= 0:
            raise HistoricalModeError(
                "interval must have calibration evidence",
                context={"reason": "invalid_calibration_count"},
            )
        for name, value in (
            ("predicted", self.predicted),
            ("actual", self.actual),
            ("lower", self.lower),
            ("upper", self.upper),
            ("radius", self.radius),
        ):
            if not math.isfinite(value):
                raise HistoricalModeError(
                    f"{name} must be finite",
                    context={"reason": "invalid_number", "field": name},
                )
        if self.radius < 0.0 or self.lower > self.upper:
            raise HistoricalModeError(
                "invalid conformal interval geometry",
                context={"reason": "invalid_interval"},
            )

    @property
    def width(self) -> float:
        return self.upper - self.lower


@dataclass(frozen=True, slots=True)
class DirectionalUncertaintyReport:
    """Sequential conformal performance for one mode in one orientation."""

    mode: HistoricalMode
    source_folds: int
    intervals: tuple[ConformalIntervalFold, ...]
    nominal_coverage: float
    empirical_coverage: float | None
    average_width: float | None
    median_width: float | None
    maximum_width: float | None

    @property
    def calibrated_folds(self) -> int:
        return len(self.intervals)


@dataclass(frozen=True, slots=True)
class UncertaintyDecision:
    candidate: HistoricalMode
    baseline: HistoricalMode
    robustness_accepted: bool
    accepted: bool
    reasons: tuple[str, ...]
    nominal_coverage: float
    forward_coverage: float | None
    backward_coverage: float | None
    coverage_gap: float | None
    forward_average_width: float | None
    backward_average_width: float | None
    width_asymmetry: float | None


@dataclass(frozen=True, slots=True)
class HistoricalUncertaintyReport:
    robustness: TemporalJackknifeReport
    forward: DirectionalUncertaintyReport
    backward: DirectionalUncertaintyReport
    decision: UncertaintyDecision
    fingerprint: str

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.decision.candidate if self.decision.accepted else self.decision.baseline

    def as_payload(self) -> dict[str, object]:
        return {
            "selected_mode": self.selected_mode.value,
            "uncertainty_accepted": self.decision.accepted,
            "robustness_accepted": self.decision.robustness_accepted,
            "nominal_coverage": self.decision.nominal_coverage,
            "forward_coverage": self.decision.forward_coverage,
            "backward_coverage": self.decision.backward_coverage,
            "coverage_gap": self.decision.coverage_gap,
            "forward_average_width": self.decision.forward_average_width,
            "backward_average_width": self.decision.backward_average_width,
            "width_asymmetry": self.decision.width_asymmetry,
            "fingerprint": self.fingerprint,
        }


class HistoricalUncertaintyModeLab:
    """Add sequential empirical uncertainty validation after robustness gates."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        bidirectional: BidirectionalConfig | None = None,
        calibration: CrossDirectionConfig | None = None,
        jackknife: TemporalJackknifeConfig | None = None,
        conformal: ConformalConfig | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.conformal = conformal or ConformalConfig()
        self._lab = TemporalJackknifeModeLab(
            config=config,
            gate=gate,
            bidirectional=bidirectional,
            calibration=calibration,
            jackknife=jackknife,
            modes=modes,
        )

    @property
    def modes(self) -> tuple[HistoricalMode, ...]:
        return self._lab.modes

    def evaluate(self, series: HistoricalSeries) -> HistoricalUncertaintyReport:
        robustness = self._lab.evaluate(series)
        candidate = robustness.decision.candidate
        full = robustness.full
        forward_mode = full.base.forward.report.by_mode(candidate)
        backward_mode = full.base.backward.report.by_mode(candidate)
        forward = build_sequential_intervals(forward_mode, self.conformal)
        backward = build_sequential_intervals(backward_mode, self.conformal)
        decision = _decision(robustness, forward, backward, self.conformal)
        fingerprint = _fingerprint(robustness, forward, backward, decision, self.conformal)
        return HistoricalUncertaintyReport(
            robustness=robustness,
            forward=forward,
            backward=backward,
            decision=decision,
            fingerprint=fingerprint,
        )


def build_sequential_intervals(
    report: ModeReport,
    config: ConformalConfig | None = None,
) -> DirectionalUncertaintyReport:
    """Build intervals using only residuals from folds preceding each target."""

    actual_config = config or ConformalConfig()
    prior_errors: list[float] = []
    intervals: list[ConformalIntervalFold] = []

    for fold in report.folds:
        calibration = prior_errors
        if actual_config.calibration_window is not None:
            calibration = calibration[-actual_config.calibration_window :]

        if len(calibration) >= actual_config.min_calibration_folds:
            radius = conformal_radius(calibration, actual_config.alpha)
            lower = fold.predicted - radius
            upper = fold.predicted + radius
            covered = lower - _EPSILON <= fold.actual <= upper + _EPSILON
            intervals.append(
                ConformalIntervalFold(
                    train_end=fold.train_end,
                    target_index=fold.target_index,
                    predicted=fold.predicted,
                    actual=fold.actual,
                    lower=lower,
                    upper=upper,
                    radius=radius,
                    calibration_count=len(calibration),
                    covered=covered,
                )
            )

        # Current residual becomes eligible only for later targets.
        prior_errors.append(fold.absolute_error)

    coverage: float | None
    average_width: float | None
    median_width: float | None
    maximum_width: float | None
    if intervals:
        widths = [interval.width for interval in intervals]
        coverage = statistics.fmean(1.0 if interval.covered else 0.0 for interval in intervals)
        average_width = statistics.fmean(widths)
        median_width = float(statistics.median(widths))
        maximum_width = max(widths)
    else:
        coverage = None
        average_width = None
        median_width = None
        maximum_width = None

    return DirectionalUncertaintyReport(
        mode=report.mode,
        source_folds=len(report.folds),
        intervals=tuple(intervals),
        nominal_coverage=actual_config.nominal_coverage,
        empirical_coverage=coverage,
        average_width=average_width,
        median_width=median_width,
        maximum_width=maximum_width,
    )


def conformal_radius(errors: Sequence[float], alpha: float) -> float:
    """Finite-sample conservative quantile of non-negative calibration errors."""

    _open_interval("alpha", alpha, 0.0, 1.0)
    if not errors:
        raise HistoricalModeError(
            "conformal radius requires calibration residuals",
            context={"reason": "insufficient_calibration"},
        )
    clean: list[float] = []
    for error in errors:
        if isinstance(error, bool) or not isinstance(error, (int, float)):
            raise HistoricalModeError(
                "calibration residuals must be numeric",
                context={"reason": "invalid_number"},
            )
        value = float(error)
        if not math.isfinite(value) or value < 0.0:
            raise HistoricalModeError(
                "calibration residuals must be non-negative and finite",
                context={"reason": "invalid_number"},
            )
        clean.append(value)

    ordered = sorted(clean)
    # Standard conservative split-conformal rank ceil((n+1)*(1-alpha)),
    # clipped to the available empirical support.
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    rank = min(len(ordered), max(1, rank))
    return ordered[rank - 1]


def _decision(
    robustness: TemporalJackknifeReport,
    forward: DirectionalUncertaintyReport,
    backward: DirectionalUncertaintyReport,
    config: ConformalConfig,
) -> UncertaintyDecision:
    reasons: list[str] = []
    if not robustness.decision.accepted:
        reasons.append("robustness_gate_rejected")
    if forward.empirical_coverage is None:
        reasons.append("insufficient_forward_calibration")
    elif forward.empirical_coverage < config.min_empirical_coverage:
        reasons.append("low_forward_empirical_coverage")
    if backward.empirical_coverage is None:
        reasons.append("insufficient_backward_calibration")
    elif backward.empirical_coverage < config.min_empirical_coverage:
        reasons.append("low_backward_empirical_coverage")

    coverage_gap = _optional_gap(forward.empirical_coverage, backward.empirical_coverage)
    if coverage_gap is not None and coverage_gap > config.max_direction_coverage_gap:
        reasons.append("directional_coverage_disagreement")

    width_asymmetry = _optional_asymmetry(forward.average_width, backward.average_width)
    if width_asymmetry is not None and width_asymmetry > config.max_direction_width_asymmetry:
        reasons.append("directional_interval_width_asymmetry")

    accepted = robustness.decision.accepted and not reasons
    if accepted:
        reasons.append("conformal_uncertainty_gate_passed")

    return UncertaintyDecision(
        candidate=robustness.decision.candidate,
        baseline=robustness.decision.baseline,
        robustness_accepted=robustness.decision.accepted,
        accepted=accepted,
        reasons=tuple(reasons),
        nominal_coverage=config.nominal_coverage,
        forward_coverage=forward.empirical_coverage,
        backward_coverage=backward.empirical_coverage,
        coverage_gap=coverage_gap,
        forward_average_width=forward.average_width,
        backward_average_width=backward.average_width,
        width_asymmetry=width_asymmetry,
    )


def _optional_gap(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return abs(left - right)


def _optional_asymmetry(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    scale = 0.5 * (abs(left) + abs(right))
    if scale <= _EPSILON:
        return 0.0
    return abs(left - right) / scale


def _fingerprint(
    robustness: TemporalJackknifeReport,
    forward: DirectionalUncertaintyReport,
    backward: DirectionalUncertaintyReport,
    decision: UncertaintyDecision,
    config: ConformalConfig,
) -> str:
    parts = [
        "historical-conformal-v1",
        robustness.fingerprint,
        repr(config),
        decision.candidate.value,
        str(decision.accepted),
        _format_optional(decision.forward_coverage),
        _format_optional(decision.backward_coverage),
        _format_optional(decision.coverage_gap),
        _format_optional(decision.forward_average_width),
        _format_optional(decision.backward_average_width),
        _format_optional(decision.width_asymmetry),
        ",".join(decision.reasons),
    ]
    for direction in (forward, backward):
        parts.extend((direction.mode.value, str(direction.source_folds), str(direction.calibrated_folds)))
        for interval in direction.intervals:
            parts.extend(
                (
                    str(interval.train_end),
                    str(interval.target_index),
                    format(interval.lower, ".17g"),
                    format(interval.upper, ".17g"),
                    str(interval.calibration_count),
                    str(interval.covered),
                )
            )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _format_optional(value: float | None) -> str:
    return "none" if value is None else format(value, ".17g")


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return value


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise HistoricalModeError(
            f"{name} must be a non-negative finite number",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HistoricalModeError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return number


def _open_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum < number < maximum:
        raise HistoricalModeError(
            f"{name} must be strictly between {minimum} and {maximum}",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return number
