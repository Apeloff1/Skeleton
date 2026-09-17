"""Prequential conformal interval calibration for Jeeves.

The calibration layer is model-agnostic. Any already-issued forecast exposing a
positive horizon, finite mean, and positive finite variance can contribute.

Temporal custody is explicit: an interval for target ``t`` is constructed only
from nonconformity scores produced by targets strictly before ``t``. The
realized value at ``t`` may update calibration state only after its interval has
been recorded and scored.

Finite-sample coverage has a hard resolution limit. With ``n`` calibration
scores, split conformal cannot request miscoverage smaller than ``1/(n+1)``
without using an infinite sentinel. Direct quantile calls therefore fail closed
when the requested alpha is unattainable. The streaming evaluator instead
records and uses the smallest attainable alpha for that target, making the
coverage limitation explicit rather than silently pretending the requested
coverage was achieved.

Adaptive miscoverage is an online coverage-control heuristic for
non-stationarity. It is not a finite-sample coverage guarantee under arbitrary
drift.
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
        _target_index(self.target_index)
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
    requested_miscoverage: float
    attainable_miscoverage_floor: float
    calibration_size: int
    normalized_scores: bool

    def __post_init__(self) -> None:
        _target_index(self.target_index)
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "conformal interval horizon must be a positive integer",
                context={"reason": "invalid_conformal_interval"},
            )
        if isinstance(self.calibration_size, bool) or not isinstance(self.calibration_size, int):
            raise StateSpaceError(
                "calibration_size must be an integer",
                context={"reason": "invalid_conformal_interval"},
            )
        if self.calibration_size < 1:
            raise StateSpaceError(
                "calibration_size must be positive",
                context={"reason": "invalid_conformal_interval"},
            )
        if not isinstance(self.normalized_scores, bool):
            raise StateSpaceError(
                "normalized_scores must be boolean",
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
            "requested_miscoverage",
            "attainable_miscoverage_floor",
        ):
            _finite(name, getattr(self, name))
        _open_unit_interval("miscoverage", self.miscoverage)
        _open_unit_interval("requested_miscoverage", self.requested_miscoverage)
        _open_unit_interval(
            "attainable_miscoverage_floor",
            self.attainable_miscoverage_floor,
        )
        if self.radius < 0.0 or self.score_quantile < 0.0 or self.forecast_scale <= 0.0:
            raise StateSpaceError(
                "conformal interval geometry is invalid",
                context={"reason": "invalid_conformal_interval"},
            )
        if self.lower > self.center or self.center > self.upper:
            raise StateSpaceError(
                "conformal interval must contain its center",
                context={"reason": "invalid_conformal_interval"},
            )
        if abs((self.upper - self.center) - self.radius) > max(1e-9, 1e-12 * abs(self.radius)):
            raise StateSpaceError(
                "upper interval radius is inconsistent",
                context={"reason": "invalid_conformal_interval"},
            )
        if abs((self.center - self.lower) - self.radius) > max(1e-9, 1e-12 * abs(self.radius)):
            raise StateSpaceError(
                "lower interval radius is inconsistent",
                context={"reason": "invalid_conformal_interval"},
            )
        expected_floor = attainable_miscoverage_floor(self.calibration_size)
        if abs(self.attainable_miscoverage_floor - expected_floor) > 1e-15:
            raise StateSpaceError(
                "attainable miscoverage floor does not match calibration size",
                context={"reason": "invalid_conformal_interval"},
            )
        expected_effective = max(self.requested_miscoverage, expected_floor)
        if abs(self.miscoverage - expected_effective) > 1e-15:
            raise StateSpaceError(
                "effective miscoverage does not match finite-sample limit",
                context={"reason": "invalid_conformal_interval"},
            )

    @property
    def width(self) -> float:
        width = self.upper - self.lower
        return _finite_result("interval_width", width)

    @property
    def coverage_limited(self) -> bool:
        return self.miscoverage > self.requested_miscoverage + 1e-15

    @property
    def effective_coverage(self) -> float:
        return 1.0 - self.miscoverage

    @property
    def requested_coverage(self) -> float:
        return 1.0 - self.requested_miscoverage

    def contains(self, actual: float) -> bool:
        actual = _finite("actual", actual)
        return self.lower <= actual <= self.upper

    def interval_score(self, actual: float) -> float:
        """Winkler interval score at the interval's effective alpha."""

        actual = _finite("actual", actual)
        score = self.width
        if actual < self.lower:
            score += (2.0 / self.miscoverage) * (self.lower - actual)
        elif actual > self.upper:
            score += (2.0 / self.miscoverage) * (actual - self.upper)
        return _finite_result("interval_score", score)


