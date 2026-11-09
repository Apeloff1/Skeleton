"""Out-of-sample conformal-style forecast bands for Jeeves.

The base forecasters expose point predictions and rolling-origin residuals.  This
module converts those held-out residuals into deterministic empirical prediction
bands using a finite-sample conformal quantile.  The bands are deliberately
simple and auditable: no distribution is assumed and no hidden optimizer learns
interval width.

Classical conformal coverage guarantees require exchangeability assumptions that
may be violated by time series.  Accordingly, this module calls the result an
empirical conformal band and exposes explicit coverage audits instead of making
an unconditional probabilistic guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_autoregression import AutoRegressiveEvaluation
from skeleton.jeeves.historical_forecasting import (
    ForecastEvaluation,
    ForecastTournamentReport,
    HistoricalForecastError,
)
from skeleton.jeeves.historical_models import canonical_fingerprint


_EPSILON: Final = 1e-12
MAX_CALIBRATION_RESIDUALS: Final = 1_000_000
MAX_INTERVAL_POINTS: Final = 100_000


class HistoricalConformalError(HistoricalForecastError):
    """Fail-closed empirical conformal calibration error."""

    code = "JVS.HISTORICAL_CONFORMAL"
    http_status = 422


@dataclass(frozen=True, slots=True)
class ConformalPolicy:
    coverage: float = 0.90
    minimum_residuals: int = 20
    horizon_growth_exponent: float = 0.5
    minimum_radius: float = 0.0

    def __post_init__(self) -> None:
        coverage = _finite("coverage", self.coverage)
        if not 0.0 < coverage < 1.0:
            raise HistoricalConformalError(
                "coverage must be strictly between 0 and 1",
                context={"reason": "invalid_coverage"},
            )
        if isinstance(self.minimum_residuals, bool) or not isinstance(self.minimum_residuals, int) or self.minimum_residuals <= 0:
            raise HistoricalConformalError(
                "minimum_residuals must be a positive integer",
                context={"reason": "invalid_minimum_residuals"},
            )
        growth = _finite("horizon_growth_exponent", self.horizon_growth_exponent)
        if growth < 0.0 or growth > 2.0:
            raise HistoricalConformalError(
                "horizon_growth_exponent must be between 0 and 2",
                context={"reason": "invalid_growth_exponent"},
            )
        radius = _finite("minimum_radius", self.minimum_radius)
        if radius < 0.0:
            raise HistoricalConformalError(
                "minimum_radius must be non-negative",
                context={"reason": "invalid_minimum_radius"},
            )
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "horizon_growth_exponent", growth)
        object.__setattr__(self, "minimum_radius", radius)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "coverage": self.coverage,
                "minimum_residuals": self.minimum_residuals,
                "horizon_growth_exponent": self.horizon_growth_exponent,
                "minimum_radius": self.minimum_radius,
            }
        )


@dataclass(frozen=True, slots=True)
class ConformalIntervalPoint:
    horizon: int
    predicted: float
    lower: float
    upper: float
    radius: float

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise HistoricalConformalError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        predicted = _finite("predicted", self.predicted)
        lower = _finite("lower", self.lower)
        upper = _finite("upper", self.upper)
        radius = _finite("radius", self.radius)
        if radius < 0.0 or lower > predicted + _EPSILON or upper + _EPSILON < predicted or lower > upper:
            raise HistoricalConformalError(
                "invalid conformal interval",
                context={"reason": "invalid_interval"},
            )
        object.__setattr__(self, "predicted", predicted)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "radius", radius)


@dataclass(frozen=True, slots=True)
class ConformalBand:
    base_radius: float
    coverage: float
    horizon_growth_exponent: float
    residual_count: int
    quantile_rank: int
    source_fingerprint: str
    policy_fingerprint: str
    band_fingerprint: str

    def __post_init__(self) -> None:
        radius = _finite("base_radius", self.base_radius)
        if radius < 0.0:
            raise HistoricalConformalError(
                "base_radius must be non-negative",
                context={"reason": "invalid_radius"},
            )
        if isinstance(self.residual_count, bool) or not isinstance(self.residual_count, int) or self.residual_count <= 0:
            raise HistoricalConformalError(
                "residual_count must be positive",
                context={"reason": "invalid_residual_count"},
            )
        if isinstance(self.quantile_rank, bool) or not isinstance(self.quantile_rank, int) or not 1 <= self.quantile_rank <= self.residual_count:
            raise HistoricalConformalError(
                "quantile_rank must index residual evidence",
                context={"reason": "invalid_quantile_rank"},
            )

    def radius_for(self, horizon: int) -> float:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise HistoricalConformalError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon"},
            )
        return self.base_radius * (float(horizon) ** self.horizon_growth_exponent)

    def apply(self, predictions: tuple[float, ...] | list[float]) -> tuple[ConformalIntervalPoint, ...]:
        predictions = tuple(predictions)
        if not predictions:
            raise HistoricalConformalError(
                "predictions must not be empty",
                context={"reason": "empty_predictions"},
            )
        if len(predictions) > MAX_INTERVAL_POINTS:
            raise HistoricalConformalError(
                "prediction count exceeds interval limit",
                context={"reason": "too_many_predictions", "max_points": MAX_INTERVAL_POINTS},
            )
        points: list[ConformalIntervalPoint] = []
        for horizon, raw in enumerate(predictions, start=1):
            predicted = _finite("prediction", raw)
            radius = self.radius_for(horizon)
            points.append(
                ConformalIntervalPoint(
                    horizon=horizon,
                    predicted=predicted,
                    lower=predicted - radius,
                    upper=predicted + radius,
                    radius=radius,
                )
            )
        return tuple(points)


@dataclass(frozen=True, slots=True)
class CoverageAudit:
    sample_count: int
    covered_count: int
    realized_coverage: float
    target_coverage: float
    coverage_gap: float
    mean_interval_width: float
    max_interval_width: float
    mean_absolute_miss: float
    audit_fingerprint: str

    @property
    def under_target(self) -> bool:
        return self.realized_coverage + _EPSILON < self.target_coverage


class HistoricalConformalCalibrator:
    """Calibrate empirical bands from rolling-origin residual evidence."""

    def __init__(self, policy: ConformalPolicy | None = None) -> None:
        self.policy = policy or ConformalPolicy()
        if not isinstance(self.policy, ConformalPolicy):
            raise HistoricalConformalError(
                "policy must be ConformalPolicy",
                context={"reason": "invalid_policy"},
            )

    def from_forecast_evaluation(self, evaluation: ForecastEvaluation) -> ConformalBand:
        if not isinstance(evaluation, ForecastEvaluation):
            raise HistoricalConformalError(
                "evaluation must be ForecastEvaluation",
                context={"reason": "invalid_evaluation"},
            )
        return self.fit(
            evaluation.residuals,
            source_fingerprint=evaluation.evaluation_fingerprint,
        )

    def from_tournament(self, report: ForecastTournamentReport) -> ConformalBand:
        if not isinstance(report, ForecastTournamentReport):
            raise HistoricalConformalError(
                "report must be ForecastTournamentReport",
                context={"reason": "invalid_report"},
            )
        return self.from_forecast_evaluation(report.champion)

    def from_autoregression(self, evaluation: AutoRegressiveEvaluation) -> ConformalBand:
        if not isinstance(evaluation, AutoRegressiveEvaluation):
            raise HistoricalConformalError(
                "evaluation must be AutoRegressiveEvaluation",
                context={"reason": "invalid_evaluation"},
            )
        return self.fit(
            evaluation.residuals,
            source_fingerprint=evaluation.evaluation_fingerprint,
        )

    def fit(self, residuals: tuple[float, ...] | list[float], *, source_fingerprint: str) -> ConformalBand:
        residuals = tuple(_finite("residual", value) for value in residuals)
        if len(residuals) < self.policy.minimum_residuals:
            raise HistoricalConformalError(
                "insufficient rolling-origin residuals for conformal calibration",
                context={
                    "reason": "insufficient_residuals",
                    "residual_count": len(residuals),
                    "minimum_residuals": self.policy.minimum_residuals,
                },
            )
        if len(residuals) > MAX_CALIBRATION_RESIDUALS:
            raise HistoricalConformalError(
                "residual evidence exceeds calibration limit",
                context={"reason": "too_many_residuals", "max_residuals": MAX_CALIBRATION_RESIDUALS},
            )
        if not isinstance(source_fingerprint, str) or not source_fingerprint.strip():
            raise HistoricalConformalError(
                "source_fingerprint is required",
                context={"reason": "missing_source_fingerprint"},
            )

        absolute = sorted(abs(value) for value in residuals)
        # Finite-sample split-conformal rank: ceil((n + 1) * target), clamped
        # because target ranks above n are represented by the maximum residual.
        rank = math.ceil((len(absolute) + 1) * self.policy.coverage)
        rank = min(len(absolute), max(1, rank))
        radius = max(self.policy.minimum_radius, absolute[rank - 1])
        payload = {
            "source": source_fingerprint,
            "policy": self.policy.fingerprint,
            "residual_count": len(absolute),
            "quantile_rank": rank,
            "base_radius": radius,
        }
        return ConformalBand(
            base_radius=radius,
            coverage=self.policy.coverage,
            horizon_growth_exponent=self.policy.horizon_growth_exponent,
            residual_count=len(absolute),
            quantile_rank=rank,
            source_fingerprint=source_fingerprint.strip(),
            policy_fingerprint=self.policy.fingerprint,
            band_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def audit(
        band: ConformalBand,
        *,
        predictions: tuple[float, ...] | list[float],
        actuals: tuple[float, ...] | list[float],
    ) -> CoverageAudit:
        if not isinstance(band, ConformalBand):
            raise HistoricalConformalError(
                "band must be ConformalBand",
                context={"reason": "invalid_band"},
            )
        predictions = tuple(predictions)
        actuals = tuple(actuals)
        if not predictions or len(predictions) != len(actuals):
            raise HistoricalConformalError(
                "predictions and actuals must be non-empty and equal length",
                context={"reason": "audit_length_mismatch"},
            )
        intervals = band.apply(predictions)
        covered = 0
        misses: list[float] = []
        widths: list[float] = []
        for interval, raw_actual in zip(intervals, actuals, strict=True):
            actual = _finite("actual", raw_actual)
            widths.append(interval.upper - interval.lower)
            if interval.lower - _EPSILON <= actual <= interval.upper + _EPSILON:
                covered += 1
                misses.append(0.0)
            elif actual < interval.lower:
                misses.append(interval.lower - actual)
            else:
                misses.append(actual - interval.upper)

        realized = covered / len(intervals)
        gap = realized - band.coverage
        mean_width = sum(widths) / len(widths)
        max_width = max(widths)
        mean_miss = sum(misses) / len(misses)
        payload = {
            "band": band.band_fingerprint,
            "sample_count": len(intervals),
            "covered": covered,
            "realized_coverage": realized,
            "target_coverage": band.coverage,
            "mean_width": mean_width,
            "max_width": max_width,
            "mean_absolute_miss": mean_miss,
        }
        return CoverageAudit(
            sample_count=len(intervals),
            covered_count=covered,
            realized_coverage=realized,
            target_coverage=band.coverage,
            coverage_gap=gap,
            mean_interval_width=mean_width,
            max_interval_width=max_width,
            mean_absolute_miss=mean_miss,
            audit_fingerprint=canonical_fingerprint(payload),
        )



def summarize_conformal_band(band: ConformalBand) -> dict[str, object]:
    return {
        "coverage": band.coverage,
        "base_radius": band.base_radius,
        "horizon_growth_exponent": band.horizon_growth_exponent,
        "residual_count": band.residual_count,
        "quantile_rank": band.quantile_rank,
        "source_fingerprint": band.source_fingerprint,
        "policy_fingerprint": band.policy_fingerprint,
        "band_fingerprint": band.band_fingerprint,
    }



def summarize_coverage_audit(audit: CoverageAudit) -> dict[str, object]:
    return {
        "sample_count": audit.sample_count,
        "covered_count": audit.covered_count,
        "realized_coverage": audit.realized_coverage,
        "target_coverage": audit.target_coverage,
        "coverage_gap": audit.coverage_gap,
        "under_target": audit.under_target,
        "mean_interval_width": audit.mean_interval_width,
        "max_interval_width": audit.max_interval_width,
        "mean_absolute_miss": audit.mean_absolute_miss,
        "audit_fingerprint": audit.audit_fingerprint,
    }



def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalConformalError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise HistoricalConformalError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return numeric