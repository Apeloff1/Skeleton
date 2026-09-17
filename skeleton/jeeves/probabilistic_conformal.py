"""Prequential conformal interval calibration for Jeeves.

This module calibrates predictive intervals from already-issued forecasts.  It is
model-agnostic: Gaussian, Student-t, regime-mixture, spectral, and arbitrated
forecasts can all contribute as long as they expose ``horizon``, ``mean``, and
``variance``.

Temporal custody is explicit.  For target ``t`` the interval is built only from
nonconformity scores produced by targets strictly before ``t``.  The realized
value at ``t`` may update calibration state only after the interval has been
recorded and scored.

With fixed miscoverage and exchangeable scores, the finite-sample order statistic
is the standard split-conformal correction.  Adaptive miscoverage is an online
coverage-control heuristic for non-stationarity; it should not be described as a
finite-sample coverage guarantee under arbitrary drift.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Protocol, Sequence

from .probabilistic_state_space import StateSpaceError

_EPSILON = 1e-15


class LocationScaleForecast(Protocol):
    """Minimal forecast contract needed by conformal calibration."""

    horizon: int
    mean: float
    variance: float


@dataclass(frozen=True, slots=True)
class ConformalConfig:
    """Configuration for prequential conformal calibration."""

    miscoverage: float = 0.10
    min_calibration_size: int = 16
    calibration_window: int | None = 128
    normalized_scores: bool = True
    adaptive: bool = True
    adaptation_rate: float = 0.02
    min_miscoverage: float = 0.005
    max_miscoverage: float = 0.50
    min_scale: float = 1e-6

    def __post_init__(self) -> None:
        _open_unit_interval("miscoverage", self.miscoverage)
        if (
            isinstance(self.min_calibration_size, bool)
            or not isinstance(self.min_calibration_size, int)
            or self.min_calibration_size < 1
        ):
            raise StateSpaceError(
                "min_calibration_size must be a positive integer",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "min_calibration_size",
                },
            )
        if self.calibration_window is not None:
            if (
                isinstance(self.calibration_window, bool)
                or not isinstance(self.calibration_window, int)
                or self.calibration_window < self.min_calibration_size
            ):
                raise StateSpaceError(
                    "calibration_window must be >= min_calibration_size or None",
                    context={
                        "reason": "invalid_conformal_config",
                        "field": "calibration_window",
                    },
                )
        if not isinstance(self.normalized_scores, bool):
            raise StateSpaceError(
                "normalized_scores must be boolean",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "normalized_scores",
                },
            )
        if not isinstance(self.adaptive, bool):
            raise StateSpaceError(
                "adaptive must be boolean",
                context={"reason": "invalid_conformal_config", "field": "adaptive"},
            )
        _closed_unit_interval("adaptation_rate", self.adaptation_rate)
        minimum = _open_unit_interval("min_miscoverage", self.min_miscoverage)
        maximum = _open_unit_interval("max_miscoverage", self.max_miscoverage)
        if minimum >= maximum:
            raise StateSpaceError(
                "min_miscoverage must be smaller than max_miscoverage",
                context={"reason": "invalid_conformal_config"},
            )
        if not minimum <= self.miscoverage <= maximum:
            raise StateSpaceError(
                "miscoverage must lie inside adaptive bounds",
                context={
                    "reason": "invalid_conformal_config",
                    "field": "miscoverage",
                },
            )
        _positive("min_scale", self.min_scale)


@dataclass(frozen=True, slots=True)
class ConformalObservation:
    """One realized target paired with the forecast issued before realization."""

    target_index: int
    actual: float
    forecast: LocationScaleForecast

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < 0
        ):
            raise StateSpaceError(
                "target_index must be a non-negative integer",
                context={"reason": "invalid_conformal_observation"},
            )
        _finite("actual", self.actual)
        _validate_forecast(self.forecast)


@dataclass(frozen=True, slots=True)
class ConformalInterval:
    """Interval produced before the associated target is observed."""

    target_index: int
    horizon: int
    center: float
    lower: float
    upper: float
    radius: float
    score_quantile: float
    forecast_scale: float
    miscoverage: float
    calibration_size: int
    normalized_scores: bool

    def __post_init__(self) -> None:
        if self.lower > self.center or self.center > self.upper:
            raise StateSpaceError(
                "conformal interval must contain its center",
                context={"reason": "invalid_conformal_interval"},
            )
        if self.radius < 0.0 or self.calibration_size < 1:
            raise StateSpaceError(
                "conformal interval geometry is invalid",
                context={"reason": "invalid_conformal_interval"},
            )
        for name in (
            "center",
            "lower",
            "upper",
            "radius",
            "score_quantile",
            "forecast_scale",
            "miscoverage",
        ):
            _finite(name, getattr(self, name))

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, actual: float) -> bool:
        actual = _finite("actual", actual)
        return self.lower <= actual <= self.upper

    def interval_score(self, actual: float) -> float:
        """Winkler interval score at this interval's nominal miscoverage."""

        actual = _finite("actual", actual)
        score = self.width
        if actual < self.lower:
            score += (2.0 / self.miscoverage) * (self.lower - actual)
        elif actual > self.upper:
            score += (2.0 / self.miscoverage) * (actual - self.upper)
        return score