@dataclass(frozen=True, slots=True)
class ConformalStep:
    """One prequential calibration transition."""

    target_index: int
    actual: float
    forecast_mean: float
    forecast_variance: float
    prior_miscoverage: float
    effective_miscoverage: float | None
    posterior_miscoverage: float
    nonconformity_score: float
    interval: ConformalInterval | None
    covered: bool | None
    calibration_size_before: int
    calibration_size_after: int

    def __post_init__(self) -> None:
        _target_index(self.target_index)
        _finite("actual", self.actual)
        _finite("forecast_mean", self.forecast_mean)
        _positive("forecast_variance", self.forecast_variance)
        _open_unit_interval("prior_miscoverage", self.prior_miscoverage)
        _open_unit_interval("posterior_miscoverage", self.posterior_miscoverage)
        _non_negative("nonconformity_score", self.nonconformity_score)
        if self.effective_miscoverage is not None:
            _open_unit_interval("effective_miscoverage", self.effective_miscoverage)
        if isinstance(self.calibration_size_before, bool) or not isinstance(
            self.calibration_size_before,
            int,
        ):
            raise StateSpaceError(
                "calibration_size_before must be an integer",
                context={"reason": "invalid_conformal_step"},
            )
        if isinstance(self.calibration_size_after, bool) or not isinstance(
            self.calibration_size_after,
            int,
        ):
            raise StateSpaceError(
                "calibration_size_after must be an integer",
                context={"reason": "invalid_conformal_step"},
            )
        if self.calibration_size_before < 0 or self.calibration_size_after < 1:
            raise StateSpaceError(
                "calibration sizes are invalid",
                context={"reason": "invalid_conformal_step"},
            )
        if self.interval is None:
            if self.covered is not None or self.effective_miscoverage is not None:
                raise StateSpaceError(
                    "warmup steps cannot carry interval outcomes",
                    context={"reason": "invalid_conformal_step"},
                )
        else:
            if not isinstance(self.covered, bool):
                raise StateSpaceError(
                    "evaluated conformal step requires boolean coverage",
                    context={"reason": "invalid_conformal_step"},
                )
            if self.effective_miscoverage is None:
                raise StateSpaceError(
                    "evaluated conformal step requires effective miscoverage",
                    context={"reason": "invalid_conformal_step"},
                )
            if self.interval.target_index != self.target_index:
                raise StateSpaceError(
                    "interval target does not match step target",
                    context={"reason": "invalid_conformal_step"},
                )

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
    finite_sample_limited_intervals: int
    empirical_coverage: float | None
    coverage_gap: float | None
    average_width: float | None
    average_interval_score: float | None
    average_score_quantile: float | None
    final_miscoverage: float
    fingerprint: str

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "report horizon must be a positive integer",
                context={"reason": "invalid_conformal_report"},
            )
        if not self.steps:
            raise StateSpaceError(
                "conformal report requires at least one step",
                context={"reason": "invalid_conformal_report"},
            )
        for name in (
            "evaluated_intervals",
            "warmup_observations",
            "finite_sample_limited_intervals",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StateSpaceError(
                    f"{name} must be a non-negative integer",
                    context={"reason": "invalid_conformal_report", "field": name},
                )
        if self.evaluated_intervals + self.warmup_observations != len(self.steps):
            raise StateSpaceError(
                "report interval counts do not match steps",
                context={"reason": "invalid_conformal_report"},
            )
        if self.finite_sample_limited_intervals > self.evaluated_intervals:
            raise StateSpaceError(
                "finite-sample limited interval count exceeds evaluated intervals",
                context={"reason": "invalid_conformal_report"},
            )
        _open_unit_interval("final_miscoverage", self.final_miscoverage)
        if not isinstance(self.fingerprint, str) or len(self.fingerprint) != 64:
            raise StateSpaceError(
                "report fingerprint must be a SHA-256 hex digest",
                context={"reason": "invalid_conformal_report"},
            )
        if self.empirical_coverage is None:
            if self.evaluated_intervals != 0:
                raise StateSpaceError(
                    "missing coverage with evaluated intervals",
                    context={"reason": "invalid_conformal_report"},
                )
            if any(
                value is not None
                for value in (
                    self.coverage_gap,
                    self.average_width,
                    self.average_interval_score,
                    self.average_score_quantile,
                )
            ):
                raise StateSpaceError(
                    "unevaluated report cannot expose aggregate interval metrics",
                    context={"reason": "invalid_conformal_report"},
                )
        else:
            coverage = _closed_unit_interval("empirical_coverage", self.empirical_coverage)
            _finite("coverage_gap", self.coverage_gap)
            _non_negative("average_width", self.average_width)
            _non_negative("average_interval_score", self.average_interval_score)
            _non_negative("average_score_quantile", self.average_score_quantile)
            if coverage != self.empirical_coverage:
                raise StateSpaceError(
                    "empirical coverage normalization changed unexpectedly",
                    context={"reason": "invalid_conformal_report"},
                )

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

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "conformal state horizon must be a positive integer",
                context={"reason": "invalid_conformal_state"},
            )
        clean_scores = tuple(_non_negative("score", score) for score in self.scores)
        if clean_scores != self.scores:
            raise StateSpaceError(
                "conformal state scores changed under validation",
                context={"reason": "invalid_conformal_state"},
            )
        if (
            self.config.calibration_window is not None
            and len(self.scores) > self.config.calibration_window
        ):
            raise StateSpaceError(
                "conformal state exceeds configured calibration window",
                context={"reason": "invalid_conformal_state"},
            )
        alpha = _open_unit_interval("current_miscoverage", self.current_miscoverage)
        if not self.config.min_miscoverage <= alpha <= self.config.max_miscoverage:
            raise StateSpaceError(
                "state miscoverage is outside configured bounds",
                context={"reason": "invalid_conformal_state"},
            )
        if not isinstance(self.fingerprint, str) or len(self.fingerprint) != 64:
            raise StateSpaceError(
                "state fingerprint must be a SHA-256 hex digest",
                context={"reason": "invalid_conformal_state"},
            )

    @property
    def ready(self) -> bool:
        return len(self.scores) >= self.config.min_calibration_size

    @property
    def attainable_floor(self) -> float | None:
        if not self.scores:
            return None
        return attainable_miscoverage_floor(len(self.scores))

    def interval_for(
        self,
        forecast: LocationScaleForecast,
        *,
        target_index: int,
    ) -> ConformalInterval | None:
        _target_index(target_index)
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
            enforce_attainable=False,
        )


