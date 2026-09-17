"""Bidirectional historical validation for Jeeves.

This module wraps :mod:`skeleton.jeeves.historical_modes` with a second,
reverse-time evaluation pass.  The reverse pass is a *diagnostic mirror*, not a
claim that a causal process literally runs backwards and not a source of live
predictions.  Its purpose is to expose models whose apparent historical edge
exists only because of one temporal orientation, endpoint placement, or an
accidental asymmetry in the evaluation harness.

Rules enforced here:

* forward and backward passes use the same walk-forward configuration;
* the backward pass receives a reversed series with monotonically increasing
  mirrored timestamps, so the underlying HistoricalSeries contract still
  holds;
* each pass remains leakage-safe inside its own temporal coordinate system;
* model selection is based on a consensus score across both directions;
* exact consensus ties prefer persistence so zero demonstrated improvement can
  never promote a more complex mode;
* promotion requires the same candidate to beat persistence independently in
  both directions and remain within bounded temporal asymmetry;
* the result is deterministic and offline-only.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .historical_modes import (
    EvaluationReport,
    HistoricalMode,
    HistoricalModeError,
    HistoricalModeLab,
    HistoricalSeries,
    ModeReport,
    SelectionGate,
    WalkForwardConfig,
)

_EPSILON = 1e-12


class TemporalDirection(str, Enum):
    """Orientation used for an offline historical evaluation."""

    FORWARD = "forward"
    BACKWARD = "backward"


@dataclass(frozen=True, slots=True)
class BidirectionalConfig:
    """Additional gates applied after the two directional evaluations.

    ``max_mae_asymmetry`` is the absolute forward/backward MAE difference
    divided by their mean.  A value of 0 requires exact symmetry; 1 permits a
    difference as large as the mean MAE.

    ``max_direction_rank`` prevents a mode from being promoted when its
    combined average looks good but it is weak in one direction.
    """

    max_mae_asymmetry: float = 0.75
    max_direction_rank: int = 4

    def __post_init__(self) -> None:
        if isinstance(self.max_mae_asymmetry, bool) or not isinstance(
            self.max_mae_asymmetry, (int, float)
        ):
            raise HistoricalModeError(
                "max_mae_asymmetry must be numeric",
                context={"reason": "invalid_bidirectional_gate"},
            )
        asymmetry = float(self.max_mae_asymmetry)
        if not math.isfinite(asymmetry) or asymmetry < 0.0:
            raise HistoricalModeError(
                "max_mae_asymmetry must be a non-negative finite number",
                context={"reason": "invalid_bidirectional_gate"},
            )
        object.__setattr__(self, "max_mae_asymmetry", asymmetry)
        if (
            isinstance(self.max_direction_rank, bool)
            or not isinstance(self.max_direction_rank, int)
            or self.max_direction_rank <= 0
        ):
            raise HistoricalModeError(
                "max_direction_rank must be a positive integer",
                context={"reason": "invalid_bidirectional_gate"},
            )


@dataclass(frozen=True, slots=True)
class DirectionalEvaluation:
    """An evaluation report paired with its temporal orientation."""

    direction: TemporalDirection
    report: EvaluationReport


@dataclass(frozen=True, slots=True)
class BidirectionalDecision:
    """Auditable consensus decision across forward and backward history."""

    candidate: HistoricalMode
    baseline: HistoricalMode
    accepted: bool
    reasons: tuple[str, ...]
    forward_relative_mae_improvement: float
    backward_relative_mae_improvement: float
    forward_worst_error_ratio: float
    backward_worst_error_ratio: float
    mae_asymmetry: float
    forward_rank: int
    backward_rank: int


@dataclass(frozen=True, slots=True)
class BidirectionalReport:
    """Complete forward/backward validation artifact."""

    forward: DirectionalEvaluation
    backward: DirectionalEvaluation
    consensus_ranking: tuple[HistoricalMode, ...]
    decision: BidirectionalDecision
    fingerprint: str

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.decision.candidate if self.decision.accepted else self.decision.baseline

    def as_payload(self) -> dict[str, object]:
        """Compact JSON-scalar summary for evidence recording."""

        forward_mode = self.forward.report.by_mode(self.selected_mode)
        backward_mode = self.backward.report.by_mode(self.selected_mode)
        return {
            "selected_mode": self.selected_mode.value,
            "bidirectional_accepted": self.decision.accepted,
            "forward_mae": forward_mode.metrics.mae,
            "backward_mae": backward_mode.metrics.mae,
            "mae_asymmetry": self.decision.mae_asymmetry,
            "forward_rank": self.decision.forward_rank,
            "backward_rank": self.decision.backward_rank,
            "fingerprint": self.fingerprint,
        }


class BidirectionalModeLab:
    """Run the same historical laboratory in both temporal orientations."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        bidirectional: BidirectionalConfig | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.config = config or WalkForwardConfig()
        self.gate = gate or SelectionGate()
        self.bidirectional = bidirectional or BidirectionalConfig()
        self._lab = HistoricalModeLab(config=self.config, gate=self.gate, modes=modes)

    @property
    def modes(self) -> tuple[HistoricalMode, ...]:
        return self._lab.modes

    def evaluate_direction(
        self,
        series: HistoricalSeries,
        direction: TemporalDirection,
    ) -> DirectionalEvaluation:
        if direction is TemporalDirection.FORWARD:
            oriented = series
        elif direction is TemporalDirection.BACKWARD:
            oriented = reverse_series(series)
        else:  # pragma: no cover - defensive against non-enum callers
            raise HistoricalModeError(
                "unsupported temporal direction",
                context={"reason": "invalid_direction", "direction": str(direction)},
            )
        return DirectionalEvaluation(direction=direction, report=self._lab.evaluate(oriented))

    def evaluate(self, series: HistoricalSeries) -> BidirectionalReport:
        """Evaluate and gate a model family in both temporal orientations."""

        forward = self.evaluate_direction(series, TemporalDirection.FORWARD)
        backward = self.evaluate_direction(series, TemporalDirection.BACKWARD)

        common_modes = _common_modes(forward.report, backward.report)
        consensus_ranking = tuple(
            sorted(
                common_modes,
                key=lambda mode: (
                    _consensus_score(mode, forward.report, backward.report),
                    0 if mode is HistoricalMode.PERSISTENCE else 1,
                    mode.value,
                ),
            )
        )
        candidate = consensus_ranking[0]
        decision = _decision(
            candidate=candidate,
            forward=forward.report,
            backward=backward.report,
            gate=self.gate,
            bidirectional=self.bidirectional,
        )
        fingerprint = _fingerprint(forward, backward, consensus_ranking, decision)
        return BidirectionalReport(
            forward=forward,
            backward=backward,
            consensus_ranking=consensus_ranking,
            decision=decision,
            fingerprint=fingerprint,
        )