@dataclass(frozen=True, slots=True)
class ConformalStep:
    """One prequential calibration transition."""

    target_index: int
    actual: float
    forecast_mean: float
    forecast_variance: float
    prior_miscoverage: float
    posterior_miscoverage: float
    nonconformity_score: float
    interval: ConformalInterval | None
    covered: bool | None
    calibration_size_before: int
    calibration_size_after: int

    @property
    def eligible(self) -> bool:
        return self.interval is not None


@dataclass(frozen=True, slots=True)
class ConformalReport:
    """Immutable evidence from a complete prequential calibration pass."""

    config: ConformalConfig
    horizon: int
    steps: tuple[ConformalStep, ...]
    evaluated_intervals: int
    warmup_observations: int
    empirical_coverage: float | None
    coverage_gap: float | None
    average_width: float | None
    average_interval_score: float | None
    average_score_quantile: float | None
    final_miscoverage: float
    fingerprint: str

    @property
    def target_coverage(self) -> float:
        return 1.0 - self.config.miscoverage

    @property
    def miss_rate(self) -> float | None:
        if self.empirical_coverage is None:
            return None
        return 1.0 - self.empirical_coverage

    @property
    def last_interval(self) -> ConformalInterval | None:
        for step in reversed(self.steps):
            if step.interval is not None:
                return step.interval
        return None


@dataclass(frozen=True, slots=True)
class ConformalCalibrationState:
    """Serializable state for producing the next interval without target leakage."""

    horizon: int
    scores: tuple[float, ...]
    current_miscoverage: float
    config: ConformalConfig
    fingerprint: str

    @property
    def ready(self) -> bool:
        return len(self.scores) >= self.config.min_calibration_size

    def interval_for(
        self,
        forecast: LocationScaleForecast,
        *,
        target_index: int,
    ) -> ConformalInterval | None:
        _validate_forecast(forecast)
        if forecast.horizon != self.horizon:
            raise StateSpaceError(
                "conformal state cannot mix forecast horizons",
                context={"reason": "conformal_horizon_mismatch"},
            )
        if not self.ready:
            return None
        return conformal_interval_from_scores(
            forecast,
            self.scores,
            target_index=target_index,
            miscoverage=self.current_miscoverage,
            config=self.config,
        )


