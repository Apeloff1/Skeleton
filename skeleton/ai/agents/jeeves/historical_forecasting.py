"""Deterministic time-series forecasting primitives for Jeeves.

This module extends the historical-model work from static benchmark ranking into
explicit temporal forecasting. It intentionally starts with transparent models
that are difficult to misuse or overfit silently:

* last-value and historical-mean baselines;
* linear drift;
* Holt level/trend exponential smoothing;
* damped Holt trend;
* expanding-window rolling-origin evaluation;
* deterministic hyper-parameter grids;
* multi-horizon error aggregation and complexity penalties;
* empirical residual intervals; and
* canonical fingerprints for replay/audit.

The implementation is dependency-free and does not pretend these simple models
are universally optimal. Their purpose is to give Jeeves a trustworthy,
inspectable forecasting baseline and model-selection harness before more complex
statistical or learned forecasters are admitted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Final

from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    HistoricalModelError,
    HistoricalModelRegistry,
    ModelIdentity,
    canonical_fingerprint,
)


_EPSILON: Final = 1e-12
DEFAULT_ALPHA_GRID: Final = (0.2, 0.4, 0.6, 0.8)
DEFAULT_BETA_GRID: Final = (0.1, 0.3, 0.5)
DEFAULT_DAMPING_GRID: Final = (0.80, 0.90, 0.95, 0.98)
MAX_GRID_COMBINATIONS: Final = 512
MAX_HORIZON: Final = 256
MAX_SERIES_POINTS: Final = 100_000


class HistoricalForecastError(HistoricalModelError):
    """Fail-closed forecasting contract violation."""

    code = "JVS.HISTORICAL_FORECAST"
    http_status = 422


class ForecastMethod(str, Enum):
    LAST_VALUE = "last_value"
    MEAN = "mean"
    DRIFT = "drift"
    HOLT = "holt"
    DAMPED_HOLT = "damped_holt"


@dataclass(frozen=True, slots=True)
class ForecastObservation:
    """One timestamped scalar observation."""

    timestamp: float
    value: float

    def __post_init__(self) -> None:
        timestamp = _finite("timestamp", self.timestamp)
        value = _finite("value", self.value)
        if timestamp < 0.0:
            raise HistoricalForecastError(
                "timestamp must be non-negative",
                context={"reason": "invalid_timestamp"},
            )
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class HistoricalSeries:
    """Strictly ordered immutable scalar series."""

    series_id: str
    observations: tuple[ForecastObservation, ...]

    def __post_init__(self) -> None:
        series_id = _bounded_text("series_id", self.series_id)
        observations = tuple(self.observations)
        if not observations:
            raise HistoricalForecastError(
                "series must contain at least one observation",
                context={"reason": "empty_series"},
            )
        if len(observations) > MAX_SERIES_POINTS:
            raise HistoricalForecastError(
                "series exceeds point limit",
                context={"reason": "series_too_large", "max_points": MAX_SERIES_POINTS},
            )
        if any(not isinstance(item, ForecastObservation) for item in observations):
            raise HistoricalForecastError(
                "observations must contain ForecastObservation values",
                context={"reason": "invalid_observation"},
            )
        prior = -math.inf
        for item in observations:
            if item.timestamp <= prior:
                raise HistoricalForecastError(
                    "series timestamps must be strictly increasing",
                    context={"reason": "non_monotonic_time", "timestamp": item.timestamp},
                )
            prior = item.timestamp
        object.__setattr__(self, "series_id", series_id)
        object.__setattr__(self, "observations", observations)

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(item.value for item in self.observations)

    @property
    def timestamps(self) -> tuple[float, ...]:
        return tuple(item.timestamp for item in self.observations)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "series_id": self.series_id,
                "observations": [
                    {"timestamp": item.timestamp, "value": item.value}
                    for item in self.observations
                ],
            }
        )

    def prefix(self, count: int) -> "HistoricalSeries":
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise HistoricalForecastError(
                "prefix count must be a positive integer",
                context={"reason": "invalid_prefix"},
            )
        if count > len(self.observations):
            raise HistoricalForecastError(
                "prefix count exceeds series length",
                context={"reason": "prefix_too_large"},
            )
        return HistoricalSeries(
            series_id=f"{self.series_id}:prefix:{count}",
            observations=self.observations[:count],
        )


@dataclass(frozen=True, slots=True)
class ForecastParameters:
    alpha: float | None = None
    beta: float | None = None
    damping: float | None = None

    def __post_init__(self) -> None:
        for name in ("alpha", "beta", "damping"):
            value = getattr(self, name)
            if value is None:
                continue
            unit = _unit_open(name, value)
            object.__setattr__(self, name, unit)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {"alpha": self.alpha, "beta": self.beta, "damping": self.damping}
        )


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    horizon: int
    predicted: float
    lower: float | None = None
    upper: float | None = None

    def __post_init__(self) -> None:
        horizon = _positive_int("horizon", self.horizon, maximum=MAX_HORIZON)
        predicted = _finite("predicted", self.predicted)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "predicted", predicted)
        if self.lower is not None:
            object.__setattr__(self, "lower", _finite("lower", self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", _finite("upper", self.upper))
        if self.lower is not None and self.upper is not None:
            if self.lower > predicted + _EPSILON or self.upper + _EPSILON < predicted:
                raise HistoricalForecastError(
                    "forecast interval must contain prediction",
                    context={"reason": "invalid_interval"},
                )
            if self.lower > self.upper:
                raise HistoricalForecastError(
                    "forecast lower bound exceeds upper bound",
                    context={"reason": "invalid_interval"},
                )


@dataclass(frozen=True, slots=True)
class FittedForecast:
    method: ForecastMethod
    parameters: ForecastParameters
    level: float
    trend: float
    training_points: int
    residuals: tuple[float, ...]
    training_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.method, ForecastMethod):
            raise HistoricalForecastError(
                "method must be ForecastMethod",
                context={"reason": "invalid_method"},
            )
        if not isinstance(self.parameters, ForecastParameters):
            raise HistoricalForecastError(
                "parameters must be ForecastParameters",
                context={"reason": "invalid_parameters"},
            )
        object.__setattr__(self, "level", _finite("level", self.level))
        object.__setattr__(self, "trend", _finite("trend", self.trend))
        object.__setattr__(self, "training_points", _positive_int("training_points", self.training_points))
        residuals = tuple(_finite("residual", value) for value in self.residuals)
        object.__setattr__(self, "residuals", residuals)
        object.__setattr__(self, "training_fingerprint", _bounded_text("training_fingerprint", self.training_fingerprint, 256))

    def forecast(self, horizon: int, *, interval_coverage: float | None = None) -> tuple[ForecastPoint, ...]:
        horizon = _positive_int("horizon", horizon, maximum=MAX_HORIZON)
        if interval_coverage is not None:
            interval_coverage = _unit_open("interval_coverage", interval_coverage)
        predictions = tuple(self._predict(step) for step in range(1, horizon + 1))
        if interval_coverage is None or not self.residuals:
            return tuple(ForecastPoint(horizon=index + 1, predicted=value) for index, value in enumerate(predictions))

        absolute = sorted(abs(value) for value in self.residuals)
        radius = _empirical_quantile(absolute, interval_coverage)
        points: list[ForecastPoint] = []
        for index, value in enumerate(predictions, start=1):
            # This is an empirical robustness band, not a parametric confidence
            # interval. sqrt(h) expands uncertainty without assuming Gaussian
            # innovations or fabricating precision the data cannot support.
            spread = radius * math.sqrt(index)
            points.append(
                ForecastPoint(
                    horizon=index,
                    predicted=value,
                    lower=value - spread,
                    upper=value + spread,
                )
            )
        return tuple(points)

    def _predict(self, horizon: int) -> float:
        if self.method is ForecastMethod.MEAN or self.method is ForecastMethod.LAST_VALUE:
            return self.level
        if self.method is ForecastMethod.DRIFT or self.method is ForecastMethod.HOLT:
            return self.level + horizon * self.trend
        damping = self.parameters.damping
        if damping is None:
            raise HistoricalForecastError(
                "damped Holt fit is missing damping parameter",
                context={"reason": "missing_damping"},
            )
        trend_multiplier = sum(damping**step for step in range(1, horizon + 1))
        return self.level + trend_multiplier * self.trend


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    horizon: int
    sample_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    symmetric_mape: float
    median_absolute_error: float


@dataclass(frozen=True, slots=True)
class ForecastEvaluation:
    method: ForecastMethod
    parameters: ForecastParameters
    horizons: tuple[HorizonMetrics, ...]
    aggregate_mae: float
    aggregate_rmse: float
    aggregate_smape: float
    complexity_penalty: float
    objective: float
    origin_count: int
    residuals: tuple[float, ...]
    evaluation_fingerprint: str

    @property
    def percent_error(self) -> float:
        """UI-friendly symmetric percentage error."""
        return round(self.aggregate_smape * 100.0, 2)


@dataclass(frozen=True, slots=True)
class ForecastTournamentReport:
    champion: ForecastEvaluation
    candidates: tuple[ForecastEvaluation, ...]
    series_fingerprint: str
    policy_fingerprint: str
    report_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForecastSelectionPolicy:
    """Rolling-origin model-selection contract."""

    horizons: tuple[int, ...] = (1, 2, 4)
    minimum_training_points: int = 6
    minimum_origins: int = 3
    horizon_weights: tuple[float, ...] | None = None
    mae_weight: float = 0.55
    rmse_weight: float = 0.30
    smape_weight: float = 0.15
    complexity_weight: float = 0.002
    alpha_grid: tuple[float, ...] = DEFAULT_ALPHA_GRID
    beta_grid: tuple[float, ...] = DEFAULT_BETA_GRID
    damping_grid: tuple[float, ...] = DEFAULT_DAMPING_GRID

    def __post_init__(self) -> None:
        horizons = tuple(_positive_int("horizon", value, maximum=MAX_HORIZON) for value in self.horizons)
        if not horizons:
            raise HistoricalForecastError(
                "horizons must not be empty",
                context={"reason": "empty_horizons"},
            )
        if len(set(horizons)) != len(horizons):
            raise HistoricalForecastError(
                "horizons must be unique",
                context={"reason": "duplicate_horizon"},
            )
        object.__setattr__(self, "horizons", tuple(sorted(horizons)))
        object.__setattr__(self, "minimum_training_points", _positive_int("minimum_training_points", self.minimum_training_points))
        object.__setattr__(self, "minimum_origins", _positive_int("minimum_origins", self.minimum_origins))

        metric_weights = tuple(
            _non_negative(name, value)
            for name, value in (
                ("mae_weight", self.mae_weight),
                ("rmse_weight", self.rmse_weight),
                ("smape_weight", self.smape_weight),
                ("complexity_weight", self.complexity_weight),
            )
        )
        object.__setattr__(self, "mae_weight", metric_weights[0])
        object.__setattr__(self, "rmse_weight", metric_weights[1])
        object.__setattr__(self, "smape_weight", metric_weights[2])
        object.__setattr__(self, "complexity_weight", metric_weights[3])
        if self.mae_weight + self.rmse_weight + self.smape_weight <= _EPSILON:
            raise HistoricalForecastError(
                "at least one forecast error metric must have positive weight",
                context={"reason": "zero_metric_weights"},
            )

        if self.horizon_weights is None:
            horizon_weights = tuple(1.0 / horizon for horizon in self.horizons)
        else:
            horizon_weights = tuple(_positive("horizon_weight", value) for value in self.horizon_weights)
            if len(horizon_weights) != len(self.horizons):
                raise HistoricalForecastError(
                    "horizon_weights length must match horizons",
                    context={"reason": "horizon_weight_mismatch"},
                )
        object.__setattr__(self, "horizon_weights", horizon_weights)

        alpha_grid = _grid("alpha_grid", self.alpha_grid)
        beta_grid = _grid("beta_grid", self.beta_grid)
        damping_grid = _grid("damping_grid", self.damping_grid)
        if len(alpha_grid) * len(beta_grid) * max(1, len(damping_grid)) > MAX_GRID_COMBINATIONS:
            raise HistoricalForecastError(
                "forecast parameter grid is too large",
                context={"reason": "grid_too_large", "max_combinations": MAX_GRID_COMBINATIONS},
            )
        object.__setattr__(self, "alpha_grid", alpha_grid)
        object.__setattr__(self, "beta_grid", beta_grid)
        object.__setattr__(self, "damping_grid", damping_grid)

    @property
    def normalized_horizon_weights(self) -> tuple[float, ...]:
        assert self.horizon_weights is not None
        total = sum(self.horizon_weights)
        return tuple(value / total for value in self.horizon_weights)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "horizons": list(self.horizons),
                "minimum_training_points": self.minimum_training_points,
                "minimum_origins": self.minimum_origins,
                "horizon_weights": list(self.horizon_weights or ()),
                "mae_weight": self.mae_weight,
                "rmse_weight": self.rmse_weight,
                "smape_weight": self.smape_weight,
                "complexity_weight": self.complexity_weight,
                "alpha_grid": list(self.alpha_grid),
                "beta_grid": list(self.beta_grid),
                "damping_grid": list(self.damping_grid),
            }
        )


class HistoricalForecaster:
    """Fit deterministic scalar forecasting models."""

    @staticmethod
    def fit(
        series: HistoricalSeries,
        method: ForecastMethod,
        parameters: ForecastParameters | None = None,
    ) -> FittedForecast:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalForecastError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        if not isinstance(method, ForecastMethod):
            raise HistoricalForecastError(
                "method must be ForecastMethod",
                context={"reason": "invalid_method"},
            )
        parameters = parameters or ForecastParameters()
        if not isinstance(parameters, ForecastParameters):
            raise HistoricalForecastError(
                "parameters must be ForecastParameters",
                context={"reason": "invalid_parameters"},
            )
        values = series.values

        if method is ForecastMethod.LAST_VALUE:
            residuals = tuple(values[index] - values[index - 1] for index in range(1, len(values)))
            return FittedForecast(
                method=method,
                parameters=ForecastParameters(),
                level=values[-1],
                trend=0.0,
                training_points=len(values),
                residuals=residuals,
                training_fingerprint=series.fingerprint,
            )

        if method is ForecastMethod.MEAN:
            level = sum(values) / len(values)
            residuals = tuple(value - level for value in values)
            return FittedForecast(
                method=method,
                parameters=ForecastParameters(),
                level=level,
                trend=0.0,
                training_points=len(values),
                residuals=residuals,
                training_fingerprint=series.fingerprint,
            )

        if len(values) < 2:
            raise HistoricalForecastError(
                "trend models require at least two observations",
                context={"reason": "insufficient_points", "method": method.value},
            )

        if method is ForecastMethod.DRIFT:
            trend = (values[-1] - values[0]) / (len(values) - 1)
            residuals = tuple(
                values[index] - (values[0] + index * trend)
                for index in range(1, len(values))
            )
            return FittedForecast(
                method=method,
                parameters=ForecastParameters(),
                level=values[-1],
                trend=trend,
                training_points=len(values),
                residuals=residuals,
                training_fingerprint=series.fingerprint,
            )

        alpha = parameters.alpha
        beta = parameters.beta
        if alpha is None or beta is None:
            raise HistoricalForecastError(
                "Holt models require alpha and beta",
                context={"reason": "missing_smoothing_parameters", "method": method.value},
            )
        damping = 1.0
        if method is ForecastMethod.DAMPED_HOLT:
            if parameters.damping is None:
                raise HistoricalForecastError(
                    "damped Holt requires damping",
                    context={"reason": "missing_damping"},
                )
            damping = parameters.damping
        elif parameters.damping is not None:
            raise HistoricalForecastError(
                "plain Holt does not accept damping",
                context={"reason": "unexpected_damping"},
            )

        level = values[0]
        trend = values[1] - values[0]
        residuals: list[float] = []
        for observed in values[1:]:
            one_step = level + damping * trend
            residuals.append(observed - one_step)
            prior_level = level
            level = alpha * observed + (1.0 - alpha) * one_step
            trend = beta * (level - prior_level) + (1.0 - beta) * damping * trend

        normalized = ForecastParameters(
            alpha=alpha,
            beta=beta,
            damping=parameters.damping if method is ForecastMethod.DAMPED_HOLT else None,
        )
        return FittedForecast(
            method=method,
            parameters=normalized,
            level=level,
            trend=trend,
            training_points=len(values),
            residuals=tuple(residuals),
            training_fingerprint=series.fingerprint,
        )


class HistoricalForecastTournament:
    """Select the strongest transparent forecaster by rolling-origin evidence."""

    def __init__(self, policy: ForecastSelectionPolicy | None = None) -> None:
        self.policy = policy or ForecastSelectionPolicy()
        if not isinstance(self.policy, ForecastSelectionPolicy):
            raise HistoricalForecastError(
                "policy must be ForecastSelectionPolicy",
                context={"reason": "invalid_policy"},
            )

    def run(self, series: HistoricalSeries) -> ForecastTournamentReport:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalForecastError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        max_horizon = max(self.policy.horizons)
        minimum_required = self.policy.minimum_training_points + max_horizon + self.policy.minimum_origins - 1
        if len(series.observations) < minimum_required:
            raise HistoricalForecastError(
                "series is too short for requested rolling-origin evaluation",
                context={
                    "reason": "insufficient_backtest_history",
                    "points": len(series.observations),
                    "minimum_required": minimum_required,
                },
            )

        candidates: list[ForecastEvaluation] = []
        candidates.append(self.evaluate(series, ForecastMethod.LAST_VALUE, ForecastParameters()))
        candidates.append(self.evaluate(series, ForecastMethod.MEAN, ForecastParameters()))
        candidates.append(self.evaluate(series, ForecastMethod.DRIFT, ForecastParameters()))

        for alpha in self.policy.alpha_grid:
            for beta in self.policy.beta_grid:
                candidates.append(
                    self.evaluate(
                        series,
                        ForecastMethod.HOLT,
                        ForecastParameters(alpha=alpha, beta=beta),
                    )
                )
                for damping in self.policy.damping_grid:
                    candidates.append(
                        self.evaluate(
                            series,
                            ForecastMethod.DAMPED_HOLT,
                            ForecastParameters(alpha=alpha, beta=beta, damping=damping),
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
                    item.parameters.alpha or 0.0,
                    item.parameters.beta or 0.0,
                    item.parameters.damping or 0.0,
                    item.method.value,
                ),
            )
        )
        payload = {
            "series": series.fingerprint,
            "policy": self.policy.fingerprint,
            "champion": _evaluation_payload(ordered[0]),
            "candidates": [_evaluation_payload(item) for item in ordered],
        }
        return ForecastTournamentReport(
            champion=ordered[0],
            candidates=ordered,
            series_fingerprint=series.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def evaluate(
        self,
        series: HistoricalSeries,
        method: ForecastMethod,
        parameters: ForecastParameters,
    ) -> ForecastEvaluation:
        errors_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in self.policy.horizons}
        actuals_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in self.policy.horizons}
        residuals: list[float] = []
        max_horizon = max(self.policy.horizons)
        final_origin = len(series.observations) - max_horizon
        origins = range(self.policy.minimum_training_points, final_origin + 1)

        origin_count = 0
        for origin in origins:
            training = HistoricalSeries(
                series_id=f"{series.series_id}:origin:{origin}",
                observations=series.observations[:origin],
            )
            fitted = HistoricalForecaster.fit(training, method, parameters)
            predictions = fitted.forecast(max_horizon)
            origin_count += 1
            for horizon in self.policy.horizons:
                predicted = predictions[horizon - 1].predicted
                actual = series.observations[origin + horizon - 1].value
                error = actual - predicted
                errors_by_horizon[horizon].append(error)
                actuals_by_horizon[horizon].append(actual)
                residuals.append(error)

        if origin_count < self.policy.minimum_origins:
            raise HistoricalForecastError(
                "not enough rolling origins for evaluation",
                context={
                    "reason": "insufficient_origins",
                    "origin_count": origin_count,
                    "minimum_origins": self.policy.minimum_origins,
                },
            )

        horizon_metrics = tuple(
            _metrics(
                horizon,
                errors_by_horizon[horizon],
                actuals_by_horizon[horizon],
            )
            for horizon in self.policy.horizons
        )
        weights = self.policy.normalized_horizon_weights
        aggregate_mae = sum(
            weight * item.mean_absolute_error
            for weight, item in zip(weights, horizon_metrics, strict=True)
        )
        aggregate_rmse = sum(
            weight * item.root_mean_squared_error
            for weight, item in zip(weights, horizon_metrics, strict=True)
        )
        aggregate_smape = sum(
            weight * item.symmetric_mape
            for weight, item in zip(weights, horizon_metrics, strict=True)
        )
        complexity = self.policy.complexity_weight * _complexity_rank(method)

        # Selection normalization is derived only from the initial training
        # window available before the first forecast origin. Using the complete
        # series here would leak future evaluation magnitudes into the relative
        # weighting of MAE/RMSE versus sMAPE and could change the winner.
        calibration_values = series.values[: self.policy.minimum_training_points]
        scale = median(abs(value) for value in calibration_values)
        if scale <= _EPSILON:
            scale = max(1.0, max(abs(value) for value in calibration_values))
        normalized_mae = aggregate_mae / scale
        normalized_rmse = aggregate_rmse / scale
        objective = (
            self.policy.mae_weight * normalized_mae
            + self.policy.rmse_weight * normalized_rmse
            + self.policy.smape_weight * aggregate_smape
            + complexity
        )
        payload = {
            "series": series.fingerprint,
            "method": method.value,
            "parameters": parameters.fingerprint,
            "policy": self.policy.fingerprint,
            "normalization_scale": scale,
            "horizons": [
                {
                    "horizon": item.horizon,
                    "samples": item.sample_count,
                    "mae": item.mean_absolute_error,
                    "rmse": item.root_mean_squared_error,
                    "smape": item.symmetric_mape,
                    "median_ae": item.median_absolute_error,
                }
                for item in horizon_metrics
            ],
            "objective": objective,
        }
        return ForecastEvaluation(
            method=method,
            parameters=parameters,
            horizons=horizon_metrics,
            aggregate_mae=aggregate_mae,
            aggregate_rmse=aggregate_rmse,
            aggregate_smape=aggregate_smape,
            complexity_penalty=complexity,
            objective=objective,
            origin_count=origin_count,
            residuals=tuple(residuals),
            evaluation_fingerprint=canonical_fingerprint(payload),
        )

    def fit_champion(self, series: HistoricalSeries) -> tuple[FittedForecast, ForecastTournamentReport]:
        report = self.run(series)
        fitted = HistoricalForecaster.fit(series, report.champion.method, report.champion.parameters)
        # Final level/trend are fit on all available history, but interval
        # calibration uses genuinely out-of-sample rolling-origin errors from
        # model selection rather than optimistic in-sample fit residuals.
        calibrated = FittedForecast(
            method=fitted.method,
            parameters=fitted.parameters,
            level=fitted.level,
            trend=fitted.trend,
            training_points=fitted.training_points,
            residuals=report.champion.residuals,
            training_fingerprint=fitted.training_fingerprint,
        )
        return calibrated, report


def series_from_registry(
    registry: HistoricalModelRegistry,
    *,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
) -> HistoricalSeries:
    """Build a normalized benchmark time series from the historical registry.

    Only the exact model revision and exact benchmark revision participate. This
    prevents accidental mixing of generations or normalization contracts.
    """
    if not isinstance(registry, HistoricalModelRegistry):
        raise HistoricalForecastError(
            "registry must be HistoricalModelRegistry",
            context={"reason": "invalid_registry"},
        )
    if not isinstance(model, ModelIdentity):
        raise HistoricalForecastError(
            "model must be ModelIdentity",
            context={"reason": "invalid_model"},
        )
    if not isinstance(benchmark, BenchmarkDefinition):
        raise HistoricalForecastError(
            "benchmark must be BenchmarkDefinition",
            context={"reason": "invalid_benchmark"},
        )
    matching = [
        snapshot
        for snapshot in registry.snapshots_for(model)
        if snapshot.benchmark.key == benchmark.key
    ]
    if not matching:
        raise HistoricalForecastError(
            "registry contains no snapshots for requested model and benchmark",
            context={
                "reason": "no_series_evidence",
                "model": model.key,
                "benchmark": benchmark.key,
            },
        )
    return HistoricalSeries(
        series_id=f"benchmark:{model.key}:{benchmark.key}",
        observations=tuple(
            ForecastObservation(
                timestamp=snapshot.measured_at,
                value=snapshot.normalized_score,
            )
            for snapshot in matching
        ),
    )


def summarize_forecast_tournament(report: ForecastTournamentReport) -> dict[str, object]:
    return {
        "champion": {
            "method": report.champion.method.value,
            "parameters": {
                "alpha": report.champion.parameters.alpha,
                "beta": report.champion.parameters.beta,
                "damping": report.champion.parameters.damping,
            },
            "objective": report.champion.objective,
            "mean_absolute_error": report.champion.aggregate_mae,
            "root_mean_squared_error": report.champion.aggregate_rmse,
            "symmetric_mape": report.champion.aggregate_smape,
            "percent_error": report.champion.percent_error,
            "origin_count": report.champion.origin_count,
        },
        "candidate_count": len(report.candidates),
        "series_fingerprint": report.series_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "candidates": [
            {
                "method": item.method.value,
                "alpha": item.parameters.alpha,
                "beta": item.parameters.beta,
                "damping": item.parameters.damping,
                "objective": item.objective,
                "mae": item.aggregate_mae,
                "rmse": item.aggregate_rmse,
                "smape": item.aggregate_smape,
                "percent_error": item.percent_error,
            }
            for item in report.candidates
        ],
    }


def _metrics(horizon: int, errors: list[float], actuals: list[float]) -> HorizonMetrics:
    if not errors or len(errors) != len(actuals):
        raise HistoricalForecastError(
            "forecast metric inputs are incomplete",
            context={"reason": "invalid_metric_inputs", "horizon": horizon},
        )
    absolute = [abs(value) for value in errors]
    mae = sum(absolute) / len(absolute)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    smape_terms: list[float] = []
    for error, actual in zip(errors, actuals, strict=True):
        predicted = actual - error
        denominator = abs(actual) + abs(predicted)
        if denominator <= _EPSILON:
            smape_terms.append(0.0)
        else:
            smape_terms.append(2.0 * abs(error) / denominator)
    return HorizonMetrics(
        horizon=horizon,
        sample_count=len(errors),
        mean_absolute_error=mae,
        root_mean_squared_error=rmse,
        symmetric_mape=sum(smape_terms) / len(smape_terms),
        median_absolute_error=median(absolute),
    )


def _complexity_rank(method: ForecastMethod) -> int:
    return {
        ForecastMethod.LAST_VALUE: 0,
        ForecastMethod.MEAN: 0,
        ForecastMethod.DRIFT: 1,
        ForecastMethod.HOLT: 2,
        ForecastMethod.DAMPED_HOLT: 3,
    }[method]


def _evaluation_payload(item: ForecastEvaluation) -> dict[str, object]:
    return {
        "method": item.method.value,
        "parameters": item.parameters.fingerprint,
        "objective": item.objective,
        "mae": item.aggregate_mae,
        "rmse": item.aggregate_rmse,
        "smape": item.aggregate_smape,
        "origins": item.origin_count,
        "fingerprint": item.evaluation_fingerprint,
    }


def _empirical_quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = probability * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _bounded_text(name: str, value: object, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalForecastError(
            f"{name} must be a non-empty string",
            context={"reason": "invalid_text", "field": name},
        )
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalForecastError(
            f"{name} exceeds {maximum} characters",
            context={"reason": "too_long", "field": name},
        )
    return cleaned


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalForecastError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalForecastError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return numeric


def _positive(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric <= 0.0:
        raise HistoricalForecastError(
            f"{name} must be positive",
            context={"reason": "invalid_positive", "field": name},
        )
    return numeric


def _non_negative(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric < 0.0:
        raise HistoricalForecastError(
            f"{name} must be non-negative",
            context={"reason": "invalid_non_negative", "field": name},
        )
    return numeric


def _unit_open(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if not 0.0 < numeric <= 1.0:
        raise HistoricalForecastError(
            f"{name} must be greater than 0 and at most 1",
            context={"reason": "out_of_range", "field": name},
        )
    return numeric


def _positive_int(name: str, value: object, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalForecastError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    if maximum is not None and value > maximum:
        raise HistoricalForecastError(
            f"{name} exceeds maximum",
            context={"reason": "too_large", "field": name, "maximum": maximum},
        )
    return value


def _grid(name: str, values: tuple[float, ...]) -> tuple[float, ...]:
    normalized = tuple(sorted(set(_unit_open(name, value) for value in values)))
    if not normalized:
        raise HistoricalForecastError(
            f"{name} must not be empty",
            context={"reason": "empty_grid", "field": name},
        )
    return normalized