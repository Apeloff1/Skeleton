"""Leakage-safe regime-aware training-route selection for Jeeves forecasts.

A changepoint detector may suggest that older observations belong to an obsolete
regime, but that suggestion is not enough to discard history.  This module turns
that diagnostic into a falsifiable route decision:

* reserve a terminal validation window;
* detect a break using only data before that window;
* train/evaluate the full-history and post-break routes independently;
* score both routes on the exact same unseen validation observations; and
* admit the post-break route only after a configured material improvement.

After route selection, the chosen history rule is refit including the historical
validation window and used to create the requested forward forecast.  No future
observation is visible to the route decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Final

from skeleton.jeeves.historical_forecasting import HistoricalForecastError, HistoricalSeries
from skeleton.jeeves.historical_models import canonical_fingerprint
from skeleton.jeeves.historical_regimes import HistoricalRegimeDetector, RegimeShiftReport
from skeleton.jeeves.predictive_engine import (
    JeevesPredictiveEngine,
    PredictiveEngineError,
    PredictiveEnginePolicy,
    PredictiveResult,
)


_EPSILON: Final = 1e-12
MAX_VALIDATION_POINTS: Final = 128


class PredictiveRegimeRoutingError(HistoricalForecastError):
    """Fail-closed regime-route selection contract violation."""

    code = "JVS.PREDICTIVE_REGIME_ROUTE"
    http_status = 422


@dataclass(frozen=True, slots=True)
class RegimeRoutePolicy:
    validation_points: int = 6
    minimum_post_break_points: int = 16
    minimum_relative_improvement: float = 0.05
    require_recent_break: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.validation_points, bool)
            or not isinstance(self.validation_points, int)
            or not 1 <= self.validation_points <= MAX_VALIDATION_POINTS
        ):
            raise PredictiveRegimeRoutingError(
                f"validation_points must be between 1 and {MAX_VALIDATION_POINTS}",
                context={"reason": "invalid_validation_points"},
            )
        if (
            isinstance(self.minimum_post_break_points, bool)
            or not isinstance(self.minimum_post_break_points, int)
            or self.minimum_post_break_points < 3
        ):
            raise PredictiveRegimeRoutingError(
                "minimum_post_break_points must be an integer of at least 3",
                context={"reason": "invalid_post_break_minimum"},
            )
        improvement = _finite("minimum_relative_improvement", self.minimum_relative_improvement)
        if improvement < 0.0 or improvement > 1.0:
            raise PredictiveRegimeRoutingError(
                "minimum_relative_improvement must be between 0 and 1",
                context={"reason": "invalid_improvement_threshold"},
            )
        if not isinstance(self.require_recent_break, bool):
            raise PredictiveRegimeRoutingError(
                "require_recent_break must be boolean",
                context={"reason": "invalid_recent_flag"},
            )
        object.__setattr__(self, "minimum_relative_improvement", improvement)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "validation_points": self.validation_points,
                "minimum_post_break_points": self.minimum_post_break_points,
                "minimum_relative_improvement": self.minimum_relative_improvement,
                "require_recent_break": self.require_recent_break,
            }
        )


@dataclass(frozen=True, slots=True)
class RouteValidationScore:
    route: str
    training_start: int
    sample_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    symmetric_mape: float
    objective: float
    result_fingerprint: str


@dataclass(frozen=True, slots=True)
class RegimeRouteReport:
    selected_route: str
    selected_training_start: int
    full_history_score: RouteValidationScore
    post_break_score: RouteValidationScore | None
    relative_improvement: float
    regime_report: RegimeShiftReport | None
    route_reason: str
    final_result: PredictiveResult
    selection_training_fingerprint: str
    validation_fingerprint: str
    policy_fingerprint: str
    report_fingerprint: str

    @property
    def post_break_selected(self) -> bool:
        return self.selected_route == "post_break"


class RegimeAwarePredictiveRouter:
    """Choose full-history or post-break training using a common terminal holdout."""

    def __init__(
        self,
        *,
        engine_policy: PredictiveEnginePolicy | None = None,
        route_policy: RegimeRoutePolicy | None = None,
    ) -> None:
        self.engine_policy = engine_policy or PredictiveEnginePolicy()
        self.route_policy = route_policy or RegimeRoutePolicy()
        if not isinstance(self.engine_policy, PredictiveEnginePolicy):
            raise PredictiveRegimeRoutingError(
                "engine_policy must be PredictiveEnginePolicy",
                context={"reason": "invalid_engine_policy"},
            )
        if not isinstance(self.route_policy, RegimeRoutePolicy):
            raise PredictiveRegimeRoutingError(
                "route_policy must be RegimeRoutePolicy",
                context={"reason": "invalid_route_policy"},
            )
        # Route selection must not fail merely because interval/regime evidence is
        # unavailable on a reduced training view. Those requirements are applied
        # again to the final selected route using the caller's original policy.
        selection_policy = PredictiveEnginePolicy(
            forecast=self.engine_policy.forecast,
            autoregression=self.engine_policy.autoregression,
            ensemble=self.engine_policy.ensemble,
            conformal=self.engine_policy.conformal,
            regime=self.engine_policy.regime,
            require_conformal=False,
            require_regime_diagnostic=False,
        )
        self.selection_engine = JeevesPredictiveEngine(selection_policy)
        self.final_engine = JeevesPredictiveEngine(self.engine_policy)
        self.detector = HistoricalRegimeDetector(self.engine_policy.regime)

    def evaluate(self, series: HistoricalSeries, *, horizon: int) -> RegimeRouteReport:
        if not isinstance(series, HistoricalSeries):
            raise PredictiveRegimeRoutingError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        validation_points = self.route_policy.validation_points
        if len(series.observations) <= validation_points:
            raise PredictiveRegimeRoutingError(
                "series is too short to reserve terminal validation",
                context={"reason": "insufficient_points_for_validation"},
            )

        selection_observations = series.observations[:-validation_points]
        validation_observations = series.observations[-validation_points:]
        selection_series = HistoricalSeries(
            series_id=f"{series.series_id}:route-selection",
            observations=selection_observations,
        )
        actuals = tuple(item.value for item in validation_observations)
        full_result = self._selection_result(selection_series, validation_points, route="full_history")
        scale = _causal_scale(selection_series.values)
        full_score = self._score(
            route="full_history",
            training_start=0,
            predictions=tuple(point.predicted for point in full_result.points),
            actuals=actuals,
            scale=scale,
            result_fingerprint=full_result.result_fingerprint,
        )

        regime_report = self._detect_optional(selection_series)
        post_score: RouteValidationScore | None = None
        post_start = 0
        route_reason = "no_eligible_break"

        if regime_report is not None and regime_report.detected:
            post_start = regime_report.recommended_training_start
            if not self.route_policy.require_recent_break:
                post_start = regime_report.best.split_index
            if self.route_policy.require_recent_break and not regime_report.recent:
                route_reason = "break_not_recent"
                post_start = 0
            elif post_start <= 0:
                route_reason = "break_not_routable"
            elif len(selection_observations) - post_start < self.route_policy.minimum_post_break_points:
                route_reason = "post_break_history_too_short"
            else:
                tail_series = HistoricalSeries(
                    series_id=f"{series.series_id}:route-selection:post-break:{post_start}",
                    observations=selection_observations[post_start:],
                )
                try:
                    tail_result = self._selection_result(tail_series, validation_points, route="post_break")
                except PredictiveRegimeRoutingError:
                    route_reason = "post_break_modeling_failed"
                else:
                    post_score = self._score(
                        route="post_break",
                        training_start=post_start,
                        predictions=tuple(point.predicted for point in tail_result.points),
                        actuals=actuals,
                        scale=scale,
                        result_fingerprint=tail_result.result_fingerprint,
                    )
                    route_reason = "post_break_compared"

        improvement = 0.0
        selected_route = "full_history"
        selected_start = 0
        if post_score is not None:
            improvement = (full_score.objective - post_score.objective) / max(full_score.objective, _EPSILON)
            if improvement + _EPSILON >= self.route_policy.minimum_relative_improvement:
                selected_route = "post_break"
                selected_start = post_score.training_start
                route_reason = "post_break_validated"
            else:
                route_reason = "post_break_improvement_insufficient"

        final_series = series
        if selected_route == "post_break":
            final_observations = series.observations[selected_start:]
            if len(final_observations) < self.route_policy.minimum_post_break_points:
                raise PredictiveRegimeRoutingError(
                    "validated post-break route became too short during refit",
                    context={"reason": "final_post_break_too_short"},
                )
            final_series = HistoricalSeries(
                series_id=f"{series.series_id}:validated-post-break:{selected_start}",
                observations=final_observations,
            )
        try:
            final_result = self.final_engine.evaluate(final_series, horizon=horizon)
        except PredictiveEngineError as exc:
            raise PredictiveRegimeRoutingError(
                "final selected predictive route failed",
                context={"reason": "final_route_failed", "detail": exc.context},
                cause=exc,
            ) from exc

        validation_fingerprint = canonical_fingerprint(
            [
                {"timestamp": item.timestamp, "value": item.value}
                for item in validation_observations
            ]
        )
        payload = {
            "source_series": series.fingerprint,
            "selection_training": selection_series.fingerprint,
            "validation": validation_fingerprint,
            "engine_policy": self.engine_policy.fingerprint,
            "route_policy": self.route_policy.fingerprint,
            "regime": regime_report.report_fingerprint if regime_report is not None else None,
            "full": full_score.result_fingerprint,
            "post": post_score.result_fingerprint if post_score is not None else None,
            "relative_improvement": improvement,
            "selected_route": selected_route,
            "selected_start": selected_start,
            "route_reason": route_reason,
            "final_result": final_result.result_fingerprint,
        }
        return RegimeRouteReport(
            selected_route=selected_route,
            selected_training_start=selected_start,
            full_history_score=full_score,
            post_break_score=post_score,
            relative_improvement=improvement,
            regime_report=regime_report,
            route_reason=route_reason,
            final_result=final_result,
            selection_training_fingerprint=selection_series.fingerprint,
            validation_fingerprint=validation_fingerprint,
            policy_fingerprint=self.route_policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def _selection_result(self, series: HistoricalSeries, horizon: int, *, route: str) -> PredictiveResult:
        try:
            result = self.selection_engine.evaluate(series, horizon=horizon)
        except (PredictiveEngineError, HistoricalForecastError) as exc:
            context = getattr(exc, "context", {})
            raise PredictiveRegimeRoutingError(
                f"{route} route cannot be evaluated on the reserved validation window",
                context={"reason": "route_modeling_failed", "route": route, "detail": context},
                cause=exc,
            ) from exc
        if len(result.points) != horizon:
            raise PredictiveRegimeRoutingError(
                "route forecast does not cover validation window",
                context={"reason": "validation_horizon_mismatch", "route": route},
            )
        return result

    def _detect_optional(self, selection_series: HistoricalSeries) -> RegimeShiftReport | None:
        try:
            return self.detector.analyze(selection_series)
        except HistoricalForecastError:
            return None

    def _score(
        self,
        *,
        route: str,
        training_start: int,
        predictions: tuple[float, ...],
        actuals: tuple[float, ...],
        scale: float,
        result_fingerprint: str,
    ) -> RouteValidationScore:
        if not predictions or len(predictions) != len(actuals):
            raise PredictiveRegimeRoutingError(
                "validation predictions and actuals must align",
                context={"reason": "validation_length_mismatch", "route": route},
            )
        errors = [actual - predicted for predicted, actual in zip(predictions, actuals, strict=True)]
        mae = sum(abs(error) for error in errors) / len(errors)
        rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
        smape_terms = []
        for predicted, actual in zip(predictions, actuals, strict=True):
            denominator = abs(predicted) + abs(actual)
            smape_terms.append(0.0 if denominator <= _EPSILON else 2.0 * abs(actual - predicted) / denominator)
        smape = sum(smape_terms) / len(smape_terms)
        weights = self.engine_policy.forecast
        weight_sum = weights.mae_weight + weights.rmse_weight + weights.smape_weight
        objective = (
            weights.mae_weight * (mae / scale)
            + weights.rmse_weight * (rmse / scale)
            + weights.smape_weight * smape
        ) / weight_sum
        return RouteValidationScore(
            route=route,
            training_start=training_start,
            sample_count=len(errors),
            mean_absolute_error=mae,
            root_mean_squared_error=rmse,
            symmetric_mape=smape,
            objective=objective,
            result_fingerprint=result_fingerprint,
        )


def summarize_regime_route(report: RegimeRouteReport) -> dict[str, object]:
    return {
        "selected_route": report.selected_route,
        "selected_training_start": report.selected_training_start,
        "post_break_selected": report.post_break_selected,
        "relative_improvement": report.relative_improvement,
        "route_reason": report.route_reason,
        "regime_detected": bool(report.regime_report is not None and report.regime_report.detected),
        "regime_recent": bool(report.regime_report is not None and report.regime_report.recent),
        "full_history": _score_payload(report.full_history_score),
        "post_break": None if report.post_break_score is None else _score_payload(report.post_break_score),
        "final_selected_family": report.final_result.selected_family,
        "final_selected_label": report.final_result.selected_label,
        "selection_training_fingerprint": report.selection_training_fingerprint,
        "validation_fingerprint": report.validation_fingerprint,
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }


def _score_payload(score: RouteValidationScore) -> dict[str, object]:
    return {
        "route": score.route,
        "training_start": score.training_start,
        "sample_count": score.sample_count,
        "mae": score.mean_absolute_error,
        "rmse": score.root_mean_squared_error,
        "smape": score.symmetric_mape,
        "objective": score.objective,
        "result_fingerprint": score.result_fingerprint,
    }


def _causal_scale(values: tuple[float, ...]) -> float:
    if not values:
        return 1.0
    scale = median(abs(value) for value in values)
    if scale <= _EPSILON:
        scale = max(1.0, max(abs(value) for value in values))
    return scale


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PredictiveRegimeRoutingError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise PredictiveRegimeRoutingError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number