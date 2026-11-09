"""Cross-direction calibration and disagreement diagnostics for Jeeves.

The bidirectional historical lab establishes a strong first boundary: a mode must
survive independent forward and reverse-time walk-forward evaluation.  This
module adds a second boundary for *agreement quality*.  A mode can look good on
average in both directions while relying on very different error tails, bias,
or rank position.  Those disagreements are useful evidence and must not be
hidden by a single combined score.

The calibration layer is deterministic, offline-only, and does not mutate
learning state.  It never changes the directional forecasts produced by
``BidirectionalModeLab``.  It can only preserve a promotion or veto it.

Diagnostics include:

* Spearman rank agreement across all common modes;
* top-K overlap between directional rankings;
* candidate rank gap and normalized score gap;
* median and p90 absolute-error asymmetry;
* normalized absolute-bias asymmetry;
* directional-accuracy disagreement when both sides expose the metric;
* same-target paired absolute-error disagreement, mapping reverse-time fold
  indices back into original-series coordinates.

The same-target pairing is deliberately descriptive.  A forward fold predicts
an observation from its historical prefix while a backward fold predicts that
same observation from a future suffix in original coordinates.  Agreement is
therefore a robustness signal, not evidence that causality is reversible.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .bidirectional_modes import (
    BidirectionalConfig,
    BidirectionalModeLab,
    BidirectionalReport,
)
from .historical_modes import (
    EvaluationReport,
    FoldResult,
    HistoricalMode,
    HistoricalModeError,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
)

_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class CrossDirectionConfig:
    """Fail-closed thresholds for cross-direction agreement.

    Thresholds intentionally describe diagnostics rather than statistical
    significance.  They are deterministic engineering gates over a supplied
    historical fixture, not population-level claims.
    """

    top_k: int = 4
    min_rank_correlation: float = 0.20
    min_top_k_overlap: float = 0.50
    max_candidate_rank_gap: int = 3
    max_normalized_score_gap: float = 1.00
    max_p90_error_asymmetry: float = 1.00
    max_bias_ratio_asymmetry: float = 1.25
    max_directional_accuracy_gap: float = 0.50
    min_paired_targets: int = 4
    max_paired_error_asymmetry: float = 1.50

    def __post_init__(self) -> None:
        _positive_int("top_k", self.top_k)
        _closed_interval("min_rank_correlation", self.min_rank_correlation, -1.0, 1.0)
        _closed_interval("min_top_k_overlap", self.min_top_k_overlap, 0.0, 1.0)
        _non_negative_int("max_candidate_rank_gap", self.max_candidate_rank_gap)
        _non_negative("max_normalized_score_gap", self.max_normalized_score_gap)
        _non_negative("max_p90_error_asymmetry", self.max_p90_error_asymmetry)
        _non_negative("max_bias_ratio_asymmetry", self.max_bias_ratio_asymmetry)
        _closed_interval(
            "max_directional_accuracy_gap",
            self.max_directional_accuracy_gap,
            0.0,
            1.0,
        )
        _non_negative_int("min_paired_targets", self.min_paired_targets)
        _non_negative("max_paired_error_asymmetry", self.max_paired_error_asymmetry)


@dataclass(frozen=True, slots=True)
class RankingAgreement:
    """Global agreement between forward and backward model orderings."""

    common_modes: int
    spearman_rank_correlation: float
    mean_absolute_rank_gap: float
    top_k: int
    top_k_overlap: float


@dataclass(frozen=True, slots=True)
class ModeCalibration:
    """Cross-direction diagnostics for one historical mode."""

    mode: HistoricalMode
    forward_rank: int
    backward_rank: int
    rank_gap: int
    forward_normalized_score: float
    backward_normalized_score: float
    normalized_score_gap: float
    forward_mae: float
    backward_mae: float
    mae_asymmetry: float
    forward_median_absolute_error: float
    backward_median_absolute_error: float
    median_error_asymmetry: float
    forward_p90_absolute_error: float
    backward_p90_absolute_error: float
    p90_error_asymmetry: float
    forward_absolute_bias_ratio: float
    backward_absolute_bias_ratio: float
    bias_ratio_asymmetry: float
    directional_accuracy_gap: float | None
    paired_targets: int
    paired_mean_absolute_error_gap: float | None
    paired_error_asymmetry: float | None
    paired_absolute_error_correlation: float | None


@dataclass(frozen=True, slots=True)
class CalibrationDecision:
    """Final calibration veto/preserve decision layered over bidirectional gate."""

    candidate: HistoricalMode
    baseline: HistoricalMode
    base_bidirectional_accepted: bool
    accepted: bool
    reasons: tuple[str, ...]
    ranking: RankingAgreement
    candidate_diagnostics: ModeCalibration


@dataclass(frozen=True, slots=True)
class CalibratedBidirectionalReport:
    """Bidirectional report plus cross-direction calibration evidence."""

    base: BidirectionalReport
    ranking_agreement: RankingAgreement
    diagnostics: tuple[ModeCalibration, ...]
    decision: CalibrationDecision
    fingerprint: str

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.decision.candidate if self.decision.accepted else self.decision.baseline

    def by_mode(self, mode: HistoricalMode) -> ModeCalibration:
        for diagnostic in self.diagnostics:
            if diagnostic.mode is mode:
                return diagnostic
        raise HistoricalModeError(
            "requested mode is absent from cross-direction diagnostics",
            context={"reason": "unknown_mode", "mode": mode.value},
        )

    def as_payload(self) -> dict[str, object]:
        """Compact finite/nullable payload suitable for evidence recording."""

        diagnostic = self.decision.candidate_diagnostics
        return {
            "selected_mode": self.selected_mode.value,
            "calibration_accepted": self.decision.accepted,
            "base_bidirectional_accepted": self.decision.base_bidirectional_accepted,
            "rank_correlation": self.ranking_agreement.spearman_rank_correlation,
            "top_k_overlap": self.ranking_agreement.top_k_overlap,
            "candidate_rank_gap": diagnostic.rank_gap,
            "candidate_p90_error_asymmetry": diagnostic.p90_error_asymmetry,
            "candidate_paired_targets": diagnostic.paired_targets,
            "candidate_paired_error_asymmetry": _finite_or_none(
                diagnostic.paired_error_asymmetry
            ),
            "fingerprint": self.fingerprint,
        }


class CalibratedBidirectionalModeLab:
    """Run bidirectional evaluation and veto temporally inconsistent promotion."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        bidirectional: BidirectionalConfig | None = None,
        calibration: CrossDirectionConfig | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.calibration = calibration or CrossDirectionConfig()
        self._lab = BidirectionalModeLab(
            config=config,
            gate=gate,
            bidirectional=bidirectional,
            modes=modes,
        )

    @property
    def modes(self) -> tuple[HistoricalMode, ...]:
        return self._lab.modes

    def evaluate(self, series: HistoricalSeries) -> CalibratedBidirectionalReport:
        base = self._lab.evaluate(series)
        ranking = _ranking_agreement(base, self.calibration.top_k)
        diagnostics = tuple(
            _mode_calibration(base, mode, len(series.values))
            for mode in base.consensus_ranking
        )
        candidate = base.decision.candidate
        candidate_diagnostics = _diagnostic_by_mode(diagnostics, candidate)
        decision = _calibration_decision(
            base=base,
            ranking=ranking,
            candidate=candidate_diagnostics,
            config=self.calibration,
        )
        fingerprint = _fingerprint(base, ranking, diagnostics, decision, self.calibration)
        return CalibratedBidirectionalReport(
            base=base,
            ranking_agreement=ranking,
            diagnostics=diagnostics,
            decision=decision,
            fingerprint=fingerprint,
        )