def evaluate_conformal_observations(
    observations: Sequence[ConformalObservation],
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Run leakage-safe prequential conformal calibration.

    Every interval is constructed from scores whose target index is strictly
    smaller than the current target index.  The current target score is appended
    only after interval scoring and adaptive-miscoverage updating.
    """

    actual_config = config or ConformalConfig()
    values = tuple(observations)
    if not values:
        raise StateSpaceError(
            "conformal evaluation requires observations",
            context={"reason": "empty_conformal_observations"},
        )
    _validate_observation_sequence(values)
    horizon = values[0].forecast.horizon

    scores: list[float] = []
    alpha = actual_config.miscoverage
    steps: list[ConformalStep] = []
    widths: list[float] = []
    interval_scores: list[float] = []
    quantiles: list[float] = []
    coverages: list[float] = []

    for observation in values:
        prior_alpha = alpha
        interval: ConformalInterval | None = None
        covered: bool | None = None
        before = len(scores)
        if before >= actual_config.min_calibration_size:
            interval = conformal_interval_from_scores(
                observation.forecast,
                scores,
                target_index=observation.target_index,
                miscoverage=prior_alpha,
                config=actual_config,
            )
            covered = interval.contains(observation.actual)
            coverages.append(1.0 if covered else 0.0)
            widths.append(interval.width)
            interval_scores.append(interval.interval_score(observation.actual))
            quantiles.append(interval.score_quantile)

            if actual_config.adaptive:
                miss = 0.0 if covered else 1.0
                alpha = _clip(
                    prior_alpha
                    + actual_config.adaptation_rate
                    * (actual_config.miscoverage - miss),
                    actual_config.min_miscoverage,
                    actual_config.max_miscoverage,
                )

        score = nonconformity_score(
            observation.forecast,
            observation.actual,
            config=actual_config,
        )
        scores.append(score)
        if (
            actual_config.calibration_window is not None
            and len(scores) > actual_config.calibration_window
        ):
            del scores[: len(scores) - actual_config.calibration_window]

        steps.append(
            ConformalStep(
                target_index=observation.target_index,
                actual=observation.actual,
                forecast_mean=float(observation.forecast.mean),
                forecast_variance=float(observation.forecast.variance),
                prior_miscoverage=prior_alpha,
                posterior_miscoverage=alpha,
                nonconformity_score=score,
                interval=interval,
                covered=covered,
                calibration_size_before=before,
                calibration_size_after=len(scores),
            )
        )

    evaluated = len(coverages)
    empirical_coverage = statistics.fmean(coverages) if coverages else None
    coverage_gap = (
        empirical_coverage - (1.0 - actual_config.miscoverage)
        if empirical_coverage is not None
        else None
    )
    fingerprint = _report_fingerprint(
        config=actual_config,
        horizon=horizon,
        steps=steps,
        final_miscoverage=alpha,
    )
    return ConformalReport(
        config=actual_config,
        horizon=horizon,
        steps=tuple(steps),
        evaluated_intervals=evaluated,
        warmup_observations=len(steps) - evaluated,
        empirical_coverage=empirical_coverage,
        coverage_gap=coverage_gap,
        average_width=statistics.fmean(widths) if widths else None,
        average_interval_score=(
            statistics.fmean(interval_scores) if interval_scores else None
        ),
        average_score_quantile=statistics.fmean(quantiles) if quantiles else None,
        final_miscoverage=alpha,
        fingerprint=fingerprint,
    )


def state_from_report(report: ConformalReport) -> ConformalCalibrationState:
    """Extract the exact score window and adaptive alpha for the next target."""

    if not report.steps:
        raise StateSpaceError(
            "cannot build conformal state from an empty report",
            context={"reason": "empty_conformal_report"},
        )
    scores = [step.nonconformity_score for step in report.steps]
    window = report.config.calibration_window
    if window is not None and len(scores) > window:
        scores = scores[-window:]
    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-conformal-state-v1",
                report.fingerprint,
                ",".join(format(value, ".17g") for value in scores),
                format(report.final_miscoverage, ".17g"),
            )
        ).encode("utf-8")
    ).hexdigest()
    return ConformalCalibrationState(
        horizon=report.horizon,
        scores=tuple(scores),
        current_miscoverage=report.final_miscoverage,
        config=report.config,
        fingerprint=fingerprint,
    )


def conformal_interval_from_scores(
    forecast: LocationScaleForecast,
    scores: Sequence[float],
    *,
    target_index: int,
    miscoverage: float,
    config: ConformalConfig | None = None,
) -> ConformalInterval:
    """Build one interval from already-realized calibration scores."""

    actual_config = config or ConformalConfig(miscoverage=miscoverage)
    _validate_forecast(forecast)
    alpha = _open_unit_interval("miscoverage", miscoverage)
    clean_scores = tuple(_non_negative("score", score) for score in scores)
    if len(clean_scores) < actual_config.min_calibration_size:
        raise StateSpaceError(
            "insufficient prior scores for a conformal interval",
            context={
                "reason": "insufficient_conformal_calibration",
                "available": len(clean_scores),
                "required": actual_config.min_calibration_size,
            },
        )
    quantile = finite_sample_conformal_quantile(clean_scores, miscoverage=alpha)
    scale = forecast_scale(forecast, config=actual_config)
    radius = quantile * scale if actual_config.normalized_scores else quantile
    center = float(forecast.mean)
    return ConformalInterval(
        target_index=target_index,
        horizon=forecast.horizon,
        center=center,
        lower=center - radius,
        upper=center + radius,
        radius=radius,
        score_quantile=quantile,
        forecast_scale=scale,
        miscoverage=alpha,
        calibration_size=len(clean_scores),
        normalized_scores=actual_config.normalized_scores,
    )


def finite_sample_conformal_quantile(
    scores: Sequence[float],
    *,
    miscoverage: float,
) -> float:
    """Return the standard finite-sample split-conformal order statistic."""

    alpha = _open_unit_interval("miscoverage", miscoverage)
    clean = sorted(_non_negative("score", score) for score in scores)
    if not clean:
        raise StateSpaceError(
            "conformal quantile requires at least one score",
            context={"reason": "empty_conformal_scores"},
        )
    rank = math.ceil((len(clean) + 1) * (1.0 - alpha))
    index = min(len(clean), max(1, rank)) - 1
    return clean[index]


def nonconformity_score(
    forecast: LocationScaleForecast,
    actual: float,
    *,
    config: ConformalConfig | None = None,
) -> float:
    """Absolute residual, optionally normalized by predictive scale."""

    actual_config = config or ConformalConfig()
    _validate_forecast(forecast)
    actual = _finite("actual", actual)
    residual = abs(actual - float(forecast.mean))
    if not actual_config.normalized_scores:
        return residual
    return residual / forecast_scale(forecast, config=actual_config)


def forecast_scale(
    forecast: LocationScaleForecast,
    *,
    config: ConformalConfig | None = None,
) -> float:
    """Positive predictive scale used by normalized nonconformity scores."""

    actual_config = config or ConformalConfig()
    _validate_forecast(forecast)
    return max(actual_config.min_scale, math.sqrt(float(forecast.variance)))


def observations_from_cross_family_report(report: object) -> tuple[ConformalObservation, ...]:
    """Adapt a cross-family arbitration report without creating a hard import cycle."""

    raw_steps = getattr(report, "steps", None)
    if raw_steps is None:
        raise StateSpaceError(
            "report does not expose prequential steps",
            context={"reason": "invalid_conformal_source_report"},
        )
    observations: list[ConformalObservation] = []
    for step in raw_steps:
        try:
            observations.append(
                ConformalObservation(
                    target_index=int(step.target_index),
                    actual=float(step.actual),
                    forecast=step.predictive,
                )
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise StateSpaceError(
                "report step does not satisfy conformal source contract",
                context={"reason": "invalid_conformal_source_report"},
            ) from exc
    return tuple(observations)


def _validate_observation_sequence(
    observations: Sequence[ConformalObservation],
) -> None:
    previous_index: int | None = None
    horizon: int | None = None
    for observation in observations:
        if previous_index is not None and observation.target_index <= previous_index:
            raise StateSpaceError(
                "conformal observations must have strictly increasing target indices",
                context={"reason": "non_monotonic_conformal_targets"},
            )
        if horizon is None:
            horizon = observation.forecast.horizon
        elif observation.forecast.horizon != horizon:
            raise StateSpaceError(
                "conformal calibration cannot pool forecast horizons",
                context={"reason": "conformal_horizon_mismatch"},
            )
        previous_index = observation.target_index


def _validate_forecast(forecast: LocationScaleForecast) -> None:
    horizon = getattr(forecast, "horizon", None)
    mean = getattr(forecast, "mean", None)
    variance = getattr(forecast, "variance", None)
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "conformal forecast horizon must be a positive integer",
            context={"reason": "invalid_conformal_forecast"},
        )
    _finite("forecast_mean", mean)
    if _positive("forecast_variance", variance) <= 0.0:
        raise StateSpaceError(
            "conformal forecast variance must be positive",
            context={"reason": "invalid_conformal_forecast"},
        )


def _report_fingerprint(
    *,
    config: ConformalConfig,
    horizon: int,
    steps: Sequence[ConformalStep],
    final_miscoverage: float,
) -> str:
    parts = [
        "jeeves-prequential-conformal-v1",
        repr(config),
        str(horizon),
    ]
    for step in steps:
        parts.extend(
            (
                str(step.target_index),
                format(step.actual, ".17g"),
                format(step.forecast_mean, ".17g"),
                format(step.forecast_variance, ".17g"),
                format(step.prior_miscoverage, ".17g"),
                format(step.posterior_miscoverage, ".17g"),
                format(step.nonconformity_score, ".17g"),
                "none" if step.covered is None else str(int(step.covered)),
            )
        )
        if step.interval is not None:
            parts.extend(
                (
                    format(step.interval.lower, ".17g"),
                    format(step.interval.upper, ".17g"),
                    format(step.interval.score_quantile, ".17g"),
                    str(step.interval.calibration_size),
                )
            )
    parts.append(format(final_miscoverage, ".17g"))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


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


def _open_unit_interval(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 < number < 1.0:
        raise StateSpaceError(
            f"{name} must lie strictly between zero and one",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return number


def _closed_unit_interval(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise StateSpaceError(
            f"{name} must lie between zero and one",
            context={"reason": "invalid_conformal_config", "field": name},
        )
    return number


def _clip(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


__all__ = [
    "ConformalCalibrationState",
    "ConformalConfig",
    "ConformalInterval",
    "ConformalObservation",
    "ConformalReport",
    "ConformalStep",
    "LocationScaleForecast",
    "conformal_interval_from_scores",
    "evaluate_conformal_observations",
    "finite_sample_conformal_quantile",
    "forecast_scale",
    "nonconformity_score",
    "observations_from_cross_family_report",
    "state_from_report",
]