def evaluate_conformal_observations(
    observations: Sequence[ConformalObservation],
    *,
    config: ConformalConfig | None = None,
) -> ConformalReport:
    """Run leakage-safe prequential conformal calibration."""

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
    limited_count = 0

    for observation in values:
        prior_alpha = alpha
        effective_alpha: float | None = None
        interval: ConformalInterval | None = None
        covered: bool | None = None
        before = len(scores)
        if before >= actual_config.min_calibration_size:
            floor = attainable_miscoverage_floor(before)
            effective_alpha = max(prior_alpha, floor)
            interval = conformal_interval_from_scores(
                observation.forecast,
                scores,
                target_index=observation.target_index,
                miscoverage=prior_alpha,
                config=actual_config,
                enforce_attainable=False,
            )
            if interval.coverage_limited:
                limited_count += 1
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
                effective_miscoverage=effective_alpha,
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
        finite_sample_limited_intervals=limited_count,
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
    """Extract exact rolling scores and adaptive alpha for the next target."""

    verify_report_integrity(report)
    scores = [step.nonconformity_score for step in report.steps]
    window = report.config.calibration_window
    if window is not None and len(scores) > window:
        scores = scores[-window:]
    fingerprint = _state_fingerprint(
        report_fingerprint=report.fingerprint,
        horizon=report.horizon,
        scores=scores,
        current_miscoverage=report.final_miscoverage,
        config=report.config,
    )
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
    enforce_attainable: bool = True,
) -> ConformalInterval:
    """Build one interval from already-realized calibration scores.

    Direct callers fail closed on unattainable alpha by default. Streaming
    callers can set ``enforce_attainable=False`` to use and record the finite-
    sample floor explicitly.
    """

    actual_config = config or ConformalConfig(miscoverage=miscoverage)
    _target_index(target_index)
    _validate_forecast(forecast)
    requested_alpha = _open_unit_interval("miscoverage", miscoverage)
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
    floor = attainable_miscoverage_floor(len(clean_scores))
    if enforce_attainable and requested_alpha + 1e-15 < floor:
        raise StateSpaceError(
            "requested conformal coverage is unattainable with available calibration scores",
            context={
                "reason": "unattainable_conformal_miscoverage",
                "requested_miscoverage": requested_alpha,
                "attainable_miscoverage_floor": floor,
                "calibration_size": len(clean_scores),
                "required_calibration_size": required_calibration_size(requested_alpha),
            },
        )
    effective_alpha = max(requested_alpha, floor)
    quantile = finite_sample_conformal_quantile(
        clean_scores,
        miscoverage=effective_alpha,
    )
    scale = forecast_scale(forecast, config=actual_config)
    radius = quantile * scale if actual_config.normalized_scores else quantile
    radius = _finite_result("conformal_radius", radius)
    center = float(forecast.mean)
    lower = _finite_result("conformal_lower", center - radius)
    upper = _finite_result("conformal_upper", center + radius)
    return ConformalInterval(
        target_index=target_index,
        horizon=forecast.horizon,
        center=center,
        lower=lower,
        upper=upper,
        radius=radius,
        score_quantile=quantile,
        forecast_scale=scale,
        miscoverage=effective_alpha,
        requested_miscoverage=requested_alpha,
        attainable_miscoverage_floor=floor,
        calibration_size=len(clean_scores),
        normalized_scores=actual_config.normalized_scores,
    )


