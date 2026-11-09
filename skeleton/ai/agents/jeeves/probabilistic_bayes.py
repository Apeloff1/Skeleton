"""Conjugate Bayesian trend forecasting with explicit parameter uncertainty.

The structural state-space models represent uncertainty in evolving latent state.
This module adds a complementary exact Bayesian regression primitive whose
predictive distribution integrates parameter and observation-variance uncertainty.

A Normal-Inverse-Gamma prior over a centered linear trend yields a Student-t
posterior predictive distribution. The implementation is dependency-light and
fully deterministic.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .probabilistic_state_space import SeriesValues, StateSpaceError

_EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class BayesianTrendConfig:
    prior_intercept_mean: float = 0.0
    prior_slope_mean: float = 0.0
    prior_intercept_precision: float = 1e-4
    prior_slope_precision: float = 1e-3
    alpha: float = 2.5
    beta: float = 1.0
    window: int | None = None

    def __post_init__(self) -> None:
        _finite("prior_intercept_mean", self.prior_intercept_mean)
        _finite("prior_slope_mean", self.prior_slope_mean)
        _positive("prior_intercept_precision", self.prior_intercept_precision)
        _positive("prior_slope_precision", self.prior_slope_precision)
        if _positive("alpha", self.alpha) <= 1.0:
            raise StateSpaceError(
                "alpha must exceed 1 so posterior observation variance has a finite mean",
                context={"reason": "invalid_bayesian_trend_config", "field": "alpha"},
            )
        _positive("beta", self.beta)
        if self.window is not None:
            if isinstance(self.window, bool) or not isinstance(self.window, int) or self.window < 3:
                raise StateSpaceError(
                    "window must be an integer >= 3 or None",
                    context={"reason": "invalid_bayesian_trend_config", "field": "window"},
                )


@dataclass(frozen=True, slots=True)
class StudentTForecast:
    horizon: int
    mean: float
    degrees_of_freedom: float
    scale_squared: float
    expected_noise_variance: float
    parameter_variance: float

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "horizon must be a positive integer",
                context={"reason": "invalid_bayesian_forecast"},
            )
        _finite("mean", self.mean)
        if _positive("degrees_of_freedom", self.degrees_of_freedom) <= 2.0:
            raise StateSpaceError(
                "predictive degrees of freedom must exceed 2",
                context={"reason": "invalid_bayesian_forecast"},
            )
        _positive("scale_squared", self.scale_squared)
        _positive("expected_noise_variance", self.expected_noise_variance)
        _non_negative("parameter_variance", self.parameter_variance)

    @property
    def variance(self) -> float:
        return self.scale_squared * self.degrees_of_freedom / (self.degrees_of_freedom - 2.0)

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(self.variance)

    @property
    def uncertainty_fraction_from_parameters(self) -> float:
        total = self.expected_noise_variance + self.parameter_variance
        return 0.0 if total <= _EPSILON else self.parameter_variance / total

    def moment_interval(self, z: float = 1.959963984540054) -> tuple[float, float]:
        """Moment-matched symmetric interval; not an exact Student-t quantile."""

        z = _positive("z", z)
        radius = z * self.standard_deviation
        return self.mean - radius, self.mean + radius

    def log_density(self, actual: float) -> float:
        actual = _finite("actual", actual)
        nu = self.degrees_of_freedom
        scale = self.scale_squared
        centered = actual - self.mean
        return (
            math.lgamma((nu + 1.0) / 2.0)
            - math.lgamma(nu / 2.0)
            - 0.5 * math.log(nu * math.pi * scale)
            - ((nu + 1.0) / 2.0) * math.log1p((centered * centered) / (nu * scale))
        )


@dataclass(frozen=True, slots=True)
class BayesianTrendFit:
    config: BayesianTrendConfig
    sample_count: int
    source_start_index: int
    center_x: float
    intercept_mean: float
    slope_mean: float
    precision_00: float
    precision_01: float
    precision_11: float
    covariance_scale_00: float
    covariance_scale_01: float
    covariance_scale_11: float
    posterior_alpha: float
    posterior_beta: float
    residual_sum_squares_at_mean: float
    fingerprint: str

    @property
    def expected_observation_variance(self) -> float:
        return self.posterior_beta / (self.posterior_alpha - 1.0)

    @property
    def slope_standard_deviation(self) -> float:
        return math.sqrt(
            self.expected_observation_variance * self.covariance_scale_11
        )

    def forecast(self, horizon: int = 1) -> StudentTForecast:
        return forecast_bayesian_trend(self, horizon=horizon)


@dataclass(frozen=True, slots=True)
class BayesianTrendFold:
    target_index: int
    actual: float
    forecast_mean: float
    forecast_variance: float
    log_score: float
    absolute_error: float
    squared_error: float
    parameter_uncertainty_fraction: float


@dataclass(frozen=True, slots=True)
class BayesianTrendEvaluation:
    folds: tuple[BayesianTrendFold, ...]
    mean_log_score: float
    mae: float
    rmse: float
    average_parameter_uncertainty_fraction: float
    fingerprint: str


def fit_bayesian_trend(
    series: SeriesValues | Sequence[float],
    *,
    config: BayesianTrendConfig | None = None,
) -> BayesianTrendFit:
    """Fit exact Normal-Inverse-Gamma Bayesian linear trend regression."""

    actual_config = config or BayesianTrendConfig()
    all_values = _coerce_values(series)
    if len(all_values) < 3:
        raise StateSpaceError(
            "Bayesian trend fitting requires at least three observations",
            context={"reason": "insufficient_history"},
        )

    source_start = 0
    values = all_values
    if actual_config.window is not None and len(values) > actual_config.window:
        source_start = len(values) - actual_config.window
        values = values[-actual_config.window :]

    count = len(values)
    absolute_x = tuple(float(source_start + index) for index in range(count))
    center_x = statistics.fmean(absolute_x)
    centered_x = tuple(value - center_x for value in absolute_x)

    sum_x = sum(centered_x)
    sum_xx = sum(value * value for value in centered_x)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(centered_x, values))

    prior_precision_00 = actual_config.prior_intercept_precision
    prior_precision_11 = actual_config.prior_slope_precision
    precision_00 = prior_precision_00 + count
    precision_01 = sum_x
    precision_11 = prior_precision_11 + sum_xx
    inverse_00, inverse_01, inverse_11 = _inverse_symmetric_2x2(
        precision_00,
        precision_01,
        precision_11,
    )

    rhs_0 = prior_precision_00 * actual_config.prior_intercept_mean + sum_y
    rhs_1 = prior_precision_11 * actual_config.prior_slope_mean + sum_xy
    intercept = inverse_00 * rhs_0 + inverse_01 * rhs_1
    slope = inverse_01 * rhs_0 + inverse_11 * rhs_1

    prior_quadratic = (
        prior_precision_00 * actual_config.prior_intercept_mean**2
        + prior_precision_11 * actual_config.prior_slope_mean**2
    )
    data_quadratic = sum(value * value for value in values)
    posterior_quadratic = intercept * rhs_0 + slope * rhs_1
    posterior_alpha = actual_config.alpha + 0.5 * count
    posterior_beta = actual_config.beta + 0.5 * (
        prior_quadratic + data_quadratic - posterior_quadratic
    )
    posterior_beta = max(_EPSILON, posterior_beta)

    residual_sum_squares = sum(
        (value - (intercept + slope * x)) ** 2
        for x, value in zip(centered_x, values)
    )
    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-bayesian-trend-v1",
                repr(actual_config),
                ",".join(format(value, ".17g") for value in values),
                str(source_start),
                format(center_x, ".17g"),
                format(intercept, ".17g"),
                format(slope, ".17g"),
                format(precision_00, ".17g"),
                format(precision_01, ".17g"),
                format(precision_11, ".17g"),
                format(posterior_alpha, ".17g"),
                format(posterior_beta, ".17g"),
            )
        ).encode("utf-8")
    ).hexdigest()
    return BayesianTrendFit(
        config=actual_config,
        sample_count=count,
        source_start_index=source_start,
        center_x=center_x,
        intercept_mean=intercept,
        slope_mean=slope,
        precision_00=precision_00,
        precision_01=precision_01,
        precision_11=precision_11,
        covariance_scale_00=inverse_00,
        covariance_scale_01=inverse_01,
        covariance_scale_11=inverse_11,
        posterior_alpha=posterior_alpha,
        posterior_beta=posterior_beta,
        residual_sum_squares_at_mean=residual_sum_squares,
        fingerprint=fingerprint,
    )


def forecast_bayesian_trend(
    fit: BayesianTrendFit,
    *,
    horizon: int = 1,
) -> StudentTForecast:
    """Posterior predictive Student-t distribution at a future absolute index."""

    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "horizon must be a positive integer",
            context={"reason": "invalid_horizon"},
        )
    last_absolute_index = fit.source_start_index + fit.sample_count - 1
    future_absolute_index = last_absolute_index + horizon
    centered_x = float(future_absolute_index) - fit.center_x
    mean = fit.intercept_mean + fit.slope_mean * centered_x

    leverage = (
        fit.covariance_scale_00
        + 2.0 * centered_x * fit.covariance_scale_01
        + centered_x * centered_x * fit.covariance_scale_11
    )
    leverage = max(0.0, leverage)
    expected_noise = fit.expected_observation_variance
    parameter_variance = expected_noise * leverage
    degrees_of_freedom = 2.0 * fit.posterior_alpha
    scale_squared = (
        fit.posterior_beta / fit.posterior_alpha
    ) * (1.0 + leverage)
    return StudentTForecast(
        horizon=horizon,
        mean=mean,
        degrees_of_freedom=degrees_of_freedom,
        scale_squared=max(_EPSILON, scale_squared),
        expected_noise_variance=expected_noise,
        parameter_variance=parameter_variance,
    )


def evaluate_bayesian_trend(
    series: SeriesValues | Sequence[float],
    *,
    min_train_size: int = 12,
    step: int = 1,
    config: BayesianTrendConfig | None = None,
) -> BayesianTrendEvaluation:
    """Leakage-safe expanding-window prequential evaluation."""

    values = _coerce_values(series)
    if isinstance(min_train_size, bool) or not isinstance(min_train_size, int) or min_train_size < 3:
        raise StateSpaceError(
            "min_train_size must be an integer >= 3",
            context={"reason": "invalid_bayesian_eval_config"},
        )
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise StateSpaceError(
            "step must be a positive integer",
            context={"reason": "invalid_bayesian_eval_config"},
        )
    if len(values) <= min_train_size:
        raise StateSpaceError(
            "series is too short for Bayesian trend evaluation",
            context={"reason": "insufficient_history"},
        )

    actual_config = config or BayesianTrendConfig()
    folds: list[BayesianTrendFold] = []
    for target_index in range(min_train_size, len(values), step):
        fit = fit_bayesian_trend(values[:target_index], config=actual_config)
        forecast = fit.forecast(1)
        actual = values[target_index]
        error = forecast.mean - actual
        folds.append(
            BayesianTrendFold(
                target_index=target_index,
                actual=actual,
                forecast_mean=forecast.mean,
                forecast_variance=forecast.variance,
                log_score=forecast.log_density(actual),
                absolute_error=abs(error),
                squared_error=error * error,
                parameter_uncertainty_fraction=forecast.uncertainty_fraction_from_parameters,
            )
        )

    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-bayesian-trend-eval-v1",
                repr(actual_config),
                str(min_train_size),
                str(step),
                *(
                    f"{fold.target_index}:{format(fold.log_score, '.17g')}:{format(fold.absolute_error, '.17g')}"
                    for fold in folds
                ),
            )
        ).encode("utf-8")
    ).hexdigest()
    return BayesianTrendEvaluation(
        folds=tuple(folds),
        mean_log_score=statistics.fmean(fold.log_score for fold in folds),
        mae=statistics.fmean(fold.absolute_error for fold in folds),
        rmse=math.sqrt(statistics.fmean(fold.squared_error for fold in folds)),
        average_parameter_uncertainty_fraction=statistics.fmean(
            fold.parameter_uncertainty_fraction for fold in folds
        ),
        fingerprint=fingerprint,
    )


def _inverse_symmetric_2x2(a: float, b: float, d: float) -> tuple[float, float, float]:
    determinant = a * d - b * b
    if not math.isfinite(determinant) or determinant <= _EPSILON:
        raise StateSpaceError(
            "Bayesian trend posterior precision is singular",
            context={"reason": "numerical_instability"},
        )
    return d / determinant, -b / determinant, a / determinant


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "Bayesian trend series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "Bayesian trend series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "Bayesian trend series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


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


__all__ = [
    "BayesianTrendConfig",
    "BayesianTrendEvaluation",
    "BayesianTrendFit",
    "BayesianTrendFold",
    "StudentTForecast",
    "evaluate_bayesian_trend",
    "fit_bayesian_trend",
    "forecast_bayesian_trend",
]
