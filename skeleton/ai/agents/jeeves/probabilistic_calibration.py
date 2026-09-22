"""Distributional calibration diagnostics for Jeeves probabilistic forecasts.

A predictive system should be judged on more than point error. This module measures
whether realized outcomes behave like draws from the forecast distributions:
probability integral transform (PIT), empirical interval coverage, quantile loss,
sharpness, and sequential calibration drift.

All diagnostics operate on already-produced forecasts and realized targets. They
never mutate model state or feed a target back into the forecast that produced it.
Calibration reports retain exact target identity, the full PIT sequence, and a
deterministic fingerprint of the predictive mixtures used for every target. This
allows downstream governance to verify evidence custody instead of relying on
equal sample counts or detached aggregate metrics.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

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
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 0
        ):
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
        if (
            isinstance(self.pit_bins, bool)
            or not isinstance(self.pit_bins, int)
            or self.pit_bins < 2
        ):
            raise StateSpaceError(
                "pit_bins must be an integer >= 2",
                context={"reason": "invalid_calibration_config", "field": "pit_bins"},
            )
        _open_interval("tail_probability", self.tail_probability, 0.0, 0.5)
        _non_negative("drift_reference", self.drift_reference)
        _positive("drift_threshold", self.drift_threshold)
        _positive("quantile_tolerance", self.quantile_tolerance)
        if (
            isinstance(self.quantile_iterations, bool)
            or not isinstance(self.quantile_iterations, int)
            or self.quantile_iterations < 10
        ):
            raise StateSpaceError(
                "quantile_iterations must be an integer >= 10",
                context={
                    "reason": "invalid_calibration_config",
                    "field": "quantile_iterations",
                },
            )


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    config: CalibrationConfig
    observations: int
    target_pairs: tuple[tuple[int, float], ...]
    target_fingerprint: str
    observation_fingerprint: str
    pits: tuple[float, ...]
    pit: PitDiagnostic
    coverage: tuple[CoverageDiagnostic, ...]
    mean_log_score: float
    mean_crps: float
    drift_events: tuple[DriftEvent, ...]
    calibration_score: float
    fingerprint: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.observations, bool)
            or not isinstance(self.observations, int)
            or self.observations < 1
        ):
            raise StateSpaceError(
                "calibration observations must be a positive integer",
                context={"reason": "invalid_calibration_report"},
            )
        _validate_target_pairs(self.target_pairs, expected_count=self.observations)
        if not isinstance(self.pits, tuple) or len(self.pits) != self.observations:
            raise StateSpaceError(
                "PIT sequence count must equal calibration observations",
                context={"reason": "invalid_calibration_report"},
            )
        for value in self.pits:
            _unit("pit", value)
        for name, value in (
            ("target_fingerprint", self.target_fingerprint),
            ("observation_fingerprint", self.observation_fingerprint),
            ("fingerprint", self.fingerprint),
        ):
            _validate_digest(name, value)
        if self.pit.count != self.observations:
            raise StateSpaceError(
                "PIT count must equal calibration observations",
                context={"reason": "invalid_calibration_report"},
            )
        _unit("calibration_score", self.calibration_score)
        _finite("mean_log_score", self.mean_log_score)
        _non_negative("mean_crps", self.mean_crps)

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

    target_pairs = tuple((item.target_index, float(item.actual)) for item in ordered)
    _validate_target_pairs(target_pairs, expected_count=len(ordered))
    target_fingerprint = _target_fingerprint(target_pairs)
    observation_fingerprint = calibration_observation_fingerprint(ordered)

    pits = tuple(
        probability_integral_transform(item.forecast, item.actual)
        for item in ordered
    )
    pit = _pit_diagnostic(pits, actual_config)
    coverage = tuple(
        _coverage_diagnostic(ordered, level, actual_config)
        for level in actual_config.levels
    )
    mean_log_score = statistics.fmean(
        item.forecast.log_density(item.actual) for item in ordered
    )
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
        target_fingerprint=target_fingerprint,
        observation_fingerprint=observation_fingerprint,
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
        target_pairs=target_pairs,
        target_fingerprint=target_fingerprint,
        observation_fingerprint=observation_fingerprint,
        pits=pits,
        pit=pit,
        coverage=coverage,
        mean_log_score=mean_log_score,
        mean_crps=mean_crps,
        drift_events=drift_events,
        calibration_score=calibration_score,
        fingerprint=fingerprint,
    )


def validate_calibration_report(report: CalibrationReport) -> None:
    """Reject malformed or tampered distributional-calibration evidence."""

    if not isinstance(report, CalibrationReport):
        raise StateSpaceError(
            "report must be a CalibrationReport",
            context={"reason": "invalid_calibration_report"},
        )
    _validate_target_pairs(report.target_pairs, expected_count=report.observations)
    expected_target_fingerprint = _target_fingerprint(report.target_pairs)
    if report.target_fingerprint != expected_target_fingerprint:
        raise StateSpaceError(
            "calibration target fingerprint mismatch",
            context={"reason": "calibration_report_identity_mismatch"},
        )
    if len(report.pits) != report.observations:
        raise StateSpaceError(
            "calibration PIT sequence count mismatch",
            context={"reason": "calibration_report_identity_mismatch"},
        )
    expected_pit = _pit_diagnostic(report.pits, report.config)
    if report.pit != expected_pit:
        raise StateSpaceError(
            "calibration PIT diagnostic mismatch",
            context={"reason": "calibration_report_identity_mismatch"},
        )
    expected_fingerprint = _report_fingerprint(
        config=report.config,
        target_fingerprint=report.target_fingerprint,
        observation_fingerprint=report.observation_fingerprint,
        pits=report.pits,
        coverage=report.coverage,
        mean_log_score=report.mean_log_score,
        mean_crps=report.mean_crps,
        drift_events=report.drift_events,
        calibration_score=report.calibration_score,
    )
    if report.fingerprint != expected_fingerprint:
        raise StateSpaceError(
            "calibration report fingerprint mismatch",
            context={"reason": "calibration_report_identity_mismatch"},
        )


def calibration_observation_fingerprint(
    observations: Sequence[DistributionObservation],
) -> str:
    """Fingerprint exact target identities and predictive-mixture geometry."""

    if not observations:
        raise StateSpaceError(
            "calibration observation fingerprint requires observations",
            context={"reason": "empty_calibration_set"},
        )
    ordered = tuple(sorted(observations, key=lambda item: item.target_index))
    if len({item.target_index for item in ordered}) != len(ordered):
        raise StateSpaceError(
            "calibration target indices must be unique",
            context={"reason": "duplicate_target_index"},
        )
    payload = {
        "schema": "jeeves.calibration-observations.v1",
        "observations": [
            {
                "target_index": item.target_index,
                "actual": float(item.actual),
                "forecast": _mixture_payload(item.forecast),
            }
            for item in ordered
        ],
    }
    return _digest(payload)


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
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations < 10
    ):
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
    upper_tail_rate = sum(
        value >= 1.0 - config.tail_probability for value in pits
    ) / count
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
    target_fingerprint: str,
    observation_fingerprint: str,
    pits: Sequence[float],
    coverage: Sequence[CoverageDiagnostic],
    mean_log_score: float,
    mean_crps: float,
    drift_events: Sequence[DriftEvent],
    calibration_score: float,
) -> str:
    payload = {
        "schema": "jeeves.probabilistic-calibration.v2",
        "config": {
            "levels": list(config.levels),
            "pit_bins": config.pit_bins,
            "tail_probability": config.tail_probability,
            "drift_reference": config.drift_reference,
            "drift_threshold": config.drift_threshold,
            "quantile_tolerance": config.quantile_tolerance,
            "quantile_iterations": config.quantile_iterations,
        },
        "target_fingerprint": target_fingerprint,
        "observation_fingerprint": observation_fingerprint,
        "pits": list(pits),
        "coverage": [
            {
                "level": item.level,
                "expected": item.expected,
                "empirical": item.empirical,
                "absolute_gap": item.absolute_gap,
                "average_width": item.average_width,
                "median_width": item.median_width,
                "average_pinball_loss": item.average_pinball_loss,
            }
            for item in coverage
        ],
        "mean_log_score": mean_log_score,
        "mean_crps": mean_crps,
        "drift_events": [
            {
                "target_index": event.target_index,
                "direction": event.direction,
                "statistic": event.statistic,
                "pit": event.pit,
            }
            for event in drift_events
        ],
        "calibration_score": calibration_score,
    }
    return _digest(payload)


def _mixture_payload(forecast: MixtureForecast) -> dict[str, object]:
    return {
        "horizon": forecast.horizon,
        "components": [
            {
                "family": component.family.value,
                "weight": component.weight,
                "horizon": component.forecast.horizon,
                "mean": component.forecast.mean,
                "variance": component.forecast.variance,
            }
            for component in forecast.components
        ],
    }


def _target_fingerprint(target_pairs: tuple[tuple[int, float], ...]) -> str:
    return _digest(
        {
            "schema": "jeeves.calibration-targets.v1",
            "targets": [
                {"target_index": index, "actual": actual}
                for index, actual in target_pairs
            ],
        }
    )


def _validate_target_pairs(
    pairs: tuple[tuple[int, float], ...],
    *,
    expected_count: int,
) -> None:
    if not isinstance(pairs, tuple) or len(pairs) != expected_count:
        raise StateSpaceError(
            "target_pairs count must equal observations",
            context={"reason": "invalid_calibration_report"},
        )
    indices: list[int] = []
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise StateSpaceError(
                "target_pairs entries must be (target_index, actual)",
                context={"reason": "invalid_calibration_report"},
            )
        index, actual = pair
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise StateSpaceError(
                "calibration target index is invalid",
                context={"reason": "invalid_calibration_report"},
            )
        _finite("target_actual", actual)
        indices.append(index)
    if tuple(indices) != tuple(sorted(indices)) or len(set(indices)) != len(indices):
        raise StateSpaceError(
            "calibration target pairs must have unique increasing indices",
            context={"reason": "invalid_calibration_report"},
        )


def _validate_digest(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_calibration_report"},
        )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise StateSpaceError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
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
    "calibration_observation_fingerprint",
    "central_interval",
    "gaussian_as_mixture",
    "mixture_cdf",
    "mixture_quantile",
    "pinball_loss",
    "validate_calibration_report",
]
