"""Deterministic temporal jackknife validation for Jeeves historical modes.

A model that survives forward/backward evaluation can still be fragile to where
the historical window starts or ends.  This module cross-examines calibrated
bidirectional selection across deterministic cropped views of the same series:
full, left-trimmed, right-trimmed, and both-ends-trimmed.

No random resampling is used.  Each view runs the complete calibrated
bidirectional laboratory independently.  Promotion is preserved only when the
full view passes and the same candidate keeps sufficient support across views
without excessive MAE spread.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .bidirectional_calibration import (
    CalibratedBidirectionalModeLab,
    CalibratedBidirectionalReport,
    CrossDirectionConfig,
)
from .bidirectional_modes import BidirectionalConfig
from .historical_modes import (
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)

_EPSILON = 1e-12


class TemporalViewKind(str, Enum):
    FULL = "full"
    TRIM_LEFT = "trim_left"
    TRIM_RIGHT = "trim_right"
    TRIM_BOTH = "trim_both"


@dataclass(frozen=True, slots=True)
class TemporalJackknifeConfig:
    """Deterministic endpoint-perturbation robustness thresholds."""

    trim_fraction: float = 0.10
    max_trim: int = 8
    min_views: int = 3
    min_acceptance_rate: float = 0.75
    min_candidate_support_rate: float = 0.75
    max_candidate_mae_spread: float = 1.00

    def __post_init__(self) -> None:
        _open_interval("trim_fraction", self.trim_fraction, 0.0, 0.5)
        _positive_int("max_trim", self.max_trim)
        if isinstance(self.min_views, bool) or not isinstance(self.min_views, int):
            raise HistoricalModeError(
                "min_views must be an integer",
                context={"reason": "invalid_jackknife_gate", "field": "min_views"},
            )
        if not 1 <= self.min_views <= len(TemporalViewKind):
            raise HistoricalModeError(
                "min_views must be between 1 and 4",
                context={"reason": "invalid_jackknife_gate", "field": "min_views"},
            )
        _closed_interval("min_acceptance_rate", self.min_acceptance_rate, 0.0, 1.0)
        _closed_interval(
            "min_candidate_support_rate",
            self.min_candidate_support_rate,
            0.0,
            1.0,
        )
        _non_negative("max_candidate_mae_spread", self.max_candidate_mae_spread)


@dataclass(frozen=True, slots=True)
class TemporalViewEvaluation:
    """One deterministic historical crop and its full calibrated evaluation."""

    kind: TemporalViewKind
    start: int
    stop: int
    report: CalibratedBidirectionalReport

    @property
    def sample_count(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True, slots=True)
class TemporalJackknifeDecision:
    candidate: HistoricalMode
    baseline: HistoricalMode
    accepted: bool
    reasons: tuple[str, ...]
    total_views: int
    accepted_views: int
    candidate_supported_views: int
    acceptance_rate: float
    candidate_support_rate: float
    candidate_mae_spread: float
    view_selected_modes: tuple[tuple[TemporalViewKind, HistoricalMode], ...]


@dataclass(frozen=True, slots=True)
class TemporalJackknifeReport:
    views: tuple[TemporalViewEvaluation, ...]
    decision: TemporalJackknifeDecision
    fingerprint: str

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.decision.candidate if self.decision.accepted else self.decision.baseline

    @property
    def full(self) -> CalibratedBidirectionalReport:
        return self.by_view(TemporalViewKind.FULL).report

    def by_view(self, kind: TemporalViewKind) -> TemporalViewEvaluation:
        for view in self.views:
            if view.kind is kind:
                return view
        raise HistoricalModeError(
            "requested temporal jackknife view is absent",
            context={"reason": "unknown_temporal_view", "view": kind.value},
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "selected_mode": self.selected_mode.value,
            "jackknife_accepted": self.decision.accepted,
            "total_views": self.decision.total_views,
            "accepted_views": self.decision.accepted_views,
            "candidate_supported_views": self.decision.candidate_supported_views,
            "acceptance_rate": self.decision.acceptance_rate,
            "candidate_support_rate": self.decision.candidate_support_rate,
            "candidate_mae_spread": self.decision.candidate_mae_spread,
            "fingerprint": self.fingerprint,
        }


class TemporalJackknifeModeLab:
    """Require calibrated bidirectional mode stability across temporal crops."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        bidirectional: BidirectionalConfig | None = None,
        calibration: CrossDirectionConfig | None = None,
        jackknife: TemporalJackknifeConfig | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.config = config or WalkForwardConfig()
        self.gate = gate or SelectionGate()
        self.bidirectional = bidirectional or BidirectionalConfig()
        self.calibration = calibration or CrossDirectionConfig()
        self.jackknife = jackknife or TemporalJackknifeConfig()
        self._lab = CalibratedBidirectionalModeLab(
            config=self.config,
            gate=self.gate,
            bidirectional=self.bidirectional,
            calibration=self.calibration,
            modes=modes,
        )

    @property
    def modes(self) -> tuple[HistoricalMode, ...]:
        return self._lab.modes

    def evaluate(self, series: HistoricalSeries) -> TemporalJackknifeReport:
        slices = _view_slices(series, self.config, self.jackknife)
        views = tuple(
            TemporalViewEvaluation(
                kind=kind,
                start=start,
                stop=stop,
                report=self._lab.evaluate(_slice_series(series, start, stop, kind)),
            )
            for kind, start, stop in slices
        )
        full = _view_by_kind(views, TemporalViewKind.FULL)
        decision = _decision(views, full.report, self.jackknife)
        fingerprint = _fingerprint(views, decision, self.jackknife)
        return TemporalJackknifeReport(
            views=views,
            decision=decision,
            fingerprint=fingerprint,
        )


