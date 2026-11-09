"""Probabilistic state-space forecasting primitives for Jeeves.

This module provides deterministic, offline mathematical forecasting utilities for
scalar time series. It intentionally avoids provider calls, market-data fetching,
order execution, and mutable learning state.

Design goals:
- explicit uncertainty rather than point forecasts only,
- numerically stable local-level/local-trend filtering,
- robust innovation handling for outliers,
- deterministic multi-step predictive distributions,
- online regime probabilities derived from observable innovation statistics,
- leakage-safe expanding-window family tournaments,
- reproducible fingerprints for evidence and regression tests.

The implementation is dependency-light on purpose so it can live inside the core
Jeeves evaluation surface without requiring NumPy/SciPy at import time. Objects
with a ``values`` attribute are accepted structurally, so the engine composes with
Jeeves historical-series contracts without importing an in-flight branch.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol, Sequence

from skeleton.kernel.errors import KernelError

_EPSILON = 1e-12
_MIN_VARIANCE = 1e-12
_MAX_VARIANCE = 1e18


class StateSpaceError(KernelError):
    """Fail-closed error for Jeeves probabilistic state-space operations."""

    code = "JEEVES.STATE_SPACE"
    http_status = 422


class SeriesValues(Protocol):
    """Structural adapter for existing Jeeves series containers."""

    values: Sequence[float]


class StateSpaceFamily(str, Enum):
    """Supported linear-Gaussian structural model families."""

    LOCAL_LEVEL = "local_level"
    LOCAL_LINEAR_TREND = "local_linear_trend"
    ROBUST_LOCAL_LINEAR_TREND = "robust_local_linear_trend"


class InnovationRegime(str, Enum):
    """Descriptive posterior regime labels based on recent innovations."""

    CALM = "calm"
    TRENDING = "trending"
    TURBULENT = "turbulent"
    SHOCK = "shock"


@dataclass(frozen=True, slots=True)
class StateSpaceConfig:
    """Configuration for structural state-space filtering.

    Variances are expressed in the same squared units as the observed series.
    When ``scale_variances`` is enabled the values are multiplied by a robust
    empirical scale squared, making one configuration portable across magnitudes.
    """

    family: StateSpaceFamily = StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND
    observation_variance: float = 0.10
    level_variance: float = 0.02
    trend_variance: float = 0.005
    initial_variance: float = 10.0
    robust_clip_sigma: float = 3.5
    regime_window: int = 12
    scale_variances: bool = True

    def __post_init__(self) -> None:
        _positive_finite("observation_variance", self.observation_variance)
        _non_negative_finite("level_variance", self.level_variance)
        _non_negative_finite("trend_variance", self.trend_variance)
        _positive_finite("initial_variance", self.initial_variance)
        clip = _positive_finite("robust_clip_sigma", self.robust_clip_sigma)
        if not 1.0 <= clip <= 20.0:
            raise StateSpaceError(
                "robust_clip_sigma must be between 1 and 20",
                context={"reason": "invalid_state_space_config", "field": "robust_clip_sigma"},
            )
        if isinstance(self.regime_window, bool) or not isinstance(self.regime_window, int) or self.regime_window < 3:
            raise StateSpaceError(
                "regime_window must be an integer >= 3",
                context={"reason": "invalid_state_space_config", "field": "regime_window"},
            )


@dataclass(frozen=True, slots=True)
class GaussianForecast:
    """One Gaussian predictive distribution for a future horizon."""

    horizon: int
    mean: float
    variance: float

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "forecast horizon must be positive",
                context={"reason": "invalid_horizon"},
            )
        _finite("mean", self.mean)
        _positive_finite("variance", self.variance)

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(self.variance)

    def interval(self, z: float = 1.959963984540054) -> tuple[float, float]:
        """Return a symmetric Gaussian interval using the supplied z-score."""

        z = _positive_finite("z", z)
        radius = z * self.standard_deviation
        return self.mean - radius, self.mean + radius

    def log_density(self, actual: float) -> float:
        """Proper logarithmic score contribution for one realized target."""

        return _gaussian_log_density(_finite("actual", actual) - self.mean, self.variance)


@dataclass(frozen=True, slots=True)
class FilterStep:
    """One posterior update in a state-space filter."""

    index: int
    observed: float
    prior_level: float
    prior_trend: float
    posterior_level: float
    posterior_trend: float
    innovation: float
    innovation_variance: float
    standardized_innovation: float
    effective_innovation: float
    log_likelihood: float
    level_variance: float
    trend_variance: float
    level_trend_covariance: float

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise StateSpaceError(
                "filter index must be a non-negative integer",
                context={"reason": "invalid_filter_step"},
            )
        for name in (
            "observed",
            "prior_level",
            "prior_trend",
            "posterior_level",
            "posterior_trend",
            "innovation",
            "innovation_variance",
            "standardized_innovation",
            "effective_innovation",
            "log_likelihood",
            "level_variance",
            "trend_variance",
            "level_trend_covariance",
        ):
            _finite(name, getattr(self, name))
        if self.innovation_variance <= 0.0 or self.level_variance < 0.0 or self.trend_variance < 0.0:
            raise StateSpaceError(
                "filter variances must remain valid",
                context={"reason": "invalid_filter_step_variance"},
            )


@dataclass(frozen=True, slots=True)
class RegimePosterior:
    """Soft descriptive regime probabilities computed from recent innovations."""

    calm: float
    trending: float
    turbulent: float
    shock: float

    def __post_init__(self) -> None:
        values = (self.calm, self.trending, self.turbulent, self.shock)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise StateSpaceError(
                "regime probabilities must be finite and non-negative",
                context={"reason": "invalid_regime_posterior"},
            )
        if abs(sum(values) - 1.0) > 1e-9:
            raise StateSpaceError(
                "regime probabilities must sum to one",
                context={"reason": "invalid_regime_posterior"},
            )

    @property
    def dominant(self) -> InnovationRegime:
        pairs = (
            (self.calm, InnovationRegime.CALM),
            (self.trending, InnovationRegime.TRENDING),
            (self.turbulent, InnovationRegime.TURBULENT),
            (self.shock, InnovationRegime.SHOCK),
        )
        return max(pairs, key=lambda item: (item[0], item[1].value))[1]

    def as_mapping(self) -> dict[str, float]:
        return {
            InnovationRegime.CALM.value: self.calm,
            InnovationRegime.TRENDING.value: self.trending,
            InnovationRegime.TURBULENT.value: self.turbulent,
            InnovationRegime.SHOCK.value: self.shock,
        }


@dataclass(frozen=True, slots=True)
class StateSpaceFit:
    """Immutable fitted structural model and its predictive surface."""

    family: StateSpaceFamily
    config: StateSpaceConfig
    scale: float
    observations: tuple[float, ...]
    steps: tuple[FilterStep, ...]
    posterior_level: float
    posterior_trend: float
    level_variance: float
    trend_variance: float
    level_trend_covariance: float
    observation_variance: float
    process_level_variance: float
    process_trend_variance: float
    log_likelihood: float
    regime: RegimePosterior
    fingerprint: str

    @property
    def sample_count(self) -> int:
        return len(self.observations)

    @property
    def average_log_likelihood(self) -> float:
        return self.log_likelihood / max(1, self.sample_count)

    def forecast(self, horizon: int = 1) -> GaussianForecast:
        return forecast_state_space(self, horizon=horizon)

    def forecast_path(self, horizons: Iterable[int]) -> tuple[GaussianForecast, ...]:
        requested = tuple(horizons)
        if not requested:
            raise StateSpaceError(
                "at least one forecast horizon is required",
                context={"reason": "empty_horizon_grid"},
            )
        if len(set(requested)) != len(requested):
            raise StateSpaceError(
                "forecast horizons must be unique",
                context={"reason": "duplicate_horizon"},
            )
        return tuple(self.forecast(horizon) for horizon in requested)


@dataclass(frozen=True, slots=True)
class StateSpaceScore:
    """Prequential score for one fitted family."""

    family: StateSpaceFamily
    folds: int
    mean_log_score: float
    rmse: float
    mae: float
    coverage_95: float
    average_interval_width_95: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class StateSpaceTournament:
    """Comparable prequential evaluation across structural families."""

    scores: tuple[StateSpaceScore, ...]
    ranking: tuple[StateSpaceFamily, ...]
    selected: StateSpaceFamily
    fingerprint: str

    def by_family(self, family: StateSpaceFamily) -> StateSpaceScore:
        for score in self.scores:
            if score.family is family:
                return score
        raise StateSpaceError(
            "family was not evaluated",
            context={"reason": "missing_family", "family": family.value},
        )


def fit_state_space(
    series: SeriesValues | Sequence[float],
    *,
    config: StateSpaceConfig | None = None,
) -> StateSpaceFit:
    """Fit a deterministic structural state-space model.

    For the robust family, standardized innovations are clipped before posterior
    correction. Predictive variance and likelihood still use the unmodified
    innovation covariance, preserving a clear separation between uncertainty
    representation and robust state correction.
    """

    actual_config = config or StateSpaceConfig()
    values = _coerce_values(series)
    if len(values) < 2:
        raise StateSpaceError(
            "state-space fitting requires at least two observations",
            context={"reason": "insufficient_history"},
        )

    scale = _series_scale(values)
    observation_variance, process_level_variance, process_trend_variance = _scaled_variances(
        actual_config, scale
    )

    level = values[0]
    trend = values[1] - values[0] if actual_config.family is not StateSpaceFamily.LOCAL_LEVEL else 0.0
    p00 = _bounded_variance(actual_config.initial_variance * scale * scale)
    p01 = 0.0
    p11 = 0.0 if actual_config.family is StateSpaceFamily.LOCAL_LEVEL else p00

    steps: list[FilterStep] = []
    total_log_likelihood = 0.0

    for index, observed in enumerate(values):
        if index == 0:
            prior_level = level
            prior_trend = trend
            prior_p00 = p00 + process_level_variance
            prior_p01 = p01
            prior_p11 = p11 + process_trend_variance
        elif actual_config.family is StateSpaceFamily.LOCAL_LEVEL:
            prior_level = level
            prior_trend = 0.0
            prior_p00 = p00 + process_level_variance
            prior_p01 = 0.0
            prior_p11 = 0.0
        else:
            prior_level = level + trend
            prior_trend = trend
            prior_p00 = p00 + 2.0 * p01 + p11 + process_level_variance
            prior_p01 = p01 + p11
            prior_p11 = p11 + process_trend_variance

        prior_p00 = _bounded_variance(prior_p00)
        prior_p11 = _bounded_non_negative(prior_p11)
        innovation = observed - prior_level
        innovation_variance = _bounded_variance(prior_p00 + observation_variance)
        innovation_std = math.sqrt(innovation_variance)
        standardized = innovation / innovation_std

        effective_innovation = innovation
        if actual_config.family is StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND:
            clipped = max(-actual_config.robust_clip_sigma, min(actual_config.robust_clip_sigma, standardized))
            effective_innovation = clipped * innovation_std

        k0 = prior_p00 / innovation_variance
        k1 = 0.0 if actual_config.family is StateSpaceFamily.LOCAL_LEVEL else prior_p01 / innovation_variance

        level = prior_level + k0 * effective_innovation
        trend = prior_trend + k1 * effective_innovation

        p00 = _bounded_variance((1.0 - k0) * prior_p00)
        p01 = (1.0 - k0) * prior_p01
        p11 = _bounded_non_negative(prior_p11 - k1 * prior_p01)
        if actual_config.family is StateSpaceFamily.LOCAL_LEVEL:
            p01 = 0.0
            p11 = 0.0

        log_likelihood = _gaussian_log_density(innovation, innovation_variance)
        total_log_likelihood += log_likelihood
        steps.append(
            FilterStep(
                index=index,
                observed=observed,
                prior_level=prior_level,
                prior_trend=prior_trend,
                posterior_level=level,
                posterior_trend=trend,
                innovation=innovation,
                innovation_variance=innovation_variance,
                standardized_innovation=standardized,
                effective_innovation=effective_innovation,
                log_likelihood=log_likelihood,
                level_variance=p00,
                trend_variance=p11,
                level_trend_covariance=p01,
            )
        )

    regime = _regime_posterior(steps, actual_config.regime_window)
    fingerprint = _fit_fingerprint(
        values=values,
        config=actual_config,
        scale=scale,
        level=level,
        trend=trend,
        p00=p00,
        p01=p01,
        p11=p11,
        observation_variance=observation_variance,
        process_level_variance=process_level_variance,
        process_trend_variance=process_trend_variance,
        log_likelihood=total_log_likelihood,
        regime=regime,
    )
    return StateSpaceFit(
        family=actual_config.family,
        config=actual_config,
        scale=scale,
        observations=values,
        steps=tuple(steps),
        posterior_level=level,
        posterior_trend=trend,
        level_variance=p00,
        trend_variance=p11,
        level_trend_covariance=p01,
        observation_variance=observation_variance,
        process_level_variance=process_level_variance,
        process_trend_variance=process_trend_variance,
        log_likelihood=total_log_likelihood,
        regime=regime,
        fingerprint=fingerprint,
    )


def forecast_state_space(fit: StateSpaceFit, *, horizon: int = 1) -> GaussianForecast:
    """Project one fitted state posterior forward without future observations."""

    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "forecast horizon must be a positive integer",
            context={"reason": "invalid_horizon"},
        )

    if fit.family is StateSpaceFamily.LOCAL_LEVEL:
        mean = fit.posterior_level
        state_variance = fit.level_variance + horizon * fit.process_level_variance
    else:
        mean = fit.posterior_level + horizon * fit.posterior_trend
        h = float(horizon)
        state_variance = (
            fit.level_variance
            + 2.0 * h * fit.level_trend_covariance
            + h * h * fit.trend_variance
            + h * fit.process_level_variance
            + _trend_process_accumulation(horizon) * fit.process_trend_variance
        )
    predictive_variance = _bounded_variance(state_variance + fit.observation_variance)
    return GaussianForecast(horizon=horizon, mean=mean, variance=predictive_variance)


def evaluate_state_space_families(
    series: SeriesValues | Sequence[float],
    *,
    min_train_size: int = 16,
    step: int = 1,
    families: Sequence[StateSpaceFamily] | None = None,
    base_config: StateSpaceConfig | None = None,
) -> StateSpaceTournament:
    """Run leakage-safe expanding-window prequential evaluation.

    Every target is scored using a model fitted only on the prefix ending before
    that target. Ranking prefers proper mean log score, then RMSE, MAE, interval
    width, and finally the stable family name.
    """

    values = _coerce_values(series)
    if isinstance(min_train_size, bool) or not isinstance(min_train_size, int) or min_train_size < 3:
        raise StateSpaceError(
            "min_train_size must be an integer >= 3",
            context={"reason": "invalid_tournament_config"},
        )
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise StateSpaceError(
            "step must be a positive integer",
            context={"reason": "invalid_tournament_config"},
        )
    if len(values) <= min_train_size:
        raise StateSpaceError(
            "series is too short for state-space tournament",
            context={"reason": "insufficient_history"},
        )

    requested = tuple(
        families
        or (
            StateSpaceFamily.LOCAL_LEVEL,
            StateSpaceFamily.LOCAL_LINEAR_TREND,
            StateSpaceFamily.ROBUST_LOCAL_LINEAR_TREND,
        )
    )
    if not requested or len(set(requested)) != len(requested):
        raise StateSpaceError(
            "state-space families must be non-empty and unique",
            context={"reason": "invalid_family_set"},
        )

    template = base_config or StateSpaceConfig()
    scores: list[StateSpaceScore] = []
    for family in requested:
        errors: list[float] = []
        squared_errors: list[float] = []
        log_scores: list[float] = []
        coverage: list[float] = []
        widths: list[float] = []

        for target_index in range(min_train_size, len(values), step):
            training = values[:target_index]
            config = StateSpaceConfig(
                family=family,
                observation_variance=template.observation_variance,
                level_variance=template.level_variance,
                trend_variance=template.trend_variance,
                initial_variance=template.initial_variance,
                robust_clip_sigma=template.robust_clip_sigma,
                regime_window=template.regime_window,
                scale_variances=template.scale_variances,
            )
            fit = fit_state_space(training, config=config)
            forecast = fit.forecast(1)
            actual = values[target_index]
            error = forecast.mean - actual
            errors.append(abs(error))
            squared_errors.append(error * error)
            log_scores.append(forecast.log_density(actual))
            lower, upper = forecast.interval()
            coverage.append(1.0 if lower <= actual <= upper else 0.0)
            widths.append(upper - lower)

        family_fingerprint = _score_fingerprint(
            family=family,
            errors=errors,
            squared_errors=squared_errors,
            log_scores=log_scores,
            coverage=coverage,
            widths=widths,
        )
        scores.append(
            StateSpaceScore(
                family=family,
                folds=len(errors),
                mean_log_score=statistics.fmean(log_scores),
                rmse=math.sqrt(statistics.fmean(squared_errors)),
                mae=statistics.fmean(errors),
                coverage_95=statistics.fmean(coverage),
                average_interval_width_95=statistics.fmean(widths),
                fingerprint=family_fingerprint,
            )
        )

    ranking = tuple(
        score.family
        for score in sorted(
            scores,
            key=lambda score: (
                -score.mean_log_score,
                score.rmse,
                score.mae,
                score.average_interval_width_95,
                score.family.value,
            ),
        )
    )
    tournament_fingerprint = hashlib.sha256(
        "|".join(
            [
                "state-space-tournament-v1",
                str(min_train_size),
                str(step),
                ",".join(family.value for family in ranking),
                *(score.fingerprint for score in scores),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return StateSpaceTournament(
        scores=tuple(scores),
        ranking=ranking,
        selected=ranking[0],
        fingerprint=tournament_fingerprint,
    )


def _regime_posterior(steps: Sequence[FilterStep], window: int) -> RegimePosterior:
    recent = tuple(steps[-window:])
    standardized = tuple(step.standardized_innovation for step in recent)
    abs_z = tuple(abs(value) for value in standardized)
    mean_abs_z = statistics.fmean(abs_z) if abs_z else 0.0
    max_abs_z = max(abs_z, default=0.0)
    signed_mean = statistics.fmean(standardized) if standardized else 0.0
    trend_magnitude = abs(steps[-1].posterior_trend) if steps else 0.0
    level_scale = max(abs(steps[-1].posterior_level) if steps else 0.0, 1.0)
    relative_trend = trend_magnitude / level_scale

    calm_score = math.exp(-1.5 * mean_abs_z) * math.exp(-8.0 * relative_trend)
    trend_score = (1.0 - math.exp(-10.0 * relative_trend)) * math.exp(-0.35 * mean_abs_z)
    turbulent_score = _sigmoid(1.75 * (mean_abs_z - 1.0)) * math.exp(-0.15 * max_abs_z)
    shock_score = _sigmoid(2.0 * (max_abs_z - 2.5)) * (0.75 + 0.25 * min(1.0, abs(signed_mean)))

    raw = [max(_EPSILON, value) for value in (calm_score, trend_score, turbulent_score, shock_score)]
    total = sum(raw)
    normalized = [value / total for value in raw]
    return RegimePosterior(
        calm=normalized[0],
        trending=normalized[1],
        turbulent=normalized[2],
        shock=normalized[3],
    )


def _scaled_variances(config: StateSpaceConfig, scale: float) -> tuple[float, float, float]:
    multiplier = scale * scale if config.scale_variances else 1.0
    observation = _bounded_variance(config.observation_variance * multiplier)
    level = _bounded_non_negative(config.level_variance * multiplier)
    trend = 0.0
    if config.family is not StateSpaceFamily.LOCAL_LEVEL:
        trend = _bounded_non_negative(config.trend_variance * multiplier)
    return observation, level, trend


def _series_scale(values: Sequence[float]) -> float:
    if len(values) < 2:
        return max(1.0, abs(values[0]))
    deltas = [right - left for left, right in zip(values, values[1:])]
    robust_delta = float(statistics.median(abs(delta) for delta in deltas))
    level = statistics.fmean(abs(value) for value in values)
    return max(1e-6, robust_delta, 0.01 * level, 1.0)


def _trend_process_accumulation(horizon: int) -> float:
    h = float(horizon)
    return h * (h + 1.0) * (2.0 * h + 1.0) / 6.0


def _gaussian_log_density(error: float, variance: float) -> float:
    variance = _bounded_variance(variance)
    return -0.5 * (math.log(2.0 * math.pi * variance) + (error * error) / variance)


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object
    if hasattr(series, "values"):
        raw = getattr(series, "values")
    else:
        raw = series
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "state-space series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "state-space series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "state-space series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _fit_fingerprint(
    *,
    values: Sequence[float],
    config: StateSpaceConfig,
    scale: float,
    level: float,
    trend: float,
    p00: float,
    p01: float,
    p11: float,
    observation_variance: float,
    process_level_variance: float,
    process_trend_variance: float,
    log_likelihood: float,
    regime: RegimePosterior,
) -> str:
    parts = [
        "jeeves-state-space-v1",
        config.family.value,
        repr(config),
        ",".join(format(value, ".17g") for value in values),
        format(scale, ".17g"),
        format(level, ".17g"),
        format(trend, ".17g"),
        format(p00, ".17g"),
        format(p01, ".17g"),
        format(p11, ".17g"),
        format(observation_variance, ".17g"),
        format(process_level_variance, ".17g"),
        format(process_trend_variance, ".17g"),
        format(log_likelihood, ".17g"),
        *(format(value, ".17g") for value in regime.as_mapping().values()),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _score_fingerprint(
    *,
    family: StateSpaceFamily,
    errors: Sequence[float],
    squared_errors: Sequence[float],
    log_scores: Sequence[float],
    coverage: Sequence[float],
    widths: Sequence[float],
) -> str:
    parts = [
        "jeeves-state-space-score-v1",
        family.value,
        ",".join(format(value, ".17g") for value in errors),
        ",".join(format(value, ".17g") for value in squared_errors),
        ",".join(format(value, ".17g") for value in log_scores),
        ",".join(format(value, ".17g") for value in coverage),
        ",".join(format(value, ".17g") for value in widths),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        exp_value = math.exp(-value)
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _bounded_variance(value: float) -> float:
    if not math.isfinite(value):
        raise StateSpaceError(
            "variance became non-finite",
            context={"reason": "numerical_instability"},
        )
    return min(_MAX_VARIANCE, max(_MIN_VARIANCE, value))


def _bounded_non_negative(value: float) -> float:
    if not math.isfinite(value):
        raise StateSpaceError(
            "variance became non-finite",
            context={"reason": "numerical_instability"},
        )
    return min(_MAX_VARIANCE, max(0.0, value))


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


def _positive_finite(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_state_space_config", "field": name},
        )
    return number


def _non_negative_finite(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_state_space_config", "field": name},
        )
    return number


__all__ = [
    "FilterStep",
    "GaussianForecast",
    "InnovationRegime",
    "RegimePosterior",
    "SeriesValues",
    "StateSpaceConfig",
    "StateSpaceError",
    "StateSpaceFamily",
    "StateSpaceFit",
    "StateSpaceScore",
    "StateSpaceTournament",
    "evaluate_state_space_families",
    "fit_state_space",
    "forecast_state_space",
]