def reverse_series(series: HistoricalSeries) -> HistoricalSeries:
    """Return a reverse-time mirror with a valid increasing clock.

    Values are reversed exactly.  When timestamps exist, intervals are reversed
    while the mirrored clock remains strictly increasing and retains the same
    first/last timestamp.  For example ``[0, 1, 3]`` becomes ``[0, 2, 3]``.
    Applying this function twice reconstructs the original timestamp sequence.
    """

    values = tuple(reversed(series.values))
    timestamps: tuple[float, ...] | None
    if series.timestamps is None:
        timestamps = None
    else:
        first = series.timestamps[0]
        last = series.timestamps[-1]
        timestamps = tuple(first + (last - timestamp) for timestamp in reversed(series.timestamps))
    return HistoricalSeries(
        values=values,
        timestamps=timestamps,
        label=f"{series.label}::backward",
    )


def _common_modes(
    forward: EvaluationReport,
    backward: EvaluationReport,
) -> tuple[HistoricalMode, ...]:
    forward_modes = {report.mode for report in forward.reports}
    backward_modes = {report.mode for report in backward.reports}
    common = tuple(sorted(forward_modes & backward_modes, key=lambda mode: mode.value))
    if HistoricalMode.PERSISTENCE not in common:
        raise HistoricalModeError(
            "persistence baseline is missing from bidirectional evaluation",
            context={"reason": "missing_baseline"},
        )
    if not common:
        raise HistoricalModeError(
            "forward and backward evaluations share no modes",
            context={"reason": "no_common_modes"},
        )
    return common


def _consensus_score(
    mode: HistoricalMode,
    forward: EvaluationReport,
    backward: EvaluationReport,
) -> float:
    """Symmetric combined score normalized against persistence in each pass."""

    forward_mode = forward.by_mode(mode).metrics.score()
    backward_mode = backward.by_mode(mode).metrics.score()
    forward_base = forward.by_mode(HistoricalMode.PERSISTENCE).metrics.score()
    backward_base = backward.by_mode(HistoricalMode.PERSISTENCE).metrics.score()
    return 0.5 * _safe_ratio(forward_mode, forward_base) + 0.5 * _safe_ratio(
        backward_mode, backward_base
    )