def _ranking_agreement(report: BidirectionalReport, top_k: int) -> RankingAgreement:
    forward = report.forward.report.ranking
    backward = report.backward.report.ranking
    common = tuple(mode for mode in forward if mode in set(backward))
    if not common:
        raise HistoricalModeError(
            "directional rankings share no common modes",
            context={"reason": "no_common_modes"},
        )

    forward_rank = {mode: index + 1 for index, mode in enumerate(forward) if mode in common}
    backward_rank = {mode: index + 1 for index, mode in enumerate(backward) if mode in common}
    gaps = [abs(forward_rank[mode] - backward_rank[mode]) for mode in common]
    correlation = _spearman_unique(
        [forward_rank[mode] for mode in common],
        [backward_rank[mode] for mode in common],
    )

    actual_k = min(top_k, len(common))
    forward_top = set(forward[:actual_k])
    backward_top = set(backward[:actual_k])
    overlap = len(forward_top & backward_top) / actual_k

    return RankingAgreement(
        common_modes=len(common),
        spearman_rank_correlation=correlation,
        mean_absolute_rank_gap=statistics.fmean(gaps),
        top_k=actual_k,
        top_k_overlap=overlap,
    )


def _mode_calibration(
    report: BidirectionalReport,
    mode: HistoricalMode,
    series_size: int,
) -> ModeCalibration:
    forward_report = report.forward.report
    backward_report = report.backward.report
    forward = forward_report.by_mode(mode)
    backward = backward_report.by_mode(mode)
    forward_base = forward_report.by_mode(HistoricalMode.PERSISTENCE)
    backward_base = backward_report.by_mode(HistoricalMode.PERSISTENCE)

    forward_rank = _rank(forward_report, mode)
    backward_rank = _rank(backward_report, mode)

    forward_score = _safe_ratio(forward.metrics.score(), forward_base.metrics.score())
    backward_score = _safe_ratio(backward.metrics.score(), backward_base.metrics.score())
    normalized_score_gap = _extended_absolute_gap(forward_score, backward_score)

    forward_absolute = tuple(fold.absolute_error for fold in forward.folds)
    backward_absolute = tuple(fold.absolute_error for fold in backward.folds)
    forward_median = _quantile(forward_absolute, 0.50)
    backward_median = _quantile(backward_absolute, 0.50)
    forward_p90 = _quantile(forward_absolute, 0.90)
    backward_p90 = _quantile(backward_absolute, 0.90)

    forward_bias_ratio = abs(forward.metrics.bias) / max(forward.metrics.mae, _EPSILON)
    backward_bias_ratio = abs(backward.metrics.bias) / max(backward.metrics.mae, _EPSILON)

    directional_gap: float | None
    if (
        forward.metrics.directional_accuracy is None
        or backward.metrics.directional_accuracy is None
    ):
        directional_gap = None
    else:
        directional_gap = abs(
            forward.metrics.directional_accuracy - backward.metrics.directional_accuracy
        )

    paired_forward, paired_backward = _paired_absolute_errors(
        forward.folds,
        backward.folds,
        series_size,
    )
    paired_count = len(paired_forward)
    if paired_count:
        paired_gap = statistics.fmean(
            abs(left - right) for left, right in zip(paired_forward, paired_backward)
        )
        paired_scale = statistics.fmean(
            0.5 * (left + right) for left, right in zip(paired_forward, paired_backward)
        )
        paired_asymmetry = 0.0 if paired_scale <= _EPSILON else paired_gap / paired_scale
        paired_correlation = _pearson(paired_forward, paired_backward)
    else:
        paired_gap = None
        paired_asymmetry = None
        paired_correlation = None

    return ModeCalibration(
        mode=mode,
        forward_rank=forward_rank,
        backward_rank=backward_rank,
        rank_gap=abs(forward_rank - backward_rank),
        forward_normalized_score=forward_score,
        backward_normalized_score=backward_score,
        normalized_score_gap=normalized_score_gap,
        forward_mae=forward.metrics.mae,
        backward_mae=backward.metrics.mae,
        mae_asymmetry=_relative_asymmetry(forward.metrics.mae, backward.metrics.mae),
        forward_median_absolute_error=forward_median,
        backward_median_absolute_error=backward_median,
        median_error_asymmetry=_relative_asymmetry(forward_median, backward_median),
        forward_p90_absolute_error=forward_p90,
        backward_p90_absolute_error=backward_p90,
        p90_error_asymmetry=_relative_asymmetry(forward_p90, backward_p90),
        forward_absolute_bias_ratio=forward_bias_ratio,
        backward_absolute_bias_ratio=backward_bias_ratio,
        bias_ratio_asymmetry=_relative_asymmetry(forward_bias_ratio, backward_bias_ratio),
        directional_accuracy_gap=directional_gap,
        paired_targets=paired_count,
        paired_mean_absolute_error_gap=paired_gap,
        paired_error_asymmetry=paired_asymmetry,
        paired_absolute_error_correlation=paired_correlation,
    )