def finite_sample_conformal_quantile(
    scores: Sequence[float],
    *,
    miscoverage: float,
) -> float:
    """Return the finite-sample split-conformal order statistic.

    Requests below ``1/(n+1)`` fail closed instead of clipping to the largest
    observed score and overstating the requested coverage.
    """

    alpha = _open_unit_interval("miscoverage", miscoverage)
    clean = sorted(_non_negative("score", score) for score in scores)
    if not clean:
        raise StateSpaceError(
            "conformal quantile requires at least one score",
            context={"reason": "empty_conformal_scores"},
        )
    floor = attainable_miscoverage_floor(len(clean))
    if alpha + 1e-15 < floor:
        raise StateSpaceError(
            "requested conformal quantile is unattainable with available scores",
            context={
                "reason": "unattainable_conformal_miscoverage",
                "requested_miscoverage": alpha,
                "attainable_miscoverage_floor": floor,
                "calibration_size": len(clean),
                "required_calibration_size": required_calibration_size(alpha),
            },
        )
    rank = math.ceil((len(clean) + 1) * (1.0 - alpha))
    if rank < 1 or rank > len(clean):
        raise StateSpaceError(
            "conformal rank escaped finite calibration support",
            context={"reason": "numerical_instability", "rank": rank},
        )
    return clean[rank - 1]


def attainable_miscoverage_floor(calibration_size: int) -> float:
    """Smallest finite split-conformal alpha supported by ``calibration_size``."""

    if (
        isinstance(calibration_size, bool)
        or not isinstance(calibration_size, int)
        or calibration_size < 1
    ):
        raise StateSpaceError(
            "calibration_size must be a positive integer",
            context={"reason": "invalid_calibration_size"},
        )
    return 1.0 / (calibration_size + 1.0)


def required_calibration_size(miscoverage: float) -> int:
    """Minimum calibration size needed for a finite interval at ``miscoverage``."""

    alpha = _open_unit_interval("miscoverage", miscoverage)
    return max(1, math.ceil(1.0 / alpha - 1.0 - 1e-12))


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
    residual = _finite_result("absolute_residual", residual)
    if not actual_config.normalized_scores:
        return residual
    score = residual / forecast_scale(forecast, config=actual_config)
    return _finite_result("nonconformity_score", score)


def forecast_scale(
    forecast: LocationScaleForecast,
    *,
    config: ConformalConfig | None = None,
) -> float:
    """Positive predictive scale used by normalized nonconformity scores."""

    actual_config = config or ConformalConfig()
    _validate_forecast(forecast)
    scale = math.sqrt(float(forecast.variance))
    return max(actual_config.min_scale, _finite_result("forecast_scale", scale))


def observations_from_cross_family_report(report: object) -> tuple[ConformalObservation, ...]:
    """Adapt a cross-family report without coercing malformed target identity."""

    raw_steps = getattr(report, "steps", None)
    if raw_steps is None:
        raise StateSpaceError(
            "report does not expose prequential steps",
            context={"reason": "invalid_conformal_source_report"},
        )
    try:
        steps = tuple(raw_steps)
    except TypeError as exc:
        raise StateSpaceError(
            "report steps must be iterable",
            context={"reason": "invalid_conformal_source_report"},
        ) from exc
    if not steps:
        raise StateSpaceError(
            "source report contains no steps",
            context={"reason": "invalid_conformal_source_report"},
        )
    observations: list[ConformalObservation] = []
    for step in steps:
        try:
            target_index = step.target_index
            actual = step.actual
            forecast = step.predictive
        except AttributeError as exc:
            raise StateSpaceError(
                "report step does not satisfy conformal source contract",
                context={"reason": "invalid_conformal_source_report"},
            ) from exc
        observations.append(
            ConformalObservation(
                target_index=target_index,
                actual=actual,
                forecast=forecast,
            )
        )
    return tuple(observations)