def _view_slices(
    series: HistoricalSeries,
    config: WalkForwardConfig,
    jackknife: TemporalJackknifeConfig,
) -> tuple[tuple[TemporalViewKind, int, int], ...]:
    size = len(series.values)
    minimum = config.min_train_size + config.horizon
    trim = min(jackknife.max_trim, max(1, int(math.floor(size * jackknife.trim_fraction))))

    candidates = (
        (TemporalViewKind.FULL, 0, size),
        (TemporalViewKind.TRIM_LEFT, trim, size),
        (TemporalViewKind.TRIM_RIGHT, 0, size - trim),
        (TemporalViewKind.TRIM_BOTH, trim, size - trim),
    )
    valid: list[tuple[TemporalViewKind, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for kind, start, stop in candidates:
        if stop - start < minimum:
            continue
        key = (start, stop)
        if key in seen:
            continue
        seen.add(key)
        valid.append((kind, start, stop))
    if not valid or valid[0][0] is not TemporalViewKind.FULL:
        raise HistoricalModeError(
            "series is too short for the full temporal jackknife view",
            context={
                "reason": "insufficient_history",
                "samples": size,
                "minimum": minimum,
            },
        )
    return tuple(valid)


def _slice_series(
    series: HistoricalSeries,
    start: int,
    stop: int,
    kind: TemporalViewKind,
) -> HistoricalSeries:
    if kind is TemporalViewKind.FULL and start == 0 and stop == len(series.values):
        return series
    timestamps = None if series.timestamps is None else series.timestamps[start:stop]
    return HistoricalSeries(
        values=series.values[start:stop],
        timestamps=timestamps,
        label=f"{series.label}::jackknife-{kind.value}",
    )


def _decision(
    views: Sequence[TemporalViewEvaluation],
    full: CalibratedBidirectionalReport,
    config: TemporalJackknifeConfig,
) -> TemporalJackknifeDecision:
    candidate = full.decision.candidate
    baseline = full.decision.baseline
    total = len(views)
    accepted_views = sum(1 for view in views if view.report.decision.accepted)
    supported_views = sum(
        1
        for view in views
        if view.report.decision.accepted and view.report.decision.candidate is candidate
    )
    acceptance_rate = accepted_views / total
    support_rate = supported_views / total

    candidate_errors = []
    for view in views:
        diagnostic = view.report.by_mode(candidate)
        candidate_errors.append(0.5 * (diagnostic.forward_mae + diagnostic.backward_mae))
    candidate_mae_spread = _relative_spread(candidate_errors)

    reasons: list[str] = []
    if not full.decision.accepted:
        reasons.append("full_calibration_rejected")
    if total < config.min_views:
        reasons.append("insufficient_temporal_views")
    if acceptance_rate < config.min_acceptance_rate:
        reasons.append("unstable_view_acceptance")
    if support_rate < config.min_candidate_support_rate:
        reasons.append("unstable_candidate_support")
    if candidate_mae_spread > config.max_candidate_mae_spread:
        reasons.append("candidate_mae_view_instability")

    accepted = full.decision.accepted and not reasons
    if accepted:
        reasons.append("temporal_jackknife_passed")

    return TemporalJackknifeDecision(
        candidate=candidate,
        baseline=baseline,
        accepted=accepted,
        reasons=tuple(reasons),
        total_views=total,
        accepted_views=accepted_views,
        candidate_supported_views=supported_views,
        acceptance_rate=acceptance_rate,
        candidate_support_rate=support_rate,
        candidate_mae_spread=candidate_mae_spread,
        view_selected_modes=tuple((view.kind, view.report.selected_mode) for view in views),
    )


def _relative_spread(values: Sequence[float]) -> float:
    if not values:
        return math.inf
    mean = statistics.fmean(abs(value) for value in values)
    if mean <= _EPSILON:
        return 0.0
    return (max(values) - min(values)) / mean


def _view_by_kind(
    views: Sequence[TemporalViewEvaluation],
    kind: TemporalViewKind,
) -> TemporalViewEvaluation:
    for view in views:
        if view.kind is kind:
            return view
    raise HistoricalModeError(
        "required temporal jackknife view is missing",
        context={"reason": "unknown_temporal_view", "view": kind.value},
    )


def _fingerprint(
    views: Sequence[TemporalViewEvaluation],
    decision: TemporalJackknifeDecision,
    config: TemporalJackknifeConfig,
) -> str:
    parts = [
        "temporal-jackknife-v1",
        repr(config),
        decision.candidate.value,
        str(decision.accepted),
        format(decision.acceptance_rate, ".17g"),
        format(decision.candidate_support_rate, ".17g"),
        format(decision.candidate_mae_spread, ".17g"),
        ",".join(decision.reasons),
    ]
    for view in views:
        parts.extend(
            (
                view.kind.value,
                str(view.start),
                str(view.stop),
                view.report.fingerprint,
                view.report.selected_mode.value,
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    return value


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise HistoricalModeError(
            f"{name} must be a non-negative finite number",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HistoricalModeError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    return number


def _open_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum < number < maximum:
        raise HistoricalModeError(
            f"{name} must be strictly between {minimum} and {maximum}",
            context={"reason": "invalid_jackknife_gate", "field": name},
        )
    return number
