"""Evidence-gated convex forecast stacking for Jeeves.

Ensembling can improve forecasts, but only when the combination is validated on
exactly the same rolling-origin evidence as its constituent models. This module
builds a transparent two-model stack from the advanced forecast tournament:

* the strongest simple baseline (last/mean/drift/Holt/damped Holt), and
* the strongest eligible ridge autoregression challenger.

A bounded deterministic weight grid is evaluated out-of-sample. The ensemble is
selected only when it clears an explicit improvement margin over the better
constituent after an ensemble complexity penalty. Otherwise the stronger single
model remains authoritative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Final

from skeleton.jeeves.historical_autoregression import (
    AdvancedForecastReport,
    AdvancedHistoricalForecastTournament,
    AutoRegressiveFit,
    AutoRegressiveForecaster,
    AutoRegressiveSelectionPolicy,
)
from skeleton.jeeves.historical_forecasting import (
    FittedForecast,
    ForecastSelectionPolicy,
    HistoricalForecaster,
    HistoricalForecastError,
    HistoricalSeries,
    HorizonMetrics,
)
from skeleton.jeeves.historical_models import canonical_fingerprint


_EPSILON: Final = 1e-12
DEFAULT_WEIGHT_GRID: Final = tuple(index / 20.0 for index in range(21))
MAX_WEIGHT_GRID: Final = 201


class HistoricalEnsembleError(HistoricalForecastError):
    """Fail-closed forecast-ensemble contract violation."""

    code = "JVS.HISTORICAL_ENSEMBLE"
    http_status = 422


@dataclass(frozen=True, slots=True)
class ForecastEnsemblePolicy:
    baseline_weight_grid: tuple[float, ...] = DEFAULT_WEIGHT_GRID
    minimum_objective_improvement: float = 0.001
    ensemble_complexity_penalty: float = 0.001
    require_interior_weight: bool = True

    def __post_init__(self) -> None:
        grid = tuple(sorted(set(_unit("baseline_weight", value) for value in self.baseline_weight_grid)))
        if not grid:
            raise HistoricalEnsembleError(
                "baseline_weight_grid must not be empty",
                context={"reason": "empty_weight_grid"},
            )
        if len(grid) > MAX_WEIGHT_GRID:
            raise HistoricalEnsembleError(
                "baseline_weight_grid is too large",
                context={"reason": "weight_grid_too_large", "maximum": MAX_WEIGHT_GRID},
            )
        improvement = _non_negative("minimum_objective_improvement", self.minimum_objective_improvement)
        complexity = _non_negative("ensemble_complexity_penalty", self.ensemble_complexity_penalty)
        if not isinstance(self.require_interior_weight, bool):
            raise HistoricalEnsembleError(
                "require_interior_weight must be boolean",
                context={"reason": "invalid_interior_flag"},
            )
        object.__setattr__(self, "baseline_weight_grid", grid)
        object.__setattr__(self, "minimum_objective_improvement", improvement)
        object.__setattr__(self, "ensemble_complexity_penalty", complexity)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "baseline_weight_grid": list(self.baseline_weight_grid),
                "minimum_objective_improvement": self.minimum_objective_improvement,
                "ensemble_complexity_penalty": self.ensemble_complexity_penalty,
                "require_interior_weight": self.require_interior_weight,
            }
        )


@dataclass(frozen=True, slots=True)
class EnsembleEvaluation:
    baseline_weight: float
    autoregression_weight: float
    horizons: tuple[HorizonMetrics, ...]
    aggregate_mae: float
    aggregate_rmse: float
    aggregate_smape: float
    objective: float
    constituent_disagreement: float
    origin_count: int
    evaluation_fingerprint: str

    @property
    def percent_error(self) -> float:
        return round(self.aggregate_smape * 100.0, 2)


@dataclass(frozen=True, slots=True)
class ForecastEnsembleReport:
    advanced_report: AdvancedForecastReport
    candidates: tuple[EnsembleEvaluation, ...]
    ensemble_champion: EnsembleEvaluation | None
    selected_family: str
    selected_objective: float
    best_constituent_objective: float
    improvement: float
    policy_fingerprint: str
    report_fingerprint: str

    @property
    def ensemble_selected(self) -> bool:
        return self.selected_family == "ensemble"


@dataclass(frozen=True, slots=True)
class FittedForecastEnsemble:
    baseline_fit: FittedForecast
    autoregression_fit: AutoRegressiveFit
    baseline_weight: float
    autoregression_weight: float
    source_report_fingerprint: str

    def forecast(self, horizon: int) -> tuple[float, ...]:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise HistoricalEnsembleError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        baseline = self.baseline_fit.forecast(horizon)
        autoregression = self.autoregression_fit.forecast(horizon)
        return tuple(
            self.baseline_weight * base.predicted + self.autoregression_weight * ar
            for base, ar in zip(baseline, autoregression, strict=True)
        )


class HistoricalForecastEnsembler:
    """Fit and validate a convex baseline/AR stack."""

    def __init__(
        self,
        *,
        forecast_policy: ForecastSelectionPolicy | None = None,
        autoregression_policy: AutoRegressiveSelectionPolicy | None = None,
        ensemble_policy: ForecastEnsemblePolicy | None = None,
    ) -> None:
        self.forecast_policy = forecast_policy or ForecastSelectionPolicy()
        self.autoregression_policy = autoregression_policy or AutoRegressiveSelectionPolicy()
        self.ensemble_policy = ensemble_policy or ForecastEnsemblePolicy()
        if not isinstance(self.forecast_policy, ForecastSelectionPolicy):
            raise HistoricalEnsembleError(
                "forecast_policy must be ForecastSelectionPolicy",
                context={"reason": "invalid_forecast_policy"},
            )
        if not isinstance(self.autoregression_policy, AutoRegressiveSelectionPolicy):
            raise HistoricalEnsembleError(
                "autoregression_policy must be AutoRegressiveSelectionPolicy",
                context={"reason": "invalid_autoregression_policy"},
            )
        if not isinstance(self.ensemble_policy, ForecastEnsemblePolicy):
            raise HistoricalEnsembleError(
                "ensemble_policy must be ForecastEnsemblePolicy",
                context={"reason": "invalid_ensemble_policy"},
            )
        self.advanced = AdvancedHistoricalForecastTournament(
            forecast_policy=self.forecast_policy,
            autoregression_policy=self.autoregression_policy,
        )

    def run(self, series: HistoricalSeries) -> ForecastEnsembleReport:
        if not isinstance(series, HistoricalSeries):
            raise HistoricalEnsembleError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        advanced_report = self.advanced.run(series)
        ar_champion = advanced_report.autoregressive_champion
        if ar_champion is None:
            return self._no_ensemble_report(advanced_report)

        predictions, actuals, disagreements, origin_count = self._rolling_predictions(
            series,
            advanced_report,
        )
        candidates = tuple(
            self._evaluate_weight(
                series=series,
                advanced_report=advanced_report,
                baseline_weight=weight,
                predictions=predictions,
                actuals=actuals,
                disagreements=disagreements,
                origin_count=origin_count,
            )
            for weight in self.ensemble_policy.baseline_weight_grid
        )
        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.objective,
                    item.aggregate_rmse,
                    item.aggregate_mae,
                    abs(item.baseline_weight - 0.5),
                    item.baseline_weight,
                ),
            )
        )
        champion = ordered[0] if ordered else None
        best_constituent = min(
            advanced_report.baseline_report.champion.objective,
            ar_champion.objective,
        )
        improvement = 0.0 if champion is None else best_constituent - champion.objective
        interior = champion is not None and _EPSILON < champion.baseline_weight < 1.0 - _EPSILON
        selected = (
            champion is not None
            and improvement + _EPSILON >= self.ensemble_policy.minimum_objective_improvement
            and (interior or not self.ensemble_policy.require_interior_weight)
        )
        selected_family = "ensemble" if selected else advanced_report.family
        selected_objective = champion.objective if selected and champion is not None else advanced_report.objective
        payload = {
            "advanced": advanced_report.report_fingerprint,
            "policy": self.ensemble_policy.fingerprint,
            "candidates": [item.evaluation_fingerprint for item in ordered],
            "champion": champion.evaluation_fingerprint if champion is not None else None,
            "best_constituent": best_constituent,
            "improvement": improvement,
            "selected_family": selected_family,
            "selected_objective": selected_objective,
        }
        return ForecastEnsembleReport(
            advanced_report=advanced_report,
            candidates=ordered,
            ensemble_champion=champion,
            selected_family=selected_family,
            selected_objective=selected_objective,
            best_constituent_objective=best_constituent,
            improvement=improvement,
            policy_fingerprint=self.ensemble_policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def fit_selected(self, series: HistoricalSeries) -> tuple[object, ForecastEnsembleReport]:
        report = self.run(series)
        if not report.ensemble_selected:
            fitted, _ = self.advanced.fit_champion(series)
            return fitted, report
        champion = report.ensemble_champion
        ar_champion = report.advanced_report.autoregressive_champion
        if champion is None or ar_champion is None:
            raise HistoricalEnsembleError(
                "selected ensemble is missing constituent evidence",
                context={"reason": "missing_constituent"},
            )
        baseline_eval = report.advanced_report.baseline_report.champion
        baseline_fit = HistoricalForecaster.fit(
            series,
            baseline_eval.method,
            baseline_eval.parameters,
        )
        ar_fit = AutoRegressiveForecaster.fit(series, ar_champion.parameters)
        return (
            FittedForecastEnsemble(
                baseline_fit=baseline_fit,
                autoregression_fit=ar_fit,
                baseline_weight=champion.baseline_weight,
                autoregression_weight=champion.autoregression_weight,
                source_report_fingerprint=report.report_fingerprint,
            ),
            report,
        )

    def _rolling_predictions(
        self,
        series: HistoricalSeries,
        report: AdvancedForecastReport,
    ) -> tuple[
        dict[int, list[tuple[float, float]]],
        dict[int, list[float]],
        list[float],
        int,
    ]:
        ar_champion = report.autoregressive_champion
        if ar_champion is None:
            raise HistoricalEnsembleError(
                "autoregressive champion is required for stacking",
                context={"reason": "missing_ar_champion"},
            )
        baseline_champion = report.baseline_report.champion
        max_horizon = max(self.forecast_policy.horizons)
        final_origin = len(series.observations) - max_horizon
        predictions: dict[int, list[tuple[float, float]]] = {
            horizon: [] for horizon in self.forecast_policy.horizons
        }
        actuals: dict[int, list[float]] = {
            horizon: [] for horizon in self.forecast_policy.horizons
        }
        disagreements: list[float] = []
        origin_count = 0

        for origin in range(self.forecast_policy.minimum_training_points, final_origin + 1):
            training = HistoricalSeries(
                series_id=f"{series.series_id}:ensemble-origin:{origin}",
                observations=series.observations[:origin],
            )
            baseline_fit = HistoricalForecaster.fit(
                training,
                baseline_champion.method,
                baseline_champion.parameters,
            )
            ar_fit = AutoRegressiveForecaster.fit(training, ar_champion.parameters)
            baseline_forecast = baseline_fit.forecast(max_horizon)
            ar_forecast = ar_fit.forecast(max_horizon)
            origin_count += 1
            for horizon in self.forecast_policy.horizons:
                base = baseline_forecast[horizon - 1].predicted
                ar = ar_forecast[horizon - 1]
                actual = series.observations[origin + horizon - 1].value
                predictions[horizon].append((base, ar))
                actuals[horizon].append(actual)
                disagreements.append(abs(base - ar))
        if origin_count < self.forecast_policy.minimum_origins:
            raise HistoricalEnsembleError(
                "not enough common rolling origins for ensemble",
                context={
                    "reason": "insufficient_origins",
                    "origin_count": origin_count,
                    "minimum_origins": self.forecast_policy.minimum_origins,
                },
            )
        return predictions, actuals, disagreements, origin_count

    def _evaluate_weight(
        self,
        *,
        series: HistoricalSeries,
        advanced_report: AdvancedForecastReport,
        baseline_weight: float,
        predictions: dict[int, list[tuple[float, float]]],
        actuals: dict[int, list[float]],
        disagreements: list[float],
        origin_count: int,
    ) -> EnsembleEvaluation:
        baseline_weight = _unit("baseline_weight", baseline_weight)
        ar_weight = 1.0 - baseline_weight
        metrics: list[HorizonMetrics] = []
        for horizon in self.forecast_policy.horizons:
            errors: list[float] = []
            for (baseline, autoregression), actual in zip(
                predictions[horizon],
                actuals[horizon],
                strict=True,
            ):
                combined = baseline_weight * baseline + ar_weight * autoregression
                errors.append(actual - combined)
            metrics.append(_metrics(horizon, errors, actuals[horizon]))
        metric_tuple = tuple(metrics)
        weights = self.forecast_policy.normalized_horizon_weights
        aggregate_mae = sum(
            weight * item.mean_absolute_error
            for weight, item in zip(weights, metric_tuple, strict=True)
        )
        aggregate_rmse = sum(
            weight * item.root_mean_squared_error
            for weight, item in zip(weights, metric_tuple, strict=True)
        )
        aggregate_smape = sum(
            weight * item.symmetric_mape
            for weight, item in zip(weights, metric_tuple, strict=True)
        )

        # Ensemble weights compete directly with baseline and AR candidates, so
        # all three families must use the same causal normalization scale. Freeze
        # it from the initial training window available before the first rolling
        # forecast origin; later evaluation magnitudes cannot change the metric
        # mixture or the selected family.
        calibration_values = series.values[: self.forecast_policy.minimum_training_points]
        scale = median(abs(value) for value in calibration_values)
        if scale <= _EPSILON:
            scale = max(1.0, max(abs(value) for value in calibration_values))
        objective = (
            self.forecast_policy.mae_weight * (aggregate_mae / scale)
            + self.forecast_policy.rmse_weight * (aggregate_rmse / scale)
            + self.forecast_policy.smape_weight * aggregate_smape
            + self.ensemble_policy.ensemble_complexity_penalty
        )
        disagreement = sum(disagreements) / len(disagreements) if disagreements else 0.0
        payload = {
            "series": series.fingerprint,
            "advanced": advanced_report.report_fingerprint,
            "policy": self.ensemble_policy.fingerprint,
            "baseline_weight": baseline_weight,
            "ar_weight": ar_weight,
            "normalization_scale": scale,
            "objective": objective,
            "mae": aggregate_mae,
            "rmse": aggregate_rmse,
            "smape": aggregate_smape,
            "origin_count": origin_count,
            "disagreement": disagreement,
        }
        return EnsembleEvaluation(
            baseline_weight=baseline_weight,
            autoregression_weight=ar_weight,
            horizons=metric_tuple,
            aggregate_mae=aggregate_mae,
            aggregate_rmse=aggregate_rmse,
            aggregate_smape=aggregate_smape,
            objective=objective,
            constituent_disagreement=disagreement,
            origin_count=origin_count,
            evaluation_fingerprint=canonical_fingerprint(payload),
        )

    def _no_ensemble_report(self, advanced_report: AdvancedForecastReport) -> ForecastEnsembleReport:
        payload = {
            "advanced": advanced_report.report_fingerprint,
            "policy": self.ensemble_policy.fingerprint,
            "reason": "no_autoregressive_champion",
            "selected_family": advanced_report.family,
            "selected_objective": advanced_report.objective,
        }
        return ForecastEnsembleReport(
            advanced_report=advanced_report,
            candidates=(),
            ensemble_champion=None,
            selected_family=advanced_report.family,
            selected_objective=advanced_report.objective,
            best_constituent_objective=advanced_report.objective,
            improvement=0.0,
            policy_fingerprint=self.ensemble_policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )


def summarize_forecast_ensemble(report: ForecastEnsembleReport) -> dict[str, object]:
    champion = report.ensemble_champion
    return {
        "selected_family": report.selected_family,
        "ensemble_selected": report.ensemble_selected,
        "selected_objective": report.selected_objective,
        "best_constituent_objective": report.best_constituent_objective,
        "improvement": report.improvement,
        "candidate_count": len(report.candidates),
        "ensemble_champion": None
        if champion is None
        else {
            "baseline_weight": champion.baseline_weight,
            "autoregression_weight": champion.autoregression_weight,
            "objective": champion.objective,
            "mae": champion.aggregate_mae,
            "rmse": champion.aggregate_rmse,
            "smape": champion.aggregate_smape,
            "percent_error": champion.percent_error,
            "constituent_disagreement": champion.constituent_disagreement,
        },
        "advanced_report_fingerprint": report.advanced_report.report_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }


def _metrics(horizon: int, errors: list[float], actuals: list[float]) -> HorizonMetrics:
    if not errors or len(errors) != len(actuals):
        raise HistoricalEnsembleError(
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


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalEnsembleError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalEnsembleError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return numeric


def _unit(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if not 0.0 <= numeric <= 1.0:
        raise HistoricalEnsembleError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return numeric


def _non_negative(name: str, value: object) -> float:
    numeric = _finite(name, value)
    if numeric < 0.0:
        raise HistoricalEnsembleError(
            f"{name} must be non-negative",
            context={"reason": "invalid_non_negative", "field": name},
        )
    return numeric