def _decision(
    *,
    candidate: HistoricalMode,
    forward: EvaluationReport,
    backward: EvaluationReport,
    gate: SelectionGate,
    bidirectional: BidirectionalConfig,
) -> BidirectionalDecision:
    baseline = HistoricalMode.PERSISTENCE
    forward_candidate = forward.by_mode(candidate)
    backward_candidate = backward.by_mode(candidate)
    forward_baseline = forward.by_mode(baseline)
    backward_baseline = backward.by_mode(baseline)

    forward_relative = _relative_improvement(
        forward_candidate.metrics.mae, forward_baseline.metrics.mae
    )
    backward_relative = _relative_improvement(
        backward_candidate.metrics.mae, backward_baseline.metrics.mae
    )
    forward_worst_ratio = _safe_ratio(
        forward_candidate.metrics.worst_absolute_error,
        forward_baseline.metrics.worst_absolute_error,
    )
    backward_worst_ratio = _safe_ratio(
        backward_candidate.metrics.worst_absolute_error,
        backward_baseline.metrics.worst_absolute_error,
    )
    mae_asymmetry = _relative_asymmetry(
        forward_candidate.metrics.mae,
        backward_candidate.metrics.mae,
    )
    forward_rank = _rank(forward, candidate)
    backward_rank = _rank(backward, candidate)

    reasons: list[str] = []
    if candidate is baseline:
        reasons.append("baseline_already_best")
    if forward_candidate.metrics.folds < gate.min_folds:
        reasons.append("forward_insufficient_folds")
    if backward_candidate.metrics.folds < gate.min_folds:
        reasons.append("backward_insufficient_folds")
    if candidate is not baseline and forward_relative < gate.min_relative_improvement:
        reasons.append("forward_insufficient_mae_improvement")
    if candidate is not baseline and backward_relative < gate.min_relative_improvement:
        reasons.append("backward_insufficient_mae_improvement")
    if forward_worst_ratio > gate.max_relative_worst_error:
        reasons.append("forward_worst_error_regression")
    if backward_worst_ratio > gate.max_relative_worst_error:
        reasons.append("backward_worst_error_regression")
    if mae_asymmetry > bidirectional.max_mae_asymmetry:
        reasons.append("temporal_mae_asymmetry")
    if forward_rank > bidirectional.max_direction_rank:
        reasons.append("weak_forward_rank")
    if backward_rank > bidirectional.max_direction_rank:
        reasons.append("weak_backward_rank")

    if gate.require_regime_coverage:
        if not _same_regime_coverage(forward_candidate, forward_baseline):
            reasons.append("forward_incomplete_regime_coverage")
        if not _same_regime_coverage(backward_candidate, backward_baseline):
            reasons.append("backward_incomplete_regime_coverage")

    accepted = candidate is not baseline and not reasons
    if accepted:
        reasons.append("bidirectional_gate_passed")

    return BidirectionalDecision(
        candidate=candidate,
        baseline=baseline,
        accepted=accepted,
        reasons=tuple(reasons),
        forward_relative_mae_improvement=forward_relative,
        backward_relative_mae_improvement=backward_relative,
        forward_worst_error_ratio=forward_worst_ratio,
        backward_worst_error_ratio=backward_worst_ratio,
        mae_asymmetry=mae_asymmetry,
        forward_rank=forward_rank,
        backward_rank=backward_rank,
    )


def _same_regime_coverage(candidate: ModeReport, baseline: ModeReport) -> bool:
    return {regime for regime, _ in candidate.regime_metrics} == {
        regime for regime, _ in baseline.regime_metrics
    }


def _rank(report: EvaluationReport, mode: HistoricalMode) -> int:
    try:
        return report.ranking.index(mode) + 1
    except ValueError as exc:  # pragma: no cover - common mode invariant
        raise HistoricalModeError(
            "candidate mode is absent from directional ranking",
            context={"reason": "unknown_mode", "mode": mode.value},
        ) from exc


def _relative_improvement(candidate_mae: float, baseline_mae: float) -> float:
    if baseline_mae <= _EPSILON:
        return 0.0 if candidate_mae <= _EPSILON else -math.inf
    return (baseline_mae - candidate_mae) / baseline_mae


def _relative_asymmetry(left: float, right: float) -> float:
    mean = 0.5 * (abs(left) + abs(right))
    if mean <= _EPSILON:
        return 0.0
    return abs(left - right) / mean


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= _EPSILON:
        return 0.0 if numerator <= _EPSILON else math.inf
    return numerator / denominator


def _fingerprint(
    forward: DirectionalEvaluation,
    backward: DirectionalEvaluation,
    ranking: Sequence[HistoricalMode],
    decision: BidirectionalDecision,
) -> str:
    payload = "|".join(
        (
            "bidirectional-v1",
            forward.report.fingerprint,
            backward.report.fingerprint,
            ",".join(mode.value for mode in ranking),
            decision.candidate.value,
            str(decision.accepted),
            format(decision.forward_relative_mae_improvement, ".17g"),
            format(decision.backward_relative_mae_improvement, ".17g"),
            format(decision.mae_asymmetry, ".17g"),
            str(decision.forward_rank),
            str(decision.backward_rank),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
