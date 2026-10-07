"""Seasonal-aware promotion layer for the Jeeves predictive engine.

Seasonality is treated as a challenger to the already evidence-selected
non-seasonal route. A seasonal model does not get promoted merely because its own
tournament likes it: both routes are replayed on the seasonal tournament's exact
common rolling-origin window, then compared with the same normalized MAE/RMSE/
sMAPE objective. Promotion also checks per-horizon MAE regressions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

from skeleton.jeeves.historical_autoregression import AutoRegressiveForecaster
from skeleton.jeeves.historical_conformal import HistoricalConformalCalibrator, HistoricalConformalError
from skeleton.jeeves.historical_forecasting import HistoricalForecaster, HistoricalSeries
from skeleton.jeeves.historical_models import canonical_fingerprint
from skeleton.jeeves.historical_seasonal import (
    HistoricalSeasonalError,
    HistoricalSeasonalForecaster,
    HistoricalSeasonalTournament,
    SeasonalSelectionPolicy,
    SeasonalTournamentReport,
)
from skeleton.jeeves.predictive_engine import (
    JeevesPredictiveEngine,
    PredictiveEngineError,
    PredictiveEnginePolicy,
    PredictivePoint,
    PredictiveResult,
)


_EPSILON = 1e-12


class SeasonalPredictiveError(PredictiveEngineError):
    """Fail-closed seasonal promotion contract violation."""

    code = "JVS.PREDICTIVE_SEASONAL"
    http_status = 422


@dataclass(frozen=True, slots=True)
class SeasonalPromotionPolicy:
    minimum_relative_improvement: float = 0.03
    max_horizon_normalized_mae_regression: float = 0.02
    require_seasonal_evaluation: bool = False

    def __post_init__(self) -> None:
        improvement = _unit("minimum_relative_improvement", self.minimum_relative_improvement)
        regression = _unit(
            "max_horizon_normalized_mae_regression",
            self.max_horizon_normalized_mae_regression,
        )
        if not isinstance(self.require_seasonal_evaluation, bool):
            raise SeasonalPredictiveError(
                "require_seasonal_evaluation must be boolean",
                context={"reason": "invalid_requirement_flag"},
            )
        object.__setattr__(self, "minimum_relative_improvement", improvement)
        object.__setattr__(self, "max_horizon_normalized_mae_regression", regression)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "minimum_relative_improvement": self.minimum_relative_improvement,
                "max_horizon_normalized_mae_regression": self.max_horizon_normalized_mae_regression,
                "require_seasonal_evaluation": self.require_seasonal_evaluation,
            }
        )


@dataclass(frozen=True, slots=True)
class FamilyHorizonScore:
    horizon: int
    sample_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    symmetric_mape: float


@dataclass(frozen=True, slots=True)
class CommonFamilyScore:
    family: str
    label: str
    horizons: tuple[FamilyHorizonScore, ...]
    aggregate_mae: float
    aggregate_rmse: float
    aggregate_smape: float
    objective: float
    origin_count: int
    common_origin_start: int
    evaluation_fingerprint: str


@dataclass(frozen=True, slots=True)
class SeasonalChallengeReport:
    final_result: PredictiveResult
    nonseasonal_result: PredictiveResult
    nonseasonal_score: CommonFamilyScore | None
    seasonal_score: CommonFamilyScore | None
    seasonal_tournament: SeasonalTournamentReport | None
    seasonal_selected: bool
    relative_improvement: float
    horizon_regressions: tuple[int, ...]
    reasons: tuple[str, ...]
    policy_fingerprint: str
    report_fingerprint: str


class SeasonalAwarePredictiveEngine:
    """Challenge the existing predictive route with validated seasonal models."""

    def __init__(
        self,
        *,
        engine_policy: PredictiveEnginePolicy | None = None,
        seasonal_policy: SeasonalSelectionPolicy | None = None,
        promotion_policy: SeasonalPromotionPolicy | None = None,
    ) -> None:
        self.engine_policy = engine_policy or PredictiveEnginePolicy()
        self.seasonal_policy = seasonal_policy or SeasonalSelectionPolicy()
        self.promotion_policy = promotion_policy or SeasonalPromotionPolicy()
        if not isinstance(self.engine_policy, PredictiveEnginePolicy):
            raise SeasonalPredictiveError("engine_policy must be PredictiveEnginePolicy", context={"reason": "invalid_engine_policy"})
        if not isinstance(self.seasonal_policy, SeasonalSelectionPolicy):
            raise SeasonalPredictiveError("seasonal_policy must be SeasonalSelectionPolicy", context={"reason": "invalid_seasonal_policy"})
        if not isinstance(self.promotion_policy, SeasonalPromotionPolicy):
            raise SeasonalPredictiveError("promotion_policy must be SeasonalPromotionPolicy", context={"reason": "invalid_promotion_policy"})
        self.base_engine = JeevesPredictiveEngine(self.engine_policy)
        self.seasonal_tournament = HistoricalSeasonalTournament(
            forecast_policy=self.engine_policy.forecast,
            seasonal_policy=self.seasonal_policy,
        )
        self.calibrator = HistoricalConformalCalibrator(self.engine_policy.conformal)

    @property
    def policy_fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "engine": self.engine_policy.fingerprint,
                "seasonal": self.seasonal_policy.fingerprint,
                "promotion": self.promotion_policy.fingerprint,
            }
        )

    def evaluate(self, series: HistoricalSeries, *, horizon: int) -> SeasonalChallengeReport:
        if not isinstance(series, HistoricalSeries):
            raise SeasonalPredictiveError("series must be HistoricalSeries", context={"reason": "invalid_series"})
        base = self.base_engine.evaluate(series, horizon=horizon)
        try:
            seasonal_report = self.seasonal_tournament.run(series)
        except HistoricalSeasonalError as exc:
            if self.promotion_policy.require_seasonal_evaluation:
                raise SeasonalPredictiveError(
                    "seasonal evaluation is required but unavailable",
                    context={"reason": "seasonal_required", "detail": exc.context},
                    cause=exc,
                ) from exc
            return self._fallback_report(base, reason=str(exc.context.get("reason", "seasonal_unavailable")))

        common_start = seasonal_report.common_origin_start
        nonseasonal = self._evaluate_nonseasonal_common(series, base, common_start)
        seasonal = self._seasonal_common_score(series, seasonal_report)
        improvement = (nonseasonal.objective - seasonal.objective) / max(nonseasonal.objective, _EPSILON)
        scale = _causal_scale(series.values[:common_start])
        nonseasonal_by_horizon = {item.horizon: item for item in nonseasonal.horizons}
        regressions: list[int] = []
        for item in seasonal.horizons:
            incumbent = nonseasonal_by_horizon[item.horizon]
            normalized_regression = (item.mean_absolute_error - incumbent.mean_absolute_error) / scale
            if normalized_regression > self.promotion_policy.max_horizon_normalized_mae_regression + _EPSILON:
                regressions.append(item.horizon)

        reasons: list[str] = []
        if improvement + _EPSILON < self.promotion_policy.minimum_relative_improvement:
            reasons.append("insufficient_improvement")
        if regressions:
            reasons.append("horizon_regression")
        selected = not reasons
        final_result = base
        if selected:
            final_result = self._fit_seasonal_result(
                series=series,
                horizon=horizon,
                base=base,
                seasonal_report=seasonal_report,
                seasonal_score=seasonal,
            )

        payload = {
            "series": series.fingerprint,
            "policy": self.policy_fingerprint,
            "base_result": base.result_fingerprint,
            "seasonal_tournament": seasonal_report.report_fingerprint,
            "nonseasonal_score": nonseasonal.evaluation_fingerprint,
            "seasonal_score": seasonal.evaluation_fingerprint,
            "seasonal_selected": selected,
            "relative_improvement": improvement,
            "horizon_regressions": regressions,
            "reasons": reasons,
            "final_result": final_result.result_fingerprint,
        }
        return SeasonalChallengeReport(
            final_result=final_result,
            nonseasonal_result=base,
            nonseasonal_score=nonseasonal,
            seasonal_score=seasonal,
            seasonal_tournament=seasonal_report,
            seasonal_selected=selected,
            relative_improvement=improvement,
            horizon_regressions=tuple(regressions),
            reasons=tuple(reasons),
            policy_fingerprint=self.policy_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def _fallback_report(self, base: PredictiveResult, *, reason: str) -> SeasonalChallengeReport:
        payload = {
            "base_result": base.result_fingerprint,
            "policy": self.policy_fingerprint,
            "reason": reason,
            "seasonal_selected": False,
        }
        return SeasonalChallengeReport(
            final_result=base,
            nonseasonal_result=base,
            nonseasonal_score=None,
            seasonal_score=None,
            seasonal_tournament=None,
            seasonal_selected=False,
            relative_improvement=0.0,
            horizon_regressions=(),
            reasons=(reason,),
            policy_fingerprint=self.policy_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def _evaluate_nonseasonal_common(
        self,
        series: HistoricalSeries,
        base: PredictiveResult,
        common_start: int,
    ) -> CommonFamilyScore:
        report = base.ensemble_report
        baseline = report.advanced_report.baseline_report.champion
        ar = report.advanced_report.autoregressive_champion
        ensemble = report.ensemble_champion
        horizons = self.engine_policy.forecast.horizons
        max_horizon = max(horizons)
        final_origin = len(series.observations) - max_horizon
        errors = {item: [] for item in horizons}
        actuals = {item: [] for item in horizons}
        origins = 0

        for origin in range(common_start, final_origin + 1):
            training = HistoricalSeries(
                series_id=f"{series.series_id}:seasonal-common-base:{origin}",
                observations=series.observations[:origin],
            )
            baseline_fit = HistoricalForecaster.fit(training, baseline.method, baseline.parameters)
            baseline_predictions = baseline_fit.forecast(max_horizon)
            ar_predictions: tuple[float, ...] | None = None
            if report.selected_family in {"autoregression", "ensemble"}:
                if ar is None:
                    raise SeasonalPredictiveError(
                        "selected nonseasonal family lacks AR evidence",
                        context={"reason": "missing_ar_evidence"},
                    )
                ar_predictions = AutoRegressiveForecaster.fit(training, ar.parameters).forecast(max_horizon)
            origins += 1
            for horizon in horizons:
                if report.selected_family == "baseline":
                    predicted = baseline_predictions[horizon - 1].predicted
                elif report.selected_family == "autoregression":
                    assert ar_predictions is not None
                    predicted = ar_predictions[horizon - 1]
                else:
                    if ensemble is None or ar_predictions is None:
                        raise SeasonalPredictiveError(
                            "selected ensemble lacks constituent evidence",
                            context={"reason": "missing_ensemble_evidence"},
                        )
                    predicted = (
                        ensemble.baseline_weight * baseline_predictions[horizon - 1].predicted
                        + ensemble.autoregression_weight * ar_predictions[horizon - 1]
                    )
                actual = series.observations[origin + horizon - 1].value
                errors[horizon].append(actual - predicted)
                actuals[horizon].append(actual)

        metrics = tuple(_metrics(item, errors[item], actuals[item]) for item in horizons)
        return self._score_from_metrics(
            family=report.selected_family,
            label=base.selected_label,
            metrics=metrics,
            origin_count=origins,
            common_start=common_start,
            scale=_causal_scale(series.values[:common_start]),
            source_fingerprint=report.report_fingerprint,
        )

    def _seasonal_common_score(
        self,
        series: HistoricalSeries,
        report: SeasonalTournamentReport,
    ) -> CommonFamilyScore:
        champion = report.champion
        metrics = tuple(
            FamilyHorizonScore(
                horizon=item.horizon,
                sample_count=item.sample_count,
                mean_absolute_error=item.mean_absolute_error,
                root_mean_squared_error=item.root_mean_squared_error,
                symmetric_mape=item.symmetric_mape,
            )
            for item in champion.horizons
        )
        label = f"{champion.method.value}(period={champion.parameters.period})"
        return self._score_from_metrics(
            family="seasonal",
            label=label,
            metrics=metrics,
            origin_count=champion.origin_count,
            common_start=report.common_origin_start,
            scale=_causal_scale(series.values[: report.common_origin_start]),
            source_fingerprint=champion.evaluation_fingerprint,
        )

    def _score_from_metrics(
        self,
        *,
        family: str,
        label: str,
        metrics: tuple[FamilyHorizonScore, ...],
        origin_count: int,
        common_start: int,
        scale: float,
        source_fingerprint: str,
    ) -> CommonFamilyScore:
        weights = self.engine_policy.forecast.normalized_horizon_weights
        aggregate_mae = sum(weight * item.mean_absolute_error for weight, item in zip(weights, metrics, strict=True))
        aggregate_rmse = sum(weight * item.root_mean_squared_error for weight, item in zip(weights, metrics, strict=True))
        aggregate_smape = sum(weight * item.symmetric_mape for weight, item in zip(weights, metrics, strict=True))
        policy = self.engine_policy.forecast
        weight_sum = policy.mae_weight + policy.rmse_weight + policy.smape_weight
        objective = (
            policy.mae_weight * aggregate_mae / scale
            + policy.rmse_weight * aggregate_rmse / scale
            + policy.smape_weight * aggregate_smape
        ) / weight_sum
        payload = {
            "family": family,
            "label": label,
            "source": source_fingerprint,
            "origin_count": origin_count,
            "common_start": common_start,
            "mae": aggregate_mae,
            "rmse": aggregate_rmse,
            "smape": aggregate_smape,
            "objective": objective,
        }
        return CommonFamilyScore(
            family=family,
            label=label,
            horizons=metrics,
            aggregate_mae=aggregate_mae,
            aggregate_rmse=aggregate_rmse,
            aggregate_smape=aggregate_smape,
            objective=objective,
            origin_count=origin_count,
            common_origin_start=common_start,
            evaluation_fingerprint=canonical_fingerprint(payload),
        )

    def _fit_seasonal_result(
        self,
        *,
        series: HistoricalSeries,
        horizon: int,
        base: PredictiveResult,
        seasonal_report: SeasonalTournamentReport,
        seasonal_score: CommonFamilyScore,
    ) -> PredictiveResult:
        champion = seasonal_report.champion
        fitted = HistoricalSeasonalForecaster.fit(series, champion.method, champion.parameters)
        predictions = fitted.forecast(horizon)
        band = None
        conformal_status = "unavailable"
        try:
            band = self.calibrator.fit(
                champion.residuals,
                source_fingerprint=champion.evaluation_fingerprint,
            )
            conformal_status = "calibrated"
        except HistoricalConformalError as exc:
            conformal_status = str(exc.context.get("reason", "unavailable"))
            if self.engine_policy.require_conformal:
                raise SeasonalPredictiveError(
                    "selected seasonal forecast lacks required conformal evidence",
                    context={"reason": "conformal_required", "detail": exc.context},
                    cause=exc,
                ) from exc

        if band is None:
            points = tuple(
                PredictivePoint(horizon=index, predicted=value, lower=None, upper=None)
                for index, value in enumerate(predictions, start=1)
            )
        else:
            intervals = band.apply(predictions)
            points = tuple(
                PredictivePoint(
                    horizon=item.horizon,
                    predicted=item.predicted,
                    lower=item.lower,
                    upper=item.upper,
                )
                for item in intervals
            )
        label = f"{champion.method.value}(period={champion.parameters.period})"
        payload = {
            "series": series.fingerprint,
            "policy": self.policy_fingerprint,
            "family": "seasonal",
            "label": label,
            "seasonal_tournament": seasonal_report.report_fingerprint,
            "common_score": seasonal_score.evaluation_fingerprint,
            "conformal": band.band_fingerprint if band is not None else None,
            "regime": base.regime_report.report_fingerprint if base.regime_report is not None else None,
            "points": [
                {"horizon": item.horizon, "predicted": item.predicted, "lower": item.lower, "upper": item.upper}
                for item in points
            ],
        }
        return PredictiveResult(
            selected_family="seasonal",
            selected_label=label,
            selected_objective=seasonal_score.objective,
            points=points,
            ensemble_report=base.ensemble_report,
            conformal_band=band,
            conformal_status=conformal_status,
            regime_report=base.regime_report,
            regime_status=base.regime_status,
            training_fingerprint=series.fingerprint,
            policy_fingerprint=self.policy_fingerprint,
            result_fingerprint=canonical_fingerprint(payload),
        )


def summarize_seasonal_challenge(report: SeasonalChallengeReport) -> dict[str, object]:
    return {
        "seasonal_selected": report.seasonal_selected,
        "relative_improvement": report.relative_improvement,
        "horizon_regressions": list(report.horizon_regressions),
        "reasons": list(report.reasons),
        "final_family": report.final_result.selected_family,
        "final_label": report.final_result.selected_label,
        "nonseasonal_objective": None if report.nonseasonal_score is None else report.nonseasonal_score.objective,
        "seasonal_objective": None if report.seasonal_score is None else report.seasonal_score.objective,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }


def _metrics(horizon: int, errors: list[float], actuals: list[float]) -> FamilyHorizonScore:
    if not errors or len(errors) != len(actuals):
        raise SeasonalPredictiveError("family metric inputs must align", context={"reason": "metric_input_mismatch"})
    absolute = [abs(item) for item in errors]
    rmse = math.sqrt(sum(item * item for item in errors) / len(errors))
    smape_terms: list[float] = []
    for error, actual in zip(errors, actuals, strict=True):
        predicted = actual - error
        denominator = abs(actual) + abs(predicted)
        smape_terms.append(0.0 if denominator <= _EPSILON else 2.0 * abs(error) / denominator)
    return FamilyHorizonScore(
        horizon=horizon,
        sample_count=len(errors),
        mean_absolute_error=sum(absolute) / len(absolute),
        root_mean_squared_error=rmse,
        symmetric_mape=sum(smape_terms) / len(smape_terms),
    )


def _causal_scale(values: tuple[float, ...]) -> float:
    if not values:
        return 1.0
    scale = median(abs(item) for item in values)
    if scale <= _EPSILON:
        scale = max(1.0, max(abs(item) for item in values))
    return scale


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SeasonalPredictiveError(f"{name} must be numeric", context={"reason": "invalid_number", "field": name})
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise SeasonalPredictiveError(
            f"{name} must be finite and between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number