def verify_report_integrity(report: ConformalReport) -> None:
    """Recompute report evidence identity and reject tampered report objects."""

    expected = _report_fingerprint(
        config=report.config,
        horizon=report.horizon,
        steps=report.steps,
        final_miscoverage=report.final_miscoverage,
    )
    if expected != report.fingerprint:
        raise StateSpaceError(
            "conformal report fingerprint mismatch",
            context={"reason": "conformal_report_integrity_failure"},
        )


def verify_state_integrity(
    state: ConformalCalibrationState,
    *,
    report_fingerprint: str,
) -> None:
    """Validate serialized state identity against the report it was derived from."""

    if not isinstance(report_fingerprint, str) or len(report_fingerprint) != 64:
        raise StateSpaceError(
            "report fingerprint must be a SHA-256 hex digest",
            context={"reason": "invalid_conformal_state"},
        )
    expected = _state_fingerprint(
        report_fingerprint=report_fingerprint,
        horizon=state.horizon,
        scores=state.scores,
        current_miscoverage=state.current_miscoverage,
        config=state.config,
    )
    if expected != state.fingerprint:
        raise StateSpaceError(
            "conformal state fingerprint mismatch",
            context={"reason": "conformal_state_integrity_failure"},
        )


def _validate_observation_sequence(
    observations: Sequence[ConformalObservation],
) -> None:
    previous_index: int | None = None
    horizon: int | None = None
    for observation in observations:
        if not isinstance(observation, ConformalObservation):
            raise StateSpaceError(
                "conformal observations must use ConformalObservation",
                context={"reason": "invalid_conformal_observation"},
            )
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
    try:
        horizon = getattr(forecast, "horizon")
        mean = getattr(forecast, "mean")
        variance = getattr(forecast, "variance")
    except (AttributeError, TypeError) as exc:
        raise StateSpaceError(
            "forecast does not satisfy conformal location-scale contract",
            context={"reason": "invalid_conformal_forecast"},
        ) from exc
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "conformal forecast horizon must be a positive integer",
            context={"reason": "invalid_conformal_forecast"},
        )
    _finite("forecast_mean", mean)
    _positive("forecast_variance", variance)


def _report_fingerprint(
    *,
    config: ConformalConfig,
    horizon: int,
    steps: Sequence[ConformalStep],
    final_miscoverage: float,
) -> str:
    parts = [
        "jeeves-prequential-conformal-v2",
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
                "none"
                if step.effective_miscoverage is None
                else format(step.effective_miscoverage, ".17g"),
                format(step.posterior_miscoverage, ".17g"),
                format(step.nonconformity_score, ".17g"),
                "none" if step.covered is None else str(int(step.covered)),
                str(step.calibration_size_before),
                str(step.calibration_size_after),
            )
        )
        if step.interval is not None:
            parts.extend(
                (
                    format(step.interval.lower, ".17g"),
                    format(step.interval.upper, ".17g"),
                    format(step.interval.score_quantile, ".17g"),
                    format(step.interval.miscoverage, ".17g"),
                    format(step.interval.requested_miscoverage, ".17g"),
                    str(step.interval.calibration_size),
                )
            )
    parts.append(format(final_miscoverage, ".17g"))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _state_fingerprint(
    *,
    report_fingerprint: str,
    horizon: int,
    scores: Sequence[float],
    current_miscoverage: float,
    config: ConformalConfig,
) -> str:
    return hashlib.sha256(
        "|".join(
            (
                "jeeves-conformal-state-v2",
                report_fingerprint,
                str(horizon),
                repr(config),
                ",".join(format(value, ".17g") for value in scores),
                format(current_miscoverage, ".17g"),
            )
        ).encode("utf-8")
    ).hexdigest()


def _target_index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StateSpaceError(
            "target_index must be a non-negative integer",
            context={"reason": "invalid_conformal_observation"},
        )
    return value


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


def _finite_result(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise StateSpaceError(
            f"{name} overflowed or became non-finite",
            context={"reason": "numerical_instability", "field": name},
        )
    return value


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
    "attainable_miscoverage_floor",
    "conformal_interval_from_scores",
    "evaluate_conformal_observations",
    "finite_sample_conformal_quantile",
    "forecast_scale",
    "nonconformity_score",
    "observations_from_cross_family_report",
    "required_calibration_size",
    "state_from_report",
    "verify_report_integrity",
    "verify_state_integrity",
]
