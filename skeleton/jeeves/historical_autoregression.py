"""Ridge-stabilized autoregressive forecasting for Jeeves.

This module is intentionally layered on top of ``historical_forecasting`` rather
than replacing it. Simple baselines remain the first line of defense; AR(p)
models are challengers and must beat the baseline champion under the same
rolling-origin objective before they are preferred.

The implementation avoids external numerical dependencies. Least-squares is
solved from ridge-regularized normal equations with deterministic partial-pivot
Gaussian elimination. This is appropriate for the deliberately small lag
orders admitted here and keeps every coefficient and failure mode inspectable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Final

from skeleton.jeeves.historical_forecasting import (
    ForecastSelectionPolicy,
    ForecastTournamentReport,
    HistoricalForecastError,
    HistoricalForecastTournament,
    HistoricalSeries,
    HorizonMetrics,
)
from skeleton.jeeves.historical_models import canonical_fingerprint


_EPSILON: Final = 1e-12
MAX_AR_ORDER: Final = 64
MAX_AR_CANDIDATES: Final = 256
DEFAULT_AR_ORDERS: Final = (1, 2, 3, 5, 8)
DEFAULT_RIDGE_GRID: Final = (1e-8, 1e-6, 1e-4, 1e-2)


class HistoricalAutoregressionError(HistoricalForecastError):
    """Fail-closed autoregression contract violation."""

    code = "JVS.HISTORICAL_AUTOREGRESSION"
    http_status = 422


@dataclass(frozen=True, slots=True)
class AutoRegressiveParameters:
    order: int
    ridge: float = 1e-6
    include_intercept: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.order, bool) or not isinstance(self.order, int) or not 1 <= self.order <= MAX_AR_ORDER:
            raise HistoricalAutoregressionError(
                f"order must be an integer between 1 and {MAX_AR_ORDER}",
                context={"reason": "invalid_order", "order": self.order},
            )
        ridge = _non_negative("ridge", self.ridge)
        object.__setattr__(self, "ridge", ridge)
        if not isinstance(self.include_intercept, bool):
            raise HistoricalAutoregressionError(
                "include_intercept must be boolean",
                context={"reason": "invalid_intercept_flag"},
            )

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "order": self.order,
                "ridge": self.ridge,
                "include_intercept": self.include_intercept,
            }
        )


@dataclass(frozen=True, slots=True)
class AutoRegressiveFit:
    parameters: AutoRegressiveParameters
    intercept: float
    coefficients: tuple[float, ...]
    residuals: tuple[float, ...]
    last_values: tuple[float, ...]
    training_points: int
    training_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, AutoRegressiveParameters):
            raise HistoricalAutoregressionError(
                "parameters must be AutoRegressiveParameters",
                context={"reason": "invalid_parameters"},
            )
        intercept = _finite("intercept", self.intercept)
        coefficients = tuple(_finite("coefficient", value) for value in self.coefficients)
        residuals = tuple(_finite("residual", value) for value in self.residuals)
        last_values = tuple(_finite("last_value", value) for value in self.last_values)
        if len(coefficients) != self.parameters.order:
            raise HistoricalAutoregressionError(
                "coefficient count must equal autoregressive order",
                context={"reason": "coefficient_count_mismatch"},
            )
        if len(last_values) != self.parameters.order:
            raise HistoricalAutoregressionError(
                "last_values count must equal autoregressive order",
                context={"reason": "history_count_mismatch"},
            )
        if isinstance(self.training_points, bool) or not isinstance(self.training_points, int) or self.training_points <= self.parameters.order:
            raise HistoricalAutoregressionError(
                "training_points must exceed autoregressive order",
                context={"reason": "invalid_training_points"},
            )
        if not isinstance(self.training_fingerprint, str) or not self.training_fingerprint:
            raise HistoricalAutoregressionError(
                "training_fingerprint is required",
                context={"reason": "missing_training_fingerprint"},
            )
        object.__setattr__(self, "intercept", intercept)
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "residuals", residuals)
        object.__setattr__(self, "last_values", last_values)

    def forecast(self, horizon: int) -> tuple[float, ...]:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise HistoricalAutoregressionError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        history = list(self.last_values)
        result: list[float] = []
        for _ in range(horizon):
            value = self.intercept
            for lag, coefficient in enumerate(self.coefficients, start=1):
                value += coefficient * history[-lag]
            if not math.isfinite(value):
                raise HistoricalAutoregressionError(
                    "autoregressive forecast became non-finite",
                    context={"reason": "non_finite_forecast"},
                )
            result.append(value)
            history.append(value)
        return tuple(result)

    @property
    def coefficient_l1(self) -> float:
        return sum(abs(value) for value in self.coefficients)


@dataclass(frozen=True, slots=True)
class AutoRegressiveEvaluation:
    parameters: AutoRegressiveParameters
    horizons: tuple[HorizonMetrics, ...]
    aggregate_mae: float
    aggregate_rmse: float
    aggregate_smape: float
    complexity_penalty: float
    objective: float
    origin_count: int
    residuals: tuple[float, ...]
    coefficient_l1_median: float
    evaluation_fingerprint: str

    @property
    def percent_error(self) -> float:
        return round(self.aggregate_smape * 100.0, 2)


@dataclass(frozen=True, slots=True)
class AutoRegressiveSelectionPolicy:
    orders: tuple[int, ...] = DEFAULT_AR_ORDERS
    ridge_grid: tuple[float, ...] = DEFAULT_RIDGE_GRID
    include_intercept: bool = True
    max_coefficient_l1: float = 12.0
    explosion_multiplier: float = 100.0

    def __post_init__(self) -> None:
        orders = tuple(sorted(set(self.orders)))
        if not orders:
            raise HistoricalAutoregressionError(
                "orders must not be empty",
                context={"reason": "empty_orders"},
            )
        for order in orders:
            if isinstance(order, bool) or not isinstance(order, int) or not 1 <= order <= MAX_AR_ORDER:
                raise HistoricalAutoregressionError(
                    "orders contain invalid lag order",
                    context={"reason": "invalid_order", "order": order},
                )
        ridges = tuple(sorted(set(_non_negative("ridge", value) for value in self.ridge_grid)))
        if not ridges:
            raise HistoricalAutoregressionError(
                "ridge_grid must not be empty",
                context={"reason": "empty_ridge_grid"},
            )
        if len(orders) * len(ridges) > MAX_AR_CANDIDATES:
            raise HistoricalAutoregressionError(
                "autoregressive candidate grid is too large",
                context={"reason": "grid_too_large", "max_candidates": MAX_AR_CANDIDATES},
            )
        if not isinstance(self.include_intercept, bool):
            raise HistoricalAutoregressionError(
                "include_intercept must be boolean",
                context={"reason": "invalid_intercept_flag"},
            )
        object.__setattr__(self, "orders", orders)
        object.__setattr__(self, "ridge_grid", ridges)
        object.__setattr__(self, "max_coefficient_l1", _positive("max_coefficient_l1", self.max_coefficient_l1))
        object.__setattr__(self, "explosion_multiplier", _positive("explosion_multiplier", self.explosion_multiplier))

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "orders": list(self.orders),
                "ridge_grid": list(self.ridge_grid),
                "include_intercept": self.include_intercept,
                "max_coefficient_l1": self.max_coefficient_l1,
                "explosion_multiplier": self.explosion_multiplier,
            }
        )


@dataclass(frozen=True, slots=True)
class AdvancedForecastReport:
    family: str
    baseline_report: ForecastTournamentReport
    autoregressive_candidates: tuple[AutoRegressiveEvaluation, ...]
    autoregressive_champion: AutoRegressiveEvaluation | None
    objective: float
    report_fingerprint: str

    @property
    def method_label(self) -> str:
        if self.family == "baseline":
            return self.baseline_report.champion.method.value
        assert self.autoregressive_champion is not None
        return f"ar({self.autoregressive_champion.parameters.order})"


class AutoRegressiveForecaster:
    """Fit a small ridge-stabilized AR(p) model."""

    @staticmethod
    def fit(series: HistoricalSeries, parameters: AutoRegressiveParameters) -> AutoRegressiveFit:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalAutoregressionError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        if not isinstance(parameters, AutoRegressiveParameters):
            raise HistoricalAutoregressionError(
                "parameters must be AutoRegressiveParameters",
                context={"reason": "invalid_parameters"},
            )
        values = series.values
        order = parameters.order
        minimum_points = order + 2
        if len(values) < minimum_points:
            raise HistoricalAutoregressionError(
                "series is too short for autoregressive fit",
                context={
                    "reason": "insufficient_points",
                    "points": len(values),
                    "minimum_points": minimum_points,
                    "order": order,
                },
            )

        feature_count = order + (1 if parameters.include_intercept else 0)
        gram = [[0.0 for _ in range(feature_count)] for _ in range(feature_count)]
        target = [0.0 for _ in range(feature_count)]

        rows: list[tuple[list[float], float]] = []
        for index in range(order, len(values)):
            features: list[float] = []
            if parameters.include_intercept:
                features.append(1.0)
            for lag in range(1, order + 1):
                features.append(values[index - lag])
            observed = values[index]
            rows.append((features, observed))
            for left in range(feature_count):
                target[left] += features[left] * observed
                for right in range(feature_count):
                    gram[left][right] += features[left] * features[right]

        ridge_start = 1 if parameters.include_intercept else 0
        for diagonal in range(ridge_start, feature_count):
            gram[diagonal][diagonal] += parameters.ridge

        solution = _solve_linear_system(gram, target)
        if parameters.include_intercept:
            intercept = solution[0]
            coefficients = tuple(solution[1:])
        else:
            intercept = 0.0
            coefficients = tuple(solution)

        residuals: list[float] = []
        for features, observed in rows:
            predicted = sum(weight * value for weight, value in zip(solution, features, strict=True))
            residuals.append(observed - predicted)

        return AutoRegressiveFit(
            parameters=parameters,
            intercept=intercept,
            coefficients=coefficients,
            residuals=tuple(residuals),
            last_values=tuple(values[-order:]),
            training_points=len(values),
            training_fingerprint=series.fingerprint,
        )


class AdvancedHistoricalForecastTournament:
    """Challenge the transparent baseline champion with AR(p) candidates."""

    def __init__(
        self,
        *,
        forecast_policy: ForecastSelectionPolicy | None = None,
        autoregression_policy: AutoRegressiveSelectionPolicy | None = None,
    ) -> None:
        self.forecast_policy = forecast_policy or ForecastSelectionPolicy()
        self.autoregression_policy = autoregression_policy or AutoRegressiveSelectionPolicy()
        if not isinstance(self.forecast_policy, ForecastSelectionPolicy):
            raise HistoricalAutoregressionError(
                "forecast_policy must be ForecastSelectionPolicy",
                context={"reason": "invalid_forecast_policy"},
            )
        if not isinstance(self.autoregression_policy, AutoRegressiveSelectionPolicy):
            raise HistoricalAutoregressionError(
                "autoregression_policy must be AutoRegressiveSelectionPolicy",
                context={"reason": "invalid_autoregression_policy"},
            )

    def run(self, series: HistoricalSeries) -> AdvancedForecastReport:
        baseline_report = HistoricalForecastTournament(self.forecast_policy).run(series)
        candidates: list[AutoRegressiveEvaluation] = []
        for order in self.autoregression_policy.orders:
            if self.forecast_policy.minimum_training_points < order + 2:
                continue
            for ridge in self.autoregression_policy.ridge_grid:
                parameters = AutoRegressiveParameters(
                    order=order,
                    ridge=ridge,
                    include_intercept=self.autoregression_policy.include_intercept,
                )
                evaluation = self.evaluate(series, parameters)
                if evaluation.coefficient_l1_median > self.autoregression_policy.max_coefficient_l1:
                    continue
                if self._explodes(series, parameters):
                    continue
                candidates.append(evaluation)

        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.objective,
                    item.aggregate_rmse,
                    item.aggregate_mae,
                    item.parameters.order,
                    item.parameters.ridge,
                    not item.parameters.include_intercept,
                ),
            )
        )
        ar_champion = ordered[0] if ordered else None
        if ar_champion is not None and ar_champion.objective + _EPSILON < baseline_report.champion.objective:
            family = "autoregression"
            objective = ar_champion.objective
        else:
            family = "baseline"
            objective = baseline_report.champion.objective

        payload = {
            "series": series.fingerprint,
            "forecast_policy": self.forecast_policy.fingerprint,
            "autoregression_policy": self.autoregression_policy.fingerprint,
            "baseline": baseline_report.report_fingerprint,
            "ar_candidates": [item.evaluation_fingerprint for item in ordered],
            "family": family,
            "objective": objective,
        }
        return AdvancedForecastReport(
            family=family,
            baseline_report=baseline_report,
            autoregressive_candidates=ordered,
            autoregressive_champion=ar_champion,
            objective=objective,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def evaluate(
        self,
        series: HistoricalSeries,
        parameters: AutoRegressiveParameters,
    ) -> AutoRegressiveEvaluation:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalAutoregressionError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        max_horizon = max(self.forecast_policy.horizons)
        final_origin = len(series.observations) - max_horizon
        errors_by_horizon: dict[int, list[float]] = {
            horizon: [] for horizon in self.forecast_policy.horizons
        }
        actuals_by_horizon: dict[int, list[float]] = {
            horizon: [] for horizon in self.forecast_policy.horizons
        }
        residuals: list[float] = []
        coefficient_l1_values: list[float] = []
        origin_count = 0

        for origin in range(self.forecast_policy.minimum_training_points, final_origin + 1):
            training = HistoricalSeries(
                series_id=f"{series.series_id}:ar-origin:{origin}",
                observations=series.observations[:origin],
            )
            fitted = AutoRegressiveForecaster.fit(training, parameters)
            predictions = fitted.forecast(max_horizon)
            coefficient_l1_values.append(fitted.coefficient_l1)
            origin_count += 1
            for horizon in self.forecast_policy.horizons:
                actual = series.observations[origin + horizon - 1].value
                predicted = predictions[horizon - 1]
                error = actual - predicted
                errors_by_horizon[horizon].append(error)
                actuals_by_horizon[horizon].append(actual)
                residuals.append(error)

        if origin_count < self.forecast_policy.minimum_origins:
            raise HistoricalAutoregressionError(
                "not enough rolling origins for autoregression evaluation",
                context={
                    "reason": "insufficient_origins",
                    "origin_count": origin_count,
                    "minimum_origins": self.forecast_policy.minimum_origins,
                },
            )

        metrics = tuple(
            _metrics(horizon, errors_by_horizon[horizon], actuals_by_horizon[horizon])
            for horizon in self.forecast_policy.horizons
        )
        weights = self.forecast_policy.normalized_horizon_weights
        aggregate_mae = sum(
            weight * item.mean_absolute_error
            for weight, item in zip(weights, metrics, strict=True)
        )
        aggregate_rmse = sum(
            weight * item.root_mean_squared_error
            for weight, item in zip(weights, metrics, strict=True)
        )
        aggregate_smape = sum(
            weight * item.symmetric_mape
            for weight, item in zip(weights, metrics, strict=True)
        )

        # AR candidates must use the exact same leakage-free normalization scale
        # as baseline candidates or their objectives are not comparable. The
        # scale is frozen from the initial training window available before the
        # first rolling-origin forecast.
        calibration_values = series.values[: self.forecast_policy.minimum_training_points]
        scale = median(abs(value) for value in calibration_values)
        if scale <= _EPSILON:
            scale = max(1.0, max(abs(value) for value in calibration_values))
        normalized_mae = aggregate_mae / scale
        normalized_rmse = aggregate_rmse / scale
        complexity = self.forecast_policy.complexity_weight * (2.0 + parameters.order / 2.0)
        objective = (
            self.forecast_policy.mae_weight * normalized_mae
            + self.forecast_policy.rmse_weight * normalized_rmse
            + self.forecast_policy.smape_weight * aggregate_smape
            + complexity
        )
        l1_median = median(coefficient_l1_values)
        payload = {
            "series": series.fingerprint,
            "parameters": parameters.fingerprint,
            "forecast_policy": self.forecast_policy.fingerprint,
            "autoregression_policy": self.autoregression_policy.fingerprint,
            "normalization_scale": scale,
            "objective": objective,
            "mae": aggregate_mae,
            "rmse": aggregate_rmse,
            "smape": aggregate_smape,
            "origin_count": origin_count,
            "coefficient_l1_median": l1_median,
        }
        return AutoRegressiveEvaluation(
            parameters=parameters,
            horizons=metrics,
            aggregate_mae=aggregate_mae,
            aggregate_rmse=aggregate_rmse,
            aggregate_smape=aggregate_smape,
            complexity_penalty=complexity,
            objective=objective,
            origin_count=origin_count,
            residuals=tuple(residuals),
            coefficient_l1_median=l1_median,
            evaluation_fingerprint=canonical_fingerprint(payload),
        )

    def fit_champion(self, series: HistoricalSeries) -> tuple[object, AdvancedForecastReport]:
        report = self.run(series)
        if report.family == "baseline":
            fitted, _ = HistoricalForecastTournament(self.forecast_policy).fit_champion(series)
            return fitted, report
        assert report.autoregressive_champion is not None
        fitted = AutoRegressiveForecaster.fit(series, report.autoregressive_champion.parameters)
        return fitted, report

    def _explodes(self, series: HistoricalSeries, parameters: AutoRegressiveParameters) -> bool:
        fitted = AutoRegressiveForecaster.fit(series, parameters)
        horizon = max(self.forecast_policy.horizons)
        forecast = fitted.forecast(horizon)
        scale = max(1.0, max(abs(value) for value in series.values))
        bound = scale * self.autoregression_policy.explosion_multiplier
        return any(abs(value) > bound for value in forecast)


def summarize_advanced_forecast(report: AdvancedForecastReport) -> dict[str, object]:
    ar = report.autoregressive_champion
    return {
        "family": report.family,
        "method": report.method_label,
        "objective": report.objective,
        "report_fingerprint": report.report_fingerprint,
        "baseline": {
            "method": report.baseline_report.champion.method.value,
            "objective": report.baseline_report.champion.objective,
            "report_fingerprint": report.baseline_report.report_fingerprint,
        },
        "autoregression": None
        if ar is None
        else {
            "order": ar.parameters.order,
            "ridge": ar.parameters.ridge,
            "include_intercept": ar.parameters.include_intercept,
            "objective": ar.objective,
            "mae": ar.aggregate_mae,
            "rmse": ar.aggregate_rmse,
            "smape": ar.aggregate_smape,
            "percent_error": ar.percent_error,
            "coefficient_l1_median": ar.coefficient_l1_median,
        },
        "autoregressive_candidate_count": len(report.autoregressive_candidates),
    }


def _metrics(horizon: int, errors: list[float], actuals: list[float]) -> HorizonMetrics:
    if not errors or len(errors) != len(actuals):
        raise HistoricalAutoregressionError(
            "metric inputs are incomplete",
            context={"reason": "invalid_metric_inputs", "horizon": horizon},
        )
    absolute = [abs(value) for value in errors]
    mae = sum(absolute) / len(absolute)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    smape_terms: list[float] = []
    for error, actual in zip(errors, actuals, strict=True):
        predicted = actual - error
        denominator = abs(actual) + abs(predicted)
        smape_terms.append(0.0 if denominator <= _EPSILON else 2.0 * abs(error) / denominator)
    return HorizonMetrics(
        horizon=horizon,
        sample_count=len(errors),
        mean_absolute_error=mae,
        root_mean_squared_error=rmse,
        symmetric_mape=sum(smape_terms) / len(smape_terms),
        median_absolute_error=median(absolute),
    )


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> tuple[float, ...]:
    """Solve Ax=b with deterministic partial-pivot Gaussian elimination."""
    size = len(vector)
    if size == 0 or len(matrix) != size or any(len(row) != size for row in matrix):
        raise HistoricalAutoregressionError(
            "linear system must be non-empty and square",
            context={"reason": "invalid_linear_system"},
        )
    augmented = [
        [_finite("matrix", value) for value in row] + [_finite("vector", vector[index])]
        for index, row in enumerate(matrix)
    ]

    for column in range(size):
        pivot = max(range(column, size), key=lambda row: (abs(augmented[row][column]), -row))
        pivot_value = augmented[pivot][column]
        if abs(pivot_value) <= _EPSILON:
            raise HistoricalAutoregressionError(
                "autoregressive normal equations are singular; increase ridge",
                context={"reason": "singular_system", "column": column},
            )
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        divisor = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= divisor

        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if abs(factor) <= _EPSILON:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]

    solution = tuple(augmented[row][size] for row in range(size))
    if any(not math.isfinite(value) for value in solution):
        raise HistoricalAutoregressionError(
            "linear solver produced non-finite coefficients",
            context={"reason": "non_finite_solution"},
        )
    return solution


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalAutoregressionError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalAutoregressionError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return numeric


def _non_negative(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric < 0.0:
        raise HistoricalAutoregressionError(
            f"{name} must be non-negative",
            context={"reason": "invalid_non_negative", "field": name},
        )
    return numeric


def _positive(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric <= 0.0:
        raise HistoricalAutoregressionError(
            f"{name} must be positive",
            context={"reason": "invalid_positive", "field": name},
        )
    return numeric