def _calibration_decision(
    *,
    base: BidirectionalReport,
    ranking: RankingAgreement,
    candidate: ModeCalibration,
    config: CrossDirectionConfig,
) -> CalibrationDecision:
    reasons: list[str] = []

    if not base.decision.accepted:
        reasons.append("base_bidirectional_gate_rejected")
    if ranking.spearman_rank_correlation < config.min_rank_correlation:
        reasons.append("weak_global_rank_agreement")
    if ranking.top_k_overlap < config.min_top_k_overlap:
        reasons.append("weak_top_k_overlap")
    if candidate.rank_gap > config.max_candidate_rank_gap:
        reasons.append("candidate_rank_instability")
    if candidate.normalized_score_gap > config.max_normalized_score_gap:
        reasons.append("candidate_score_asymmetry")
    if candidate.p90_error_asymmetry > config.max_p90_error_asymmetry:
        reasons.append("candidate_tail_error_asymmetry")
    if candidate.bias_ratio_asymmetry > config.max_bias_ratio_asymmetry:
        reasons.append("candidate_bias_asymmetry")
    if (
        candidate.directional_accuracy_gap is not None
        and candidate.directional_accuracy_gap > config.max_directional_accuracy_gap
    ):
        reasons.append("candidate_directional_accuracy_disagreement")
    if candidate.paired_targets < config.min_paired_targets:
        reasons.append("insufficient_paired_targets")
    elif (
        candidate.paired_error_asymmetry is not None
        and candidate.paired_error_asymmetry > config.max_paired_error_asymmetry
    ):
        reasons.append("candidate_paired_error_asymmetry")

    accepted = base.decision.accepted and not reasons
    if accepted:
        reasons.append("cross_direction_calibration_passed")

    return CalibrationDecision(
        candidate=base.decision.candidate,
        baseline=base.decision.baseline,
        base_bidirectional_accepted=base.decision.accepted,
        accepted=accepted,
        reasons=tuple(reasons),
        ranking=ranking,
        candidate_diagnostics=candidate,
    )


