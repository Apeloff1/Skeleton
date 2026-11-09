"""Deterministic structural-regime diagnostics for Jeeves time series.

Longer history is not always better.  When the data-generating process changes,
a forecaster trained on the full archive can be systematically biased toward an
obsolete regime.  This module provides an inspectable changepoint diagnostic
based on three independent signals:

* level/mean displacement;
* local linear-trend displacement; and
* variance-ratio displacement.

It does not silently truncate training data or activate a new model.  Instead it
returns a fingerprinted report and an explicit recommended training start when a
strong, sufficiently recent break is detected.  A caller can then backtest the
full-history and post-break alternatives under the same forward window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Final

from skeleton.jeeves.historical_forecasting import (
    HistoricalForecastError,
    HistoricalSeries,
)
from skeleton.jeeves.historical_models import canonical_fingerprint


_EPSILON: Final = 1e-12
MAX_CANDIDATE_SPLITS: Final = 2_000


class HistoricalRegimeError(HistoricalForecastError):
    """Fail-closed structural-regime diagnostic error."""

    code = "JVS.HISTORICAL_REGIME"
    http_status = 422


@dataclass(frozen=True, slots=True)
class RegimeDetectionPolicy:
    minimum_segment_points: int = 8
    max_candidate_splits: int = 256
    mean_weight: float = 0.45
    slope_weight: float = 0.35
    variance_weight: float = 0.20
    change_threshold: float = 1.5
    recent_fraction: float = 0.35
    minimum_scale: float = 1e-8

    def __post_init__(self) -> None:
        if isinstance(self.minimum_segment_points, bool) or not isinstance(self.minimum_segment_points, int) or self.minimum_segment_points < 2:
            raise HistoricalRegimeError(
                "minimum_segment_points must be an integer of at least 2",
                context={"reason": "invalid_minimum_segment_points"},
            )
        if isinstance(self.max_candidate_splits, bool) or not isinstance(self.max_candidate_splits, int) or not 1 <= self.max_candidate_splits <= MAX_CANDIDATE_SPLITS:
            raise HistoricalRegimeError(
                "max_candidate_splits is out of range",
                context={"reason": "invalid_max_candidate_splits"},
            )
        weights = []
        for name in ("mean_weight", "slope_weight", "variance_weight"):
            value = _non_negative(name, getattr(self, name))
            weights.append(value)
            object.__setattr__(self, name, value)
        if sum(weights) <= _EPSILON:
            raise HistoricalRegimeError(
                "at least one regime signal weight must be positive",
                context={"reason": "zero_signal_weights"},
            )
        threshold = _positive("change_threshold", self.change_threshold)
        recent = _finite("recent_fraction", self.recent_fraction)
        if not 0.0 < recent <= 1.0:
            raise HistoricalRegimeError(
                "recent_fraction must be greater than 0 and at most 1",
                context={"reason": "invalid_recent_fraction"},
            )
        scale = _positive("minimum_scale", self.minimum_scale)
        object.__setattr__(self, "change_threshold", threshold)
        object.__setattr__(self, "recent_fraction", recent)
        object.__setattr__(self, "minimum_scale", scale)

    @property
    def normalized_signal_weights(self) -> tuple[float, float, float]:
        total = self.mean_weight + self.slope_weight + self.variance_weight
        return (
            self.mean_weight / total,
            self.slope_weight / total,
            self.variance_weight / total,
        )

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "minimum_segment_points": self.minimum_segment_points,
                "max_candidate_splits": self.max_candidate_splits,
                "mean_weight": self.mean_weight,
                "slope_weight": self.slope_weight,
                "variance_weight": self.variance_weight,
                "change_threshold": self.change_threshold,
                "recent_fraction": self.recent_fraction,
                "minimum_scale": self.minimum_scale,
            }
        )


@dataclass(frozen=True, slots=True)
class SegmentStatistics:
    start_index: int
    end_index: int
    count: int
    mean: float
    variance: float
    slope: float
    median: float
    mad: float


@dataclass(frozen=True, slots=True)
class RegimeCandidate:
    split_index: int
    pre: SegmentStatistics
    post: SegmentStatistics
    mean_effect: float
    slope_effect: float
    variance_effect: float
    score: float
    balance: float


@dataclass(frozen=True, slots=True)
class RegimeShiftReport:
    series_fingerprint: str
    policy_fingerprint: str
    candidate_count: int
    best: RegimeCandidate
    detected: bool
    recent: bool
    recommended_training_start: int
    report_fingerprint: str

    @property
    def recommended_post_break_points(self) -> int:
        return self.best.pre.count + self.best.post.count - self.recommended_training_start


class HistoricalRegimeDetector:
    """Search deterministic candidate splits for a structural break."""

    def __init__(self, policy: RegimeDetectionPolicy | None = None) -> None:
        self.policy = policy or RegimeDetectionPolicy()
        if not isinstance(self.policy, RegimeDetectionPolicy):
            raise HistoricalRegimeError(
                "policy must be RegimeDetectionPolicy",
                context={"reason": "invalid_policy"},
            )

    def analyze(self, series: HistoricalSeries) -> RegimeShiftReport:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalRegimeError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        minimum = self.policy.minimum_segment_points
        n = len(series.observations)
        if n < 2 * minimum:
            raise HistoricalRegimeError(
                "series is too short for two regime segments",
                context={
                    "reason": "insufficient_points",
                    "points": n,
                    "minimum_required": 2 * minimum,
                },
            )

        split_indices = list(range(minimum, n - minimum + 1))
        split_indices = _bounded_candidates(split_indices, self.policy.max_candidate_splits)
        candidates = tuple(self._candidate(series, split) for split in split_indices)
        if not candidates:
            raise HistoricalRegimeError(
                "no valid regime split candidates",
                context={"reason": "no_candidates"},
            )
        best = sorted(
            candidates,
            key=lambda item: (
                -item.score,
                -item.balance,
                -item.mean_effect,
                -item.slope_effect,
                item.split_index,
            ),
        )[0]
        detected = best.score + _EPSILON >= self.policy.change_threshold
        recent_boundary = n * (1.0 - self.policy.recent_fraction)
        recent = detected and best.split_index + _EPSILON >= recent_boundary
        recommended = best.split_index if recent else 0
        payload = {
            "series": series.fingerprint,
            "policy": self.policy.fingerprint,
            "candidate_count": len(candidates),
            "best": _candidate_payload(best),
            "detected": detected,
            "recent": recent,
            "recommended_training_start": recommended,
        }
        return RegimeShiftReport(
            series_fingerprint=series.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            candidate_count=len(candidates),
            best=best,
            detected=detected,
            recent=recent,
            recommended_training_start=recommended,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def recommended_series(
        self,
        series: HistoricalSeries,
        report: RegimeShiftReport | None = None,
    ) -> HistoricalSeries:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalRegimeError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        report = report or self.analyze(series)
        if not isinstance(report, RegimeShiftReport):
            raise HistoricalRegimeError(
                "report must be RegimeShiftReport",
                context={"reason": "invalid_report"},
            )
        if report.series_fingerprint != series.fingerprint:
            raise HistoricalRegimeError(
                "regime report does not belong to supplied series",
                context={"reason": "series_fingerprint_mismatch"},
            )
        start = report.recommended_training_start
        if start <= 0:
            return series
        observations = series.observations[start:]
        if len(observations) < self.policy.minimum_segment_points:
            raise HistoricalRegimeError(
                "recommended post-break series is unexpectedly too short",
                context={"reason": "post_break_too_short"},
            )
        return HistoricalSeries(
            series_id=f"{series.series_id}:regime:{start}",
            observations=observations,
        )

    def _candidate(self, series: HistoricalSeries, split: int) -> RegimeCandidate:
        values = series.values
        left = values[:split]
        right = values[split:]
        pre = _segment_statistics(left, start_index=0)
        post = _segment_statistics(right, start_index=split)
        robust_scale = _robust_scale(values, minimum=self.policy.minimum_scale)

        mean_effect = abs(post.mean - pre.mean) / robust_scale
        comparable_span = float(min(pre.count, post.count))
        slope_effect = abs(post.slope - pre.slope) * comparable_span / robust_scale
        variance_effect = abs(
            math.log((post.variance + self.policy.minimum_scale**2) / (pre.variance + self.policy.minimum_scale**2))
        )
        mean_weight, slope_weight, variance_weight = self.policy.normalized_signal_weights
        raw_score = (
            mean_weight * mean_effect
            + slope_weight * slope_effect
            + variance_weight * variance_effect
        )
        balance = 2.0 * min(pre.count, post.count) / (pre.count + post.count)
        # Mild balance adjustment avoids edge splits dominating solely because a
        # tiny segment has noisy variance/slope estimates while still allowing a
        # true recent break to win.
        score = raw_score * math.sqrt(balance)
        return RegimeCandidate(
            split_index=split,
            pre=pre,
            post=post,
            mean_effect=mean_effect,
            slope_effect=slope_effect,
            variance_effect=variance_effect,
            score=score,
            balance=balance,
        )



def summarize_regime_shift(report: RegimeShiftReport) -> dict[str, object]:
    return {
        "detected": report.detected,
        "recent": report.recent,
        "recommended_training_start": report.recommended_training_start,
        "candidate_count": report.candidate_count,
        "score": report.best.score,
        "change_threshold": None,
        "split_index": report.best.split_index,
        "mean_effect": report.best.mean_effect,
        "slope_effect": report.best.slope_effect,
        "variance_effect": report.best.variance_effect,
        "pre": _stats_payload(report.best.pre),
        "post": _stats_payload(report.best.post),
        "series_fingerprint": report.series_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }



def _segment_statistics(values: tuple[float, ...], *, start_index: int) -> SegmentStatistics:
    if len(values) < 2:
        raise HistoricalRegimeError(
            "segment requires at least two values",
            context={"reason": "segment_too_short"},
        )
    count = len(values)
    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / count
    slope = _linear_slope(values)
    med = median(values)
    mad = median(abs(value - med) for value in values)
    return SegmentStatistics(
        start_index=start_index,
        end_index=start_index + count,
        count=count,
        mean=mean,
        variance=variance,
        slope=slope,
        median=med,
        mad=mad,
    )



def _linear_slope(values: tuple[float, ...]) -> float:
    count = len(values)
    mean_x = (count - 1) / 2.0
    mean_y = sum(values) / count
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    if denominator <= _EPSILON:
        return 0.0
    return numerator / denominator



def _robust_scale(values: tuple[float, ...], *, minimum: float) -> float:
    med = median(values)
    mad = median(abs(value - med) for value in values)
    # 1.4826 scales normal-distribution MAD to sigma, while the fallbacks keep
    # the effect size finite for constant or near-constant histories.
    scale = 1.4826 * mad
    if scale <= minimum:
        mean = sum(values) / len(values)
        std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        scale = std
    if scale <= minimum:
        magnitude = median(abs(value) for value in values)
        scale = max(minimum, magnitude, 1.0)
    return scale



def _bounded_candidates(indices: list[int], maximum: int) -> list[int]:
    if len(indices) <= maximum:
        return indices
    if maximum == 1:
        return [indices[len(indices) // 2]]
    selected: list[int] = []
    last_position = len(indices) - 1
    for slot in range(maximum):
        position = round(slot * last_position / (maximum - 1))
        value = indices[position]
        if not selected or selected[-1] != value:
            selected.append(value)
    return selected



def _candidate_payload(candidate: RegimeCandidate) -> dict[str, object]:
    return {
        "split_index": candidate.split_index,
        "score": candidate.score,
        "balance": candidate.balance,
        "mean_effect": candidate.mean_effect,
        "slope_effect": candidate.slope_effect,
        "variance_effect": candidate.variance_effect,
        "pre": _stats_payload(candidate.pre),
        "post": _stats_payload(candidate.post),
    }



def _stats_payload(stats: SegmentStatistics) -> dict[str, object]:
    return {
        "start_index": stats.start_index,
        "end_index": stats.end_index,
        "count": stats.count,
        "mean": stats.mean,
        "variance": stats.variance,
        "slope": stats.slope,
        "median": stats.median,
        "mad": stats.mad,
    }



def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalRegimeError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalRegimeError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return numeric



def _non_negative(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric < 0.0:
        raise HistoricalRegimeError(
            f"{name} must be non-negative",
            context={"reason": "invalid_non_negative", "field": name},
        )
    return numeric



def _positive(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric <= 0.0:
        raise HistoricalRegimeError(
            f"{name} must be positive",
            context={"reason": "invalid_positive", "field": name},
        )
    return numeric