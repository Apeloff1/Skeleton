"""End-to-end evidence-gated predictive modeling for Jeeves.

This coordinator turns the lower-level forecasting components into one auditable
workflow without weakening their boundaries:

1. evaluate transparent baselines, ridge AR challengers, and a convex stack on
   the same expanding-window evidence;
2. fit only the selected family on the complete supplied history;
3. calibrate empirical conformal intervals from *that selected family's* held-
   out rolling-origin residuals;
4. attach structural-regime diagnostics without silently truncating history;
5. fingerprint the complete decision and every forecast point.

Regime detection is diagnostic by design. A detected break is not permission to
throw older data away: post-break training must be compared separately on a
common future evaluation window before it can replace the full-history route.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_autoregression import (
    AutoRegressiveFit,
    AutoRegressiveForecaster,
    AutoRegressiveSelectionPolicy,
)
from skeleton.jeeves.historical_conformal import (
    ConformalBand,
    ConformalIntervalPoint,
    ConformalPolicy,
    HistoricalConformalCalibrator,
    HistoricalConformalError,
)
from skeleton.jeeves.historical_ensemble import (
    FittedForecastEnsemble,
    ForecastEnsemblePolicy,
    ForecastEnsembleReport,
    HistoricalForecastEnsembler,
)
from skeleton.jeeves.historical_forecasting import (
    FittedForecast,
    ForecastSelectionPolicy,
    HistoricalForecastError,
    HistoricalForecaster,
    HistoricalSeries,
)
from skeleton.jeeves.historical_models import canonical_fingerprint
from skeleton.jeeves.historical_regimes import (
    HistoricalRegimeDetector,
    HistoricalRegimeError,
    RegimeDetectionPolicy,
    RegimeShiftReport,
)


_EPSILON: Final = 1e-12
MAX_PREDICTIVE_HORIZON: Final = 256


class PredictiveEngineError(HistoricalForecastError):
    """Fail-closed predictive orchestration contract violation."""

    code = "JVS.PREDICTIVE_ENGINE"
    http_status = 422


@dataclass(frozen=True, slots=True)
class PredictiveEnginePolicy:
    forecast: ForecastSelectionPolicy = ForecastSelectionPolicy()
    autoregression: AutoRegressiveSelectionPolicy = AutoRegressiveSelectionPolicy()
    ensemble: ForecastEnsemblePolicy = ForecastEnsemblePolicy()
    conformal: ConformalPolicy = ConformalPolicy()
    regime: RegimeDetectionPolicy = RegimeDetectionPolicy()
    require_conformal: bool = False
    require_regime_diagnostic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.forecast, ForecastSelectionPolicy):
            raise PredictiveEngineError(
                "forecast must be ForecastSelectionPolicy",
                context={"reason": "invalid_forecast_policy"},
            )
        if not isinstance(self.autoregression, AutoRegressiveSelectionPolicy):
            raise PredictiveEngineError(
                "autoregression must be AutoRegressiveSelectionPolicy",
                context={"reason": "invalid_autoregression_policy"},
            )
        if not isinstance(self.ensemble, ForecastEnsemblePolicy):
            raise PredictiveEngineError(
                "ensemble must be ForecastEnsemblePolicy",
                context={"reason": "invalid_ensemble_policy"},
            )
        if not isinstance(self.conformal, ConformalPolicy):
            raise PredictiveEngineError(
                "conformal must be ConformalPolicy",
                context={"reason": "invalid_conformal_policy"},
            )
        if not isinstance(self.regime, RegimeDetectionPolicy):
            raise PredictiveEngineError(
                "regime must be RegimeDetectionPolicy",
                context={"reason": "invalid_regime_policy"},
            )
        if not isinstance(self.require_conformal, bool) or not isinstance(self.require_regime_diagnostic, bool):
            raise PredictiveEngineError(
                "require flags must be boolean",
                context={"reason": "invalid_requirement_flag"},
            )

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "forecast": self.forecast.fingerprint,
                "autoregression": self.autoregression.fingerprint,
                "ensemble": self.ensemble.fingerprint,
                "conformal": self.conformal.fingerprint,
                "regime": self.regime.fingerprint,
                "require_conformal": self.require_conformal,
                "require_regime_diagnostic": self.require_regime_diagnostic,
            }
        )


@dataclass(frozen=True, slots=True)
class PredictivePoint:
    horizon: int
    predicted: float
    lower: float | None
    upper: float | None

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise PredictiveEngineError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        predicted = _finite("predicted", self.predicted)
        object.__setattr__(self, "predicted", predicted)
        if self.lower is not None:
            object.__setattr__(self, "lower", _finite("lower", self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", _finite("upper", self.upper))
        if self.lower is not None and self.upper is not None:
            if self.lower > predicted + _EPSILON or self.upper + _EPSILON < predicted or self.lower > self.upper:
                raise PredictiveEngineError(
                    "predictive interval must contain prediction",
                    context={"reason": "invalid_interval"},
                )


@dataclass(frozen=True, slots=True)
class PredictiveResult:
    selected_family: str
    selected_label: str
    selected_objective: float
    points: tuple[PredictivePoint, ...]
    ensemble_report: ForecastEnsembleReport
    conformal_band: ConformalBand | None
    conformal_status: str
    regime_report: RegimeShiftReport | None
    regime_status: str
    training_fingerprint: str
    policy_fingerprint: str
    result_fingerprint: str

    @property
    def interval_available(self) -> bool:
        return self.conformal_band is not None

    @property
    def regime_shift_detected(self) -> bool:
        return bool(self.regime_report is not None and self.regime_report.detected)


class JeevesPredictiveEngine:
    """Select, fit, calibrate, and diagnose a scalar Jeeves forecast."""

    def __init__(self, policy: PredictiveEnginePolicy | None = None) -> None:
        self.policy = policy or PredictiveEnginePolicy()
        if not isinstance(self.policy, PredictiveEnginePolicy):
            raise PredictiveEngineError(
                "policy must be PredictiveEnginePolicy",
                context={"reason": "invalid_policy"},
            )
        self.ensembler = HistoricalForecastEnsembler(
            forecast_policy=self.policy.forecast,
            autoregression_policy=self.policy.autoregression,
            ensemble_policy=self.policy.ensemble,
        )
        self.calibrator = HistoricalConformalCalibrator(self.policy.conformal)
        self.regime_detector = HistoricalRegimeDetector(self.policy.regime)

    def evaluate(self, series: HistoricalSeries, *, horizon: int) -> PredictiveResult:
        if not isinstance(series, HistoricalSeries):
            raise PredictiveEngineError(
                "series must be HistoricalSeries",
                context={"reason": "invalid_series"},
            )
        if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= MAX_PREDICTIVE_HORIZON:
            raise PredictiveEngineError(
                f"horizon must be between 1 and {MAX_PREDICTIVE_HORIZON}",
                context={"reason": "invalid_horizon"},
            )

        fitted, ensemble_report = self.ensembler.fit_selected(series)
        predictions = self._point_predictions(fitted, horizon)
        residuals, source_fingerprint = self._selected_residuals(series, ensemble_report)
        band, conformal_status = self._calibrate(residuals, source_fingerprint)
        intervals = band.apply(predictions) if band is not None else None
        points = self._points(predictions, intervals)
        regime_report, regime_status = self._regime(series)
        selected_label = self._selected_label(ensemble_report)

        payload = {
            "series": series.fingerprint,
            "policy": self.policy.fingerprint,
            "selected_family": ensemble_report.selected_family,
            "selected_label": selected_label,
            "selected_objective": ensemble_report.selected_objective,
            "ensemble_report": ensemble_report.report_fingerprint,
            "conformal_band": band.band_fingerprint if band is not None else None,
            "conformal_status": conformal_status,
            "regime_report": regime_report.report_fingerprint if regime_report is not None else None,
            "regime_status": regime_status,
            "points": [
                {
                    "horizon": point.horizon,
                    "predicted": point.predicted,
                    "lower": point.lower,
                    "upper": point.upper,
                }
                for point in points
            ],
        }
        return PredictiveResult(
            selected_family=ensemble_report.selected_family,
            selected_label=selected_label,
            selected_objective=ensemble_report.selected_objective,
            points=points,
            ensemble_report=ensemble_report,
            conformal_band=band,
            conformal_status=conformal_status,
            regime_report=regime_report,
            regime_status=regime_status,
            training_fingerprint=series.fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            result_fingerprint=canonical_fingerprint(payload),
        )

    def _calibrate(
        self,
        residuals: tuple[float, ...],
        source_fingerprint: str,
    ) -> tuple[ConformalBand | None, str]:
        try:
            return self.calibrator.fit(residuals, source_fingerprint=source_fingerprint), "calibrated"
        except HistoricalConformalError as exc:
            if self.policy.require_conformal:
                raise PredictiveEngineError(
                    "selected forecast lacks sufficient conformal calibration evidence",
                    context={"reason": "conformal_required", "detail": exc.context},
                    cause=exc,
                ) from exc
            return None, str(exc.context.get("reason", "unavailable"))

    def _regime(self, series: HistoricalSeries) -> tuple[RegimeShiftReport | None, str]:
        try:
            report = self.regime_detector.analyze(series)
        except HistoricalRegimeError as exc:
            if self.policy.require_regime_diagnostic:
                raise PredictiveEngineError(
                    "series lacks required regime diagnostic evidence",
                    context={"reason": "regime_required", "detail": exc.context},
                    cause=exc,
                ) from exc
            return None, str(exc.context.get("reason", "unavailable"))
        if report.detected and report.recent:
            return report, "recent_shift_detected"
        if report.detected:
            return report, "historical_shift_detected"
        return report, "stable"

    def _selected_residuals(
        self,
        series: HistoricalSeries,
        report: ForecastEnsembleReport,
    ) -> tuple[tuple[float, ...], str]:
        if report.ensemble_selected:
            champion = report.ensemble_champion
            ar_champion = report.advanced_report.autoregressive_champion
            if champion is None or ar_champion is None:
                raise PredictiveEngineError(
                    "ensemble selection is missing constituent evidence",
                    context={"reason": "missing_ensemble_evidence"},
                )
            baseline = report.advanced_report.baseline_report.champion
            max_horizon = max(self.policy.forecast.horizons)
            final_origin = len(series.observations) - max_horizon
            residuals: list[float] = []
            origins = 0
            for origin in range(self.policy.forecast.minimum_training_points, final_origin + 1):
                training = HistoricalSeries(
                    series_id=f"{series.series_id}:engine-ensemble-origin:{origin}",
                    observations=series.observations[:origin],
                )
                baseline_fit = HistoricalForecaster.fit(training, baseline.method, baseline.parameters)
                ar_fit = AutoRegressiveForecaster.fit(training, ar_champion.parameters)
                base_forecast = baseline_fit.forecast(max_horizon)
                ar_forecast = ar_fit.forecast(max_horizon)
                origins += 1
                for step in self.policy.forecast.horizons:
                    predicted = (
                        champion.baseline_weight * base_forecast[step - 1].predicted
                        + champion.autoregression_weight * ar_forecast[step - 1]
                    )
                    actual = series.observations[origin + step - 1].value
                    residuals.append(actual - predicted)
            if origins < self.policy.forecast.minimum_origins:
                raise PredictiveEngineError(
                    "selected ensemble lacks enough common rolling origins",
                    context={"reason": "insufficient_ensemble_origins", "origin_count": origins},
                )
            source = canonical_fingerprint(
                {
                    "ensemble_evaluation": champion.evaluation_fingerprint,
                    "report": report.report_fingerprint,
                    "residual_count": len(residuals),
                }
            )
            return tuple(residuals), source

        advanced = report.advanced_report
        if report.selected_family == "autoregression":
            ar = advanced.autoregressive_champion
            if ar is None:
                raise PredictiveEngineError(
                    "autoregression selected without autoregressive evidence",
                    context={"reason": "missing_ar_evidence"},
                )
            return ar.residuals, ar.evaluation_fingerprint
        baseline = advanced.baseline_report.champion
        return baseline.residuals, baseline.evaluation_fingerprint

    @staticmethod
    def _point_predictions(fitted: object, horizon: int) -> tuple[float, ...]:
        if isinstance(fitted, FittedForecast):
            return tuple(point.predicted for point in fitted.forecast(horizon))
        if isinstance(fitted, (AutoRegressiveFit, FittedForecastEnsemble)):
            return tuple(_finite("prediction", value) for value in fitted.forecast(horizon))
        raise PredictiveEngineError(
            "unsupported fitted forecast family",
            context={"reason": "unsupported_fit", "type": type(fitted).__name__},
        )

    @staticmethod
    def _points(
        predictions: tuple[float, ...],
        intervals: tuple[ConformalIntervalPoint, ...] | None,
    ) -> tuple[PredictivePoint, ...]:
        if intervals is None:
            return tuple(
                PredictivePoint(horizon=index, predicted=predicted, lower=None, upper=None)
                for index, predicted in enumerate(predictions, start=1)
            )
        if len(intervals) != len(predictions):
            raise PredictiveEngineError(
                "interval count does not match predictions",
                context={"reason": "interval_length_mismatch"},
            )
        return tuple(
            PredictivePoint(
                horizon=interval.horizon,
                predicted=interval.predicted,
                lower=interval.lower,
                upper=interval.upper,
            )
            for interval in intervals
        )

    @staticmethod
    def _selected_label(report: ForecastEnsembleReport) -> str:
        if report.ensemble_selected:
            champion = report.ensemble_champion
            if champion is None:
                return "ensemble"
            return f"ensemble(baseline={champion.baseline_weight:.3f},ar={champion.autoregression_weight:.3f})"
        advanced = report.advanced_report
        if report.selected_family == "autoregression" and advanced.autoregressive_champion is not None:
            return f"ar({advanced.autoregressive_champion.parameters.order})"
        return advanced.baseline_report.champion.method.value


def summarize_predictive_result(result: PredictiveResult) -> dict[str, object]:
    """Return a JSON-friendly predictive decision without hiding evidence state."""
    return {
        "selected_family": result.selected_family,
        "selected_label": result.selected_label,
        "selected_objective": result.selected_objective,
        "interval_available": result.interval_available,
        "conformal_status": result.conformal_status,
        "regime_status": result.regime_status,
        "regime_shift_detected": result.regime_shift_detected,
        "training_fingerprint": result.training_fingerprint,
        "policy_fingerprint": result.policy_fingerprint,
        "result_fingerprint": result.result_fingerprint,
        "points": [
            {
                "horizon": point.horizon,
                "predicted": point.predicted,
                "lower": point.lower,
                "upper": point.upper,
            }
            for point in result.points
        ],
    }


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PredictiveEngineError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise PredictiveEngineError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number