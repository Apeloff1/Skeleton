"""Distributional calibration diagnostics for Jeeves probabilistic forecasts.

A predictive system should be judged on more than point error. This module measures
whether realized outcomes behave like draws from the forecast distributions:
probability integral transform (PIT), empirical interval coverage, quantile loss,
sharpness, and sequential calibration drift.

All diagnostics operate on already-produced forecasts and realized targets. They
never mutate model state or feed a target back into the forecast that produced it.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from .probabilistic_ensemble import MixtureForecast, probability_integral_transform
from .probabilistic_state_space import GaussianForecast, StateSpaceError

_EPSILON = 1e-12
_DEFAULT_LEVELS = (0.50, 0.80, 0.90, 0.95)


@dataclass(frozen=True, slots=True)
class DistributionObservation:
    """One immutable predictive distribution paired with its realized target."""

    forecast: MixtureForecast
    actual: float
    target_index: int

    def __post_init__(self) -> None:
        _finite("actual", self.actual)
        if isinstance(self.target_index, bool) or not isinstance(self.target_index, int) or self.target_index < 0:
            raise StateSpaceError(
                "target_index must be a non-negative integer",
                context={"reason": "invalid_calibration_observation"},
            )


@dataclass(frozen=True, slots=True)
class CoverageDiagnostic:
    level: float
    expected: float
    empirical: float
    absolute_gap: float
    average_width: float
    median_width: float
    average_pinball_loss: float


@dataclass(frozen=True, slots=True)
class PitDiagnostic:
    count: int
    mean: float
    variance: float
    ks_distance: float
    lower_tail_rate: float
    upper_tail_rate: float
    histogram: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DriftEvent:
    """Sequential CUSUM calibration-drift event."""

    target_index: int
    direction: str
    statistic: float
    pit: float


@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    levels: tuple[float, ...] = _DEFAULT_LEVELS
    pit_bins: int = 10
    tail_probability: float = 0.05
    drift_reference: float = 0.20
    drift_threshold: float = 4.0
    quantile_tolerance: float = 1e-9
    quantile_iterations: int = 100

    def __post_init__(self) -> None:
        if not self.levels:
            raise StateSpaceError(
                "at least one calibration level is required",
                context={"reason": "invalid_calibration_config"},
            )
        if len(set(self.levels)) != len(self.levels):
            raise StateSpaceError(
                "calibration levels must be unique",
                context={"reason": "invalid_calibration_config"},
            )
        for level in self.levels:
            _open_interval("level", level, 0.0, 1.0)
        if isinstance(self.pit_bins, bool) or not isinstance(self.pit_bins, int) or self.pit_bins < 2:
            raise StateSpaceError(
                "pit_bins must be an integer >= 2",
                context={"reason": "invalid_calibration_config", "field": "pit_bins"},
            )
        _open_interval("tail_probability", self.tail_probability, 0.0, 0.5)
        _non_negative("drift_reference", self.drift_reference)
        _positive("drift_threshold", self.drift_threshold)
        _positive("quantile_tolerance", self.quantile_tolerance)
        if isinstance(self.quantile_iterations, bool) or not isinstance(self.quantile_iterations, int) or self.quantile_iterations < 10:
            raise StateSpaceError(
                "quantile_iterations must be an integer >= 10",
                context={"reason": "invalid_calibration_config", "field": "quantile_iterations"},
            )


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    config: CalibrationConfig
    observations: int
    pit: PitDiagnostic
    coverage: tuple[CoverageDiagnostic, ...]
    mean_log_score: float
    mean_crps: float
    drift_events: tuple[DriftEvent, ...]
    calibration_score: float
    fingerprint: str

    @property
    def drift_detected(self) -> bool:
        return bool(self.drift_events)

    def coverage_for(self, level: float) -> CoverageDiagnostic:
        for diagnostic in self.coverage:
            if abs(diagnostic.level - level) <= 1e-12:
                return diagnostic
        raise StateSpaceError(
            "requested calibration level is absent",
            context={"reason": "missing_calibration_level", "level": level},
        )


def calibrate_distributions(
    observations: Sequence[DistributionObservation],
    *,
    config: CalibrationConfig | None = None,
) -> CalibrationReport:
    """Compute deterministic calibration diagnostics over forecast/target pairs."""

    actual_config = config or CalibrationConfig()
    if not observations:
        raise StateSpaceError(
            "calibration requires at least one observation",
            context={"reason": "empty_calibration_set"},
        )

    ordered = tuple(sorted(observations, key=lambda item: item.target_index))
    if len({item.target_index for item in ordered}) != len(ordered):
        raise StateSpaceError(
            "calibration target indices must be unique",
            context={"reason": "duplicate_target_index"},
        )

    pits = tuple(probability_integral_transform(item.forecast, item.actual) for item in ordered)
    pit = _pit_diagnostic(pits, actual_config)
    coverage = tuple(
        _coverage_diagnostic(ordered, level, actual_config)
        for level in actual_config.levels
    )
    mean_log_score = statistics.fmean(item.forecast.log_density(item.actual) for item in ordered)
    mean_crps = statistics.fmean(item.forecast.crps(item.actual) for item in ordered)
    drift_events = _cusum_drift(ordered, pits, actual_config)

    # A bounded, interpretable lower-is-better aggregate transformed to [0, 1].
    coverage_gap = statistics.fmean(item.absolute_gap for item in coverage)
    pit_mean_gap = abs(pit.mean - 0.5) * 2.0
    pit_variance_gap = abs(pit.variance - (1.0 / 12.0)) / (1.0 / 12.0)
    ks_penalty = min(1.0, pit.ks_distance)
    drift_penalty = min(1.0, len(drift_events) / max(1.0, len(ordered) / 20.0))
    raw_penalty = (
        0.35 * min(1.0, coverage_gap)
        + 0.20 * min(1.0, pit_mean_gap)
        + 0.20 * min(1.0, pit_variance_gap)
        + 0.20 * ks_penalty
        + 0.05 * drift_penalty
    )
    calibration_score = max(0.0, min(1.0, 1.0 - raw_penalty))

    fingerprint = _report_fingerprint(
        config=actual_config,
        ordered=ordered,
        pits=pits,
        coverage=coverage,
        mean_log_score=mean_log_score,
        mean_crps=mean_crps,
        drift_events=drift_events,
        calibration_score=calibration_score,
    )
    return CalibrationReport(
        config=actual_config,
        observations=len(ordered),
        pit=pit,
        coverage=coverage,
        mean_log_score=mean_log_score,
        mean_crps=mean_crps,
        drift_events=drift_events,
        calibration_score=calibration_score,
        fingerprint=fingerprint,
    )


def mixture_cdf(forecast: MixtureForecast, value: float) -> float:
    """Evaluate a finite Gaussian-mixture CDF."""

    value = _finite("value", value)
    total = 0.0
    for component in forecast.components:
        sigma = math.sqrt(component.forecast.variance)
        z = (value - component.forecast.mean) / sigma
        total += component.weight * _normal_cdf(z)
    return min(1.0, max(0.0, total))


def mixture_quantile(
    forecast: MixtureForecast,
    probability: float,
    *,
    tolerance: float = 1e-9,
    max_iterations: int = 100,
) -> float:
    """Deterministically invert a Gaussian-mixture CDF using bracketed bisection."""

    probability = _closed_interval("probability", probability, 0.0, 1.0)
    tolerance = _positive("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 10:
        raise StateSpaceError(
            "max_iterations must be an integer >= 10",
            context={"reason": "invalid_quantile_config"},
        )

    means = [component.forecast.mean for component in forecast.components]
    sigmas = [math.sqrt(component.forecast.variance) for component in forecast.components]
    lower = min(mean - 12.0 * sigma for mean, sigma in zip(means, sigmas))
    upper = max(mean + 12.0 * sigma for mean, sigma in zip(means, sigmas))

    if probability <= 0.0:
        return lower
    if probability >= 1.0:
        return upper

    for _ in range(max_iterations):
        midpoint = 0.5 * (lower + upper)
        cdf = mixture_cdf(forecast, midpoint)
        if abs(cdf - probability) <= tolerance or upper - lower <= tolerance:
            return midpoint
        if cdf < probability:
            lower = midpoint
        else:
            upper = midpoint
    return 0.5 * (lower + upper)


def central_interval(
    forecast: MixtureForecast,
    level: float,
    *,
    tolerance: float = 1e-9,
    max_iterations: int = 100,
) -> tuple[float, float]:
    """Return an equal-tail central interval for a Gaussian mixture."""

    level = _open_interval("level", level, 0.0, 1.0)
    alpha = 1.0 - level
    lower = mixture_quantile(
        forecast,
        0.5 * alpha,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
    upper = mixture_quantile(
        forecast,
        1.0 - 0.5 * alpha,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
    return lower, upper


def pinball_loss(actual: float, quantile: float, probability: float) -> float:
    """Quantile (pinball) loss."""

    actual = _finite("actual", actual)
    quantile = _finite("quantile", quantile)
    probability = _closed_interval("probability", probability, 0.0, 1.0)
    error = actual - quantile
    return probability * error if error >= 0.0 else (probability - 1.0) * error


def gaussian_as_mixture(forecast: GaussianForecast, family) -> MixtureForecast:
    """Compatibility helper used by callers that have one Gaussian forecast.

    ``family`` is deliberately passed through to ``WeightedForecast`` without a
    concrete annotation here to avoid inventing a second family enum.
    """

    from .probabilistic_ensemble import WeightedForecast

    return MixtureForecast(
        horizon=forecast.horizon,
        components=(WeightedForecast(family=family, weight=1.0, forecast=forecast),),
    )


def _pit_diagnostic(pits: Sequence[float], config: CalibrationConfig) -> PitDiagnostic:
    ordered = sorted(pits)
    count = len(ordered)
    mean = statistics.fmean(ordered)
    variance = statistics.pvariance(ordered) if count > 1 else 0.0

    d_plus = max((index + 1) / count - value for index, value in enumerate(ordered))
    d_minus = max(value - index / count for index, value in enumerate(ordered))
    ks_distance = max(d_plus, d_minus)

    lower_tail_rate = sum(value <= config.tail_probability for value in pits) / count
    upper_tail_rate = sum(value >= 1.0 - config.tail_probability for value in pits) / count
    histogram = [0] * config.pit_bins
    for value in pits:
        index = min(config.pit_bins - 1, int(value * config.pit_bins))
        histogram[index] += 1

    return PitDiagnostic(
        count=count,
        mean=mean,
        variance=variance,
        ks_distance=ks_distance,
        lower_tail_rate=lower_tail_rate,
        upper_tail_rate=upper_tail_rate,
        histogram=tuple(histogram),
    )


def _coverage_diagnostic(
    observations: Sequence[DistributionObservation],
    level: float,
    config: CalibrationConfig,
) -> CoverageDiagnostic:
    alpha = 1.0 - level
    lower_probability = 0.5 * alpha
    upper_probability = 1.0 - 0.5 * alpha
    covered: list[float] = []
    widths: list[float] = []
    losses: list[float] = []

    for item in observations:
        lower = mixture_quantile(
            item.forecast,
            lower_probability,
            tolerance=config.quantile_tolerance,
            max_iterations=config.quantile_iterations,
        )
        upper = mixture_quantile(
            item.forecast,
            upper_probability,
            tolerance=config.quantile_tolerance,
            max_iterations=config.quantile_iterations,
        )
        covered.append(1.0 if lower <= item.actual <= upper else 0.0)
        widths.append(upper - lower)
        losses.append(pinball_loss(item.actual, lower, lower_probability))
        losses.append(pinball_loss(item.actual, upper, upper_probability))

    empirical = statistics.fmean(covered)
    return CoverageDiagnostic(
        level=level,
        expected=level,
        empirical=empirical,
        absolute_gap=abs(empirical - level),
        average_width=statistics.fmean(widths),
        median_width=float(statistics.median(widths)),
        average_pinball_loss=statistics.fmean(losses),
    )


def _cusum_drift(
    observations: Sequence[DistributionObservation],
    pits: Sequence[float],
    config: CalibrationConfig,
) -> tuple[DriftEvent, ...]:
    positive = 0.0
    negative = 0.0
    events: list[DriftEvent] = []

    # Centered PIT residuals have expectation zero when calibrated.
    for item, pit in zip(observations, pits):
        residual = 2.0 * (pit - 0.5)
        positive = max(0.0, positive + residual - config.drift_reference)
        negative = min(0.0, negative + residual + config.drift_reference)
        if positive >= config.drift_threshold:
            events.append(
                DriftEvent(
                    target_index=item.target_index,
                    direction="high",
                    statistic=positive,
                    pit=pit,
                )
            )
            positive = 0.0
        if negative <= -config.drift_threshold:
            events.append(
                DriftEvent(
                    target_index=item.target_index,
                    direction="low",
                    statistic=negative,
                    pit=pit,
                )
            )
            negative = 0.0
    return tuple(events)


def _report_fingerprint(
    *,
    config: CalibrationConfig,
    ordered: Sequence[DistributionObservation],
    pits: Sequence[float],
    coverage: Sequence[CoverageDiagnostic],
    mean_log_score: float,
    mean_crps: float,
    drift_events: Sequence[DriftEvent],
    calibration_score: float,
) -> str:
    parts = [
        "jeeves-probabilistic-calibration-v1",
        repr(config),
        format(mean_log_score, ".17g"),
        format(mean_crps, ".17g"),
        format(calibration_score, ".17g"),
        ",".join(format(value, ".17g") for value in pits),
    ]
    for item in ordered:
        parts.extend(
            (
                str(item.target_index),
                format(item.actual, ".17g"),
                format(item.forecast.mean, ".17g"),
                format(item.forecast.variance, ".17g"),
            )
        )
    for item in coverage:
        parts.extend(
            (
                format(item.level, ".17g"),
                format(item.empirical, ".17g"),
                format(item.absolute_gap, ".17g"),
                format(item.average_width, ".17g"),
                format(item.average_pinball_loss, ".17g"),
            )
        )
    for event in drift_events:
        parts.extend(
            (
                str(event.target_index),
                event.direction,
                format(event.statistic, ".17g"),
                format(event.pit, ".17g"),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _non_negative(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _open_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum < number < maximum:
        raise StateSpaceError(
            f"{name} must be strictly between {minimum} and {maximum}",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum <= number <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "out_of_range", "field": name},
        )
    return number


__all__ = [
    "CalibrationConfig",
    "CalibrationReport",
    "CoverageDiagnostic",
    "DistributionObservation",
    "DriftEvent",
    "PitDiagnostic",
    "calibrate_distributions",
    "central_interval",
    "gaussian_as_mixture",
    "mixture_cdf",
    "mixture_quantile",
    "pinball_loss",
]
