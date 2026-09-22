"""Deterministic seasonal forecasting challengers for Jeeves.

The non-seasonal predictive stack already covers persistence, drift, Holt trends,
ridge autoregression, convex stacking, conformal calibration, and regime checks.
This module adds a deliberately small set of classical seasonal models:

* seasonal naive, a difficult-to-beat periodic baseline;
* additive Holt-Winters; and
* damped-trend additive Holt-Winters.

Every candidate is evaluated on the same expanding-window origins. The common
origin starts late enough to give the *largest* configured seasonal period two
complete cycles, preventing a long-period model from being compared on a newer,
easier evaluation window than a short-period model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Final

from skeleton.jeeves.historical_forecasting import ForecastSelectionPolicy, HistoricalForecastError, HistoricalSeries
from skeleton.jeeves.historical_models import canonical_fingerprint


_EPSILON: Final = 1e-12
MAX_SEASONAL_PERIOD: Final = 512
MAX_SEASONAL_GRID: Final = 768
DEFAULT_SEASONAL_PERIODS: Final = (4, 7, 12)
DEFAULT_SEASONAL_ALPHA_GRID: Final = (0.2, 0.5, 0.8)
DEFAULT_SEASONAL_BETA_GRID: Final = (0.1, 0.3)
DEFAULT_SEASONAL_GAMMA_GRID: Final = (0.1, 0.3, 0.5)
DEFAULT_SEASONAL_DAMPING_GRID: Final = (0.90, 0.98)


class HistoricalSeasonalError(HistoricalForecastError):
    """Fail-closed seasonal forecasting contract violation."""

    code = "JVS.HISTORICAL_SEASONAL"
    http_status = 422


class SeasonalMethod(str, Enum):
    SEASONAL_NAIVE = "seasonal_naive"
    ADDITIVE_HOLT_WINTERS = "additive_holt_winters"
    DAMPED_ADDITIVE_HOLT_WINTERS = "damped_additive_holt_winters"


@dataclass(frozen=True, slots=True)
class SeasonalParameters:
    period: int
    alpha: float | None = None
    beta: float | None = None
    gamma: float | None = None
    damping: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.period, bool) or not isinstance(self.period, int) or not 2 <= self.period <= MAX_SEASONAL_PERIOD:
            raise HistoricalSeasonalError(
                f"period must be between 2 and {MAX_SEASONAL_PERIOD}",
                context={"reason": "invalid_period"},
            )
        for name in ("alpha", "beta", "gamma", "damping"):
            value = getattr(self, name)
            if value is None:
                continue
            object.__setattr__(self, name, _unit_open(name, value))

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "period": self.period,
                "alpha": self.alpha,
                "beta": self.beta,
                "gamma": self.gamma,
                "damping": self.damping,
            }
        )


@dataclass(frozen=True, slots=True)
class FittedSeasonalForecast:
    method: SeasonalMethod
    parameters: SeasonalParameters
    level: float
    trend: float
    seasonal: tuple[float, ...]
    training_points: int
    residuals: tuple[float, ...]
    training_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.method, SeasonalMethod):
            raise HistoricalSeasonalError("method must be SeasonalMethod", context={"reason": "invalid_method"})
        if not isinstance(self.parameters, SeasonalParameters):
            raise HistoricalSeasonalError("parameters must be SeasonalParameters", context={"reason": "invalid_parameters"})
        if len(self.seasonal) != self.parameters.period:
            raise HistoricalSeasonalError(
                "seasonal state length must equal period",
                context={"reason": "seasonal_state_mismatch"},
            )
        object.__setattr__(self, "level", _finite("level", self.level))
        object.__setattr__(self, "trend", _finite("trend", self.trend))
        object.__setattr__(self, "seasonal", tuple(_finite("seasonal", item) for item in self.seasonal))
        if isinstance(self.training_points, bool) or not isinstance(self.training_points, int) or self.training_points <= 0:
            raise HistoricalSeasonalError("training_points must be positive", context={"reason": "invalid_training_points"})
        object.__setattr__(self, "residuals", tuple(_finite("residual", item) for item in self.residuals))
        if not isinstance(self.training_fingerprint, str) or not self.training_fingerprint:
            raise HistoricalSeasonalError("training_fingerprint is required", context={"reason": "missing_fingerprint"})

    def forecast(self, horizon: int) -> tuple[float, ...]:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise HistoricalSeasonalError("horizon must be positive", context={"reason": "invalid_horizon"})
        period = self.parameters.period
        result: list[float] = []
        for step in range(1, horizon + 1):
            phase = (self.training_points + step - 1) % period
            if self.method is SeasonalMethod.SEASONAL_NAIVE:
                result.append(self.seasonal[phase])
                continue
            damping = 1.0 if self.parameters.damping is None else self.parameters.damping
            trend_multiplier = sum(damping**index for index in range(1, step + 1))
            result.append(self.level + trend_multiplier * self.trend + self.seasonal[phase])
        return tuple(result)


@dataclass(frozen=True, slots=True)
class SeasonalHorizonMetrics:
    horizon: int
    sample_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    symmetric_mape: float
    median_absolute_error: float


@dataclass(frozen=True, slots=True)
class SeasonalEvaluation:
    method: SeasonalMethod
    parameters: SeasonalParameters
    horizons: tuple[SeasonalHorizonMetrics, ...]
    aggregate_mae: float
    aggregate_rmse: float
    aggregate_smape: float
    complexity_penalty: float
    objective: float
    origin_count: int
    common_origin_start: int
    residuals: tuple[float, ...]
    evaluation_fingerprint: str


@dataclass(frozen=True, slots=True)
class SeasonalSelectionPolicy:
    periods: tuple[int, ...] = DEFAULT_SEASONAL_PERIODS
    alpha_grid: tuple[float, ...] = DEFAULT_SEASONAL_ALPHA_GRID
    beta_grid: tuple[float, ...] = DEFAULT_SEASONAL_BETA_GRID
    gamma_grid: tuple[float, ...] = DEFAULT_SEASONAL_GAMMA_GRID
    damping_grid: tuple[float, ...] = DEFAULT_SEASONAL_DAMPING_GRID
    complexity_weight: float = 0.002

    def __post_init__(self) -> None:
        periods = tuple(sorted(set(_period(item) for item in self.periods)))
        if not periods:
            raise HistoricalSeasonalError("periods must not be empty", context={"reason": "empty_periods"})
        object.__setattr__(self, "periods", periods)
        alpha = _grid("alpha_grid", self.alpha_grid)
        beta = _grid("beta_grid", self.beta_grid)
        gamma = _grid("gamma_grid", self.gamma_grid)
        damping = _grid("damping_grid", self.damping_grid)
        combinations = len(periods) * (1 + len(alpha) * len(beta) * len(gamma) * (1 + len(damping)))
        if combinations > MAX_SEASONAL_GRID:
            raise HistoricalSeasonalError(
                "seasonal parameter grid is too large",
                context={"reason": "grid_too_large", "combinations": combinations, "maximum": MAX_SEASONAL_GRID},
            )
        object.__setattr__(self, "alpha_grid", alpha)
        object.__setattr__(self, "beta_grid", beta)
        object.__setattr__(self, "gamma_grid", gamma)
        object.__setattr__(self, "damping_grid", damping)
        complexity = _finite("complexity_weight", self.complexity_weight)
        if complexity < 0.0:
            raise HistoricalSeasonalError("complexity_weight must be non-negative", context={"reason": "negative_complexity"})
        object.__setattr__(self, "complexity_weight", complexity)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "periods": list(self.periods),
                "alpha_grid": list(self.alpha_grid),
                "beta_grid": list(self.beta_grid),
                "gamma_grid": list(self.gamma_grid),
                "damping_grid": list(self.damping_grid),
                "complexity_weight": self.complexity_weight,
            }
        )


@dataclass(frozen=True, slots=True)
class SeasonalTournamentReport:
    champion: SeasonalEvaluation
    candidates: tuple[SeasonalEvaluation, ...]
    series_fingerprint: str
    forecast_policy_fingerprint: str
    seasonal_policy_fingerprint: str
    common_origin_start: int
    report_fingerprint: str


class HistoricalSeasonalForecaster:
    """Fit transparent additive seasonal models."""

    @staticmethod
    def fit(
        series: HistoricalSeries,
        method: SeasonalMethod,
        parameters: SeasonalParameters,
    ) -> FittedSeasonalForecast:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalSeasonalError("series must be HistoricalSeries", context={"reason": "invalid_series"})
        if not isinstance(method, SeasonalMethod):
            raise HistoricalSeasonalError("method must be SeasonalMethod", context={"reason": "invalid_method"})
        if not isinstance(parameters, SeasonalParameters):
            raise HistoricalSeasonalError("parameters must be SeasonalParameters", context={"reason": "invalid_parameters"})
        values = series.values
        period = parameters.period
        if len(values) < 2 * period:
            raise HistoricalSeasonalError(
                "seasonal models require at least two complete cycles",
                context={"reason": "insufficient_cycles", "period": period, "points": len(values)},
            )

        if method is SeasonalMethod.SEASONAL_NAIVE:
            if any(value is not None for value in (parameters.alpha, parameters.beta, parameters.gamma, parameters.damping)):
                raise HistoricalSeasonalError(
                    "seasonal naive does not accept smoothing parameters",
                    context={"reason": "unexpected_parameters"},
                )
            seasonal = [0.0] * period
            for index in range(len(values) - period, len(values)):
                seasonal[index % period] = values[index]
            residuals = tuple(values[index] - values[index - period] for index in range(period, len(values)))
            return FittedSeasonalForecast(
                method=method,
                parameters=SeasonalParameters(period=period),
                level=0.0,
                trend=0.0,
                seasonal=tuple(seasonal),
                training_points=len(values),
                residuals=residuals,
                training_fingerprint=series.fingerprint,
            )

        alpha = parameters.alpha
        beta = parameters.beta
        gamma = parameters.gamma
        if alpha is None or beta is None or gamma is None:
            raise HistoricalSeasonalError(
                "Holt-Winters requires alpha, beta, and gamma",
                context={"reason": "missing_smoothing_parameters"},
            )
        damping = 1.0
        normalized_damping: float | None = None
        if method is SeasonalMethod.DAMPED_ADDITIVE_HOLT_WINTERS:
            if parameters.damping is None:
                raise HistoricalSeasonalError("damped Holt-Winters requires damping", context={"reason": "missing_damping"})
            damping = parameters.damping
            normalized_damping = damping
        elif parameters.damping is not None:
            raise HistoricalSeasonalError("plain Holt-Winters does not accept damping", context={"reason": "unexpected_damping"})

        first_mean = sum(values[:period]) / period
        second_mean = sum(values[period : 2 * period]) / period
        trend = (second_mean - first_mean) / period
        level = first_mean + (period - 1) * trend
        seasonal = [values[index] - first_mean - index * trend for index in range(period)]
        residuals: list[float] = []

        for index in range(period, len(values)):
            phase = index % period
            old_seasonal = seasonal[phase]
            one_step = level + damping * trend + old_seasonal
            observed = values[index]
            residuals.append(observed - one_step)
            prior_level = level
            level = alpha * (observed - old_seasonal) + (1.0 - alpha) * (level + damping * trend)
            trend = beta * (level - prior_level) + (1.0 - beta) * damping * trend
            seasonal[phase] = gamma * (observed - level) + (1.0 - gamma) * old_seasonal

        return FittedSeasonalForecast(
            method=method,
            parameters=SeasonalParameters(
                period=period,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                damping=normalized_damping,
            ),
            level=level,
            trend=trend,
            seasonal=tuple(seasonal),
            training_points=len(values),
            residuals=tuple(residuals),
            training_fingerprint=series.fingerprint,
        )


class HistoricalSeasonalTournament:
    """Rank seasonal challengers on a common expanding-window evaluation plane."""

    def __init__(
        self,
        *,
        forecast_policy: ForecastSelectionPolicy | None = None,
        seasonal_policy: SeasonalSelectionPolicy | None = None,
    ) -> None:
        self.forecast_policy = forecast_policy or ForecastSelectionPolicy()
        self.seasonal_policy = seasonal_policy or SeasonalSelectionPolicy()
        if not isinstance(self.forecast_policy, ForecastSelectionPolicy):
            raise HistoricalSeasonalError("forecast_policy must be ForecastSelectionPolicy", context={"reason": "invalid_forecast_policy"})
        if not isinstance(self.seasonal_policy, SeasonalSelectionPolicy):
            raise HistoricalSeasonalError("seasonal_policy must be SeasonalSelectionPolicy", context={"reason": "invalid_seasonal_policy"})

    @property
    def common_origin_start(self) -> int:
        return max(self.forecast_policy.minimum_training_points, 2 * max(self.seasonal_policy.periods))

    def run(self, series: HistoricalSeries) -> SeasonalTournamentReport:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalSeasonalError("series must be HistoricalSeries", context={"reason": "invalid_series"})
        max_horizon = max(self.forecast_policy.horizons)
        final_origin = len(series.observations) - max_horizon
        origin_count = final_origin - self.common_origin_start + 1
        if origin_count < self.forecast_policy.minimum_origins:
            minimum_required = self.common_origin_start + max_horizon + self.forecast_policy.minimum_origins - 1
            raise HistoricalSeasonalError(
                "series is too short for common seasonal rolling-origin evaluation",
                context={
                    "reason": "insufficient_backtest_history",
                    "points": len(series.observations),
                    "minimum_required": minimum_required,
                    "common_origin_start": self.common_origin_start,
                },
            )

        candidates: list[SeasonalEvaluation] = []
        for period in self.seasonal_policy.periods:
            candidates.append(
                self.evaluate(series, SeasonalMethod.SEASONAL_NAIVE, SeasonalParameters(period=period))
            )
            for alpha in self.seasonal_policy.alpha_grid:
                for beta in self.seasonal_policy.beta_grid:
                    for gamma in self.seasonal_policy.gamma_grid:
                        candidates.append(
                            self.evaluate(
                                series,
                                SeasonalMethod.ADDITIVE_HOLT_WINTERS,
                                SeasonalParameters(period=period, alpha=alpha, beta=beta, gamma=gamma),
                            )
                        )
                        for damping in self.seasonal_policy.damping_grid:
                            candidates.append(
                                self.evaluate(
                                    series,
                                    SeasonalMethod.DAMPED_ADDITIVE_HOLT_WINTERS,
                                    SeasonalParameters(
                                        period=period,
                                        alpha=alpha,
                                        beta=beta,
                                        gamma=gamma,
                                        damping=damping,
                                    ),
                                )
                            )

        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.objective,
                    item.aggregate_rmse,
                    item.aggregate_mae,
                    _complexity_rank(item.method),
                    item.parameters.period,
                    item.parameters.alpha or 0.0,
                    item.parameters.beta or 0.0,
                    item.parameters.gamma or 0.0,
                    item.parameters.damping or 0.0,
                    item.method.value,
                ),
            )
        )
        payload = {
            "series": series.fingerprint,
            "forecast_policy": self.forecast_policy.fingerprint,
            "seasonal_policy": self.seasonal_policy.fingerprint,
            "common_origin_start": self.common_origin_start,
            "champion": _evaluation_payload(ordered[0]),
            "candidates": [_evaluation_payload(item) for item in ordered],
        }
        return SeasonalTournamentReport(
            champion=ordered[0],
            candidates=ordered,
            series_fingerprint=series.fingerprint,
            forecast_policy_fingerprint=self.forecast_policy.fingerprint,
            seasonal_policy_fingerprint=self.seasonal_policy.fingerprint,
            common_origin_start=self.common_origin_start,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def evaluate(
        self,
        series: HistoricalSeries,
        method: SeasonalMethod,
        parameters: SeasonalParameters,
    ) -> SeasonalEvaluation:
        errors_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in self.forecast_policy.horizons}
        actuals_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in self.forecast_policy.horizons}
        residuals: list[float] = []
        max_horizon = max(self.forecast_policy.horizons)
        final_origin = len(series.observations) - max_horizon
        origin_count = 0

        for origin in range(self.common_origin_start, final_origin + 1):
            training = HistoricalSeries(
                series_id=f"{series.series_id}:seasonal-origin:{origin}",
                observations=series.observations[:origin],
            )
            fitted = HistoricalSeasonalForecaster.fit(training, method, parameters)
            predictions = fitted.forecast(max_horizon)
            origin_count += 1
            for horizon in self.forecast_policy.horizons:
                predicted = predictions[horizon - 1]
                actual = series.observations[origin + horizon - 1].value
                error = actual - predicted
                errors_by_horizon[horizon].append(error)
                actuals_by_horizon[horizon].append(actual)
                residuals.append(error)

        if origin_count < self.forecast_policy.minimum_origins:
            raise HistoricalSeasonalError(
                "not enough common rolling origins",
                context={"reason": "insufficient_origins", "origin_count": origin_count},
            )

        metrics = tuple(
            _metrics(horizon, errors_by_horizon[horizon], actuals_by_horizon[horizon])
            for horizon in self.forecast_policy.horizons
        )
        weights = self.forecast_policy.normalized_horizon_weights
        aggregate_mae = sum(weight * item.mean_absolute_error for weight, item in zip(weights, metrics, strict=True))
        aggregate_rmse = sum(weight * item.root_mean_squared_error for weight, item in zip(weights, metrics, strict=True))
        aggregate_smape = sum(weight * item.symmetric_mape for weight, item in zip(weights, metrics, strict=True))
        complexity = self.seasonal_policy.complexity_weight * _complexity_rank(method)

        calibration_values = series.values[: self.common_origin_start]
        scale = median(abs(value) for value in calibration_values)
        if scale <= _EPSILON:
            scale = max(1.0, max(abs(value) for value in calibration_values))
        metric_weight_sum = (
            self.forecast_policy.mae_weight
            + self.forecast_policy.rmse_weight
            + self.forecast_policy.smape_weight
        )
        objective = (
            self.forecast_policy.mae_weight * (aggregate_mae / scale)
            + self.forecast_policy.rmse_weight * (aggregate_rmse / scale)
            + self.forecast_policy.smape_weight * aggregate_smape
        ) / metric_weight_sum + complexity

        payload = {
            "series": series.fingerprint,
            "method": method.value,
            "parameters": parameters.fingerprint,
            "common_origin_start": self.common_origin_start,
            "origin_count": origin_count,
            "horizons": [
                {
                    "horizon": item.horizon,
                    "sample_count": item.sample_count,
                    "mae": item.mean_absolute_error,
                    "rmse": item.root_mean_squared_error,
                    "smape": item.symmetric_mape,
                    "median_ae": item.median_absolute_error,
                }
                for item in metrics
            ],
            "objective": objective,
        }
        return SeasonalEvaluation(
            method=method,
            parameters=parameters,
            horizons=metrics,
            aggregate_mae=aggregate_mae,
            aggregate_rmse=aggregate_rmse,
            aggregate_smape=aggregate_smape,
            complexity_penalty=complexity,
            objective=objective,
            origin_count=origin_count,
            common_origin_start=self.common_origin_start,
            residuals=tuple(residuals),
            evaluation_fingerprint=canonical_fingerprint(payload),
        )

    def fit_champion(self, series: HistoricalSeries) -> tuple[FittedSeasonalForecast, SeasonalTournamentReport]:
        report = self.run(series)
        champion = report.champion
        return HistoricalSeasonalForecaster.fit(series, champion.method, champion.parameters), report


def summarize_seasonal_tournament(report: SeasonalTournamentReport) -> dict[str, object]:
    return {
        "champion_method": report.champion.method.value,
        "champion_period": report.champion.parameters.period,
        "champion_objective": report.champion.objective,
        "candidate_count": len(report.candidates),
        "common_origin_start": report.common_origin_start,
        "series_fingerprint": report.series_fingerprint,
        "forecast_policy_fingerprint": report.forecast_policy_fingerprint,
        "seasonal_policy_fingerprint": report.seasonal_policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }


def _metrics(horizon: int, errors: list[float], actuals: list[float]) -> SeasonalHorizonMetrics:
    if not errors or len(errors) != len(actuals):
        raise HistoricalSeasonalError("metric inputs must align", context={"reason": "metric_input_mismatch"})
    absolute = [abs(error) for error in errors]
    mae = sum(absolute) / len(absolute)
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    smape_terms: list[float] = []
    for error, actual in zip(errors, actuals, strict=True):
        predicted = actual - error
        denominator = abs(actual) + abs(predicted)
        smape_terms.append(0.0 if denominator <= _EPSILON else 2.0 * abs(error) / denominator)
    return SeasonalHorizonMetrics(
        horizon=horizon,
        sample_count=len(errors),
        mean_absolute_error=mae,
        root_mean_squared_error=rmse,
        symmetric_mape=sum(smape_terms) / len(smape_terms),
        median_absolute_error=median(absolute),
    )


def _evaluation_payload(item: SeasonalEvaluation) -> dict[str, object]:
    return {
        "method": item.method.value,
        "parameters": item.parameters.fingerprint,
        "objective": item.objective,
        "rmse": item.aggregate_rmse,
        "mae": item.aggregate_mae,
        "smape": item.aggregate_smape,
        "origin_count": item.origin_count,
        "common_origin_start": item.common_origin_start,
        "evaluation_fingerprint": item.evaluation_fingerprint,
    }


def _complexity_rank(method: SeasonalMethod) -> int:
    if method is SeasonalMethod.SEASONAL_NAIVE:
        return 1
    if method is SeasonalMethod.ADDITIVE_HOLT_WINTERS:
        return 4
    return 5


def _period(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= MAX_SEASONAL_PERIOD:
        raise HistoricalSeasonalError(
            f"seasonal period must be between 2 and {MAX_SEASONAL_PERIOD}",
            context={"reason": "invalid_period"},
        )
    return value


def _grid(name: str, values: tuple[float, ...]) -> tuple[float, ...]:
    normalized = tuple(sorted(set(_unit_open(name, value) for value in values)))
    if not normalized:
        raise HistoricalSeasonalError(f"{name} must not be empty", context={"reason": "empty_grid", "field": name})
    return normalized


def _unit_open(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 < number <= 1.0:
        raise HistoricalSeasonalError(
            f"{name} must be greater than 0 and at most 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalSeasonalError(f"{name} must be numeric", context={"reason": "invalid_number", "field": name})
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalSeasonalError(f"{name} must be finite", context={"reason": "invalid_number", "field": name})
    return number