def _paired_absolute_errors(
    forward: Sequence[FoldResult],
    backward: Sequence[FoldResult],
    series_size: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Pair folds that target the same observation in original coordinates."""

    if series_size <= 0:
        raise HistoricalModeError(
            "series_size must be positive for directional pairing",
            context={"reason": "invalid_series_size"},
        )
    forward_by_target = {fold.target_index: fold.absolute_error for fold in forward}
    backward_by_target = {
        series_size - 1 - fold.target_index: fold.absolute_error for fold in backward
    }
    targets = sorted(set(forward_by_target) & set(backward_by_target))
    return (
        tuple(forward_by_target[target] for target in targets),
        tuple(backward_by_target[target] for target in targets),
    )


def _diagnostic_by_mode(
    diagnostics: Sequence[ModeCalibration],
    mode: HistoricalMode,
) -> ModeCalibration:
    for diagnostic in diagnostics:
        if diagnostic.mode is mode:
            return diagnostic
    raise HistoricalModeError(
        "candidate is absent from cross-direction diagnostics",
        context={"reason": "unknown_mode", "mode": mode.value},
    )


def _rank(report: EvaluationReport, mode: HistoricalMode) -> int:
    try:
        return report.ranking.index(mode) + 1
    except ValueError as exc:
        raise HistoricalModeError(
            "mode is absent from directional ranking",
            context={"reason": "unknown_mode", "mode": mode.value},
        ) from exc


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise HistoricalModeError(
            "cannot compute error quantile without folds",
            context={"reason": "no_folds"},
        )
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _spearman_unique(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right) or not left:
        raise HistoricalModeError(
            "rank vectors must be equally sized and non-empty",
            context={"reason": "invalid_rank_vectors"},
        )
    count = len(left)
    if count == 1:
        return 1.0
    sum_squared = sum((a - b) ** 2 for a, b in zip(left, right))
    return 1.0 - (6.0 * sum_squared) / (count * (count * count - 1))


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    left_ss = sum((value - mean_left) ** 2 for value in left)
    right_ss = sum((value - mean_right) ** 2 for value in right)
    if left_ss <= _EPSILON or right_ss <= _EPSILON:
        return None
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left, right)
    )
    value = numerator / math.sqrt(left_ss * right_ss)
    return max(-1.0, min(1.0, value))


def _relative_asymmetry(left: float, right: float) -> float:
    scale = 0.5 * (abs(left) + abs(right))
    if scale <= _EPSILON:
        return 0.0
    return abs(left - right) / scale


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= _EPSILON:
        return 0.0 if numerator <= _EPSILON else math.inf
    return numerator / denominator


def _extended_absolute_gap(left: float, right: float) -> float:
    if math.isinf(left) and math.isinf(right):
        return 0.0
    if not math.isfinite(left) or not math.isfinite(right):
        return math.inf
    return abs(left - right)


def _fingerprint(
    base: BidirectionalReport,
    ranking: RankingAgreement,
    diagnostics: Sequence[ModeCalibration],
    decision: CalibrationDecision,
    config: CrossDirectionConfig,
) -> str:
    parts = [
        "cross-direction-calibration-v1",
        base.fingerprint,
        repr(config),
        format(ranking.spearman_rank_correlation, ".17g"),
        format(ranking.top_k_overlap, ".17g"),
        decision.candidate.value,
        str(decision.accepted),
        ",".join(decision.reasons),
    ]
    for diagnostic in diagnostics:
        parts.extend(
            (
                diagnostic.mode.value,
                str(diagnostic.forward_rank),
                str(diagnostic.backward_rank),
                format(diagnostic.mae_asymmetry, ".17g"),
                format(diagnostic.p90_error_asymmetry, ".17g"),
                format(diagnostic.bias_ratio_asymmetry, ".17g"),
                str(diagnostic.paired_targets),
                _format_optional(diagnostic.paired_error_asymmetry),
                _format_optional(diagnostic.paired_absolute_error_correlation),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _format_optional(value: float | None) -> str:
    return "none" if value is None else format(value, ".17g")


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalModeError(
            f"{name} must be a non-negative integer",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    return value


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise HistoricalModeError(
            f"{name} must be a non-negative finite number",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HistoricalModeError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_cross_direction_gate", "field": name},
        )
    return number
