"""Forward-outcome calibration for Jeeves historical model scores.

A ranking score is useful only if its magnitude has a stable relationship with
future performance. This module turns temporal backtest folds into calibration
points and fits a small deterministic affine calibration model. The fit is
strictly descriptive and derived from already-completed backtests; it never
alters benchmark evidence or champion state.

The implementation intentionally stays simple, bounded, and inspectable. It
reports bias, absolute error, RMSE, bins, and fit quality instead of hiding score
corrections inside a learned black box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_backtest import BacktestReport, HistoricalBacktestError
from skeleton.jeeves.historical_models import canonical_fingerprint


DEFAULT_CALIBRATION_BINS: Final = 5
MAX_CALIBRATION_BINS: Final = 50
_EPSILON: Final = 1e-12


class HistoricalCalibrationError(HistoricalBacktestError):
    code = "JVS.HISTORICAL_CALIBRATION"
    http_status = 422


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalCalibrationError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise HistoricalCalibrationError(
            f"{name} must be finite and between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _positive_int(name: str, value: object, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalCalibrationError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    if maximum is not None and value > maximum:
        raise HistoricalCalibrationError(
            f"{name} exceeds maximum",
            context={"reason": "too_large", "field": name, "maximum": maximum},
        )
    return value


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    fold_id: str
    predicted_score: float
    realized_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.fold_id, str) or not self.fold_id.strip() or len(self.fold_id) > 160:
            raise HistoricalCalibrationError(
                "fold_id must be a bounded non-empty string",
                context={"reason": "invalid_fold_id"},
            )
        object.__setattr__(self, "fold_id", self.fold_id.strip())
        object.__setattr__(self, "predicted_score", _unit("predicted_score", self.predicted_score))
        object.__setattr__(self, "realized_score", _unit("realized_score", self.realized_score))

    @property
    def error(self) -> float:
        return self.realized_score - self.predicted_score

    @property
    def absolute_error(self) -> float:
        return abs(self.error)


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float
    mean_realized: float
    gap: float


@dataclass(frozen=True, slots=True)
class CalibrationModel:
    """Deterministic clipped affine score calibration."""

    slope: float
    intercept: float
    source_fingerprint: str

    def calibrate(self, score: float) -> float:
        score = _unit("score", score)
        calibrated = self.intercept + self.slope * score
        return min(1.0, max(0.0, calibrated))


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    points: tuple[CalibrationPoint, ...]
    bins: tuple[CalibrationBin, ...]
    mean_bias: float
    mean_absolute_error: float
    root_mean_squared_error: float
    max_absolute_error: float
    slope: float
    intercept: float
    r_squared: float
    report_fingerprint: str

    @property
    def sample_count(self) -> int:
        return len(self.points)

    @property
    def model(self) -> CalibrationModel:
        return CalibrationModel(
            slope=self.slope,
            intercept=self.intercept,
            source_fingerprint=self.report_fingerprint,
        )


class HistoricalScoreCalibrator:
    """Fit transparent calibration from temporal backtest outcomes."""

    @staticmethod
    def points_from_backtest(report: BacktestReport) -> tuple[CalibrationPoint, ...]:
        if not isinstance(report, BacktestReport):
            raise HistoricalCalibrationError(
                "report must be BacktestReport",
                context={"reason": "invalid_report"},
            )
        return tuple(
            CalibrationPoint(
                fold_id=fold.fold.fold_id,
                predicted_score=fold.ranking.champion.conservative_score,
                realized_score=fold.selected_holdout.score,
            )
            for fold in report.folds
        )

    @classmethod
    def fit_backtest(
        cls,
        report: BacktestReport,
        *,
        bins: int = DEFAULT_CALIBRATION_BINS,
    ) -> CalibrationReport:
        return cls.fit(cls.points_from_backtest(report), bins=bins)

    @staticmethod
    def fit(
        points: tuple[CalibrationPoint, ...] | list[CalibrationPoint],
        *,
        bins: int = DEFAULT_CALIBRATION_BINS,
    ) -> CalibrationReport:
        bins = _positive_int("bins", bins, maximum=MAX_CALIBRATION_BINS)
        normalized = tuple(points)
        if not normalized:
            raise HistoricalCalibrationError(
                "at least one calibration point is required",
                context={"reason": "empty_calibration"},
            )
        if any(not isinstance(point, CalibrationPoint) for point in normalized):
            raise HistoricalCalibrationError(
                "points must contain CalibrationPoint values",
                context={"reason": "invalid_point"},
            )
        fold_ids = [point.fold_id for point in normalized]
        if len(fold_ids) != len(set(fold_ids)):
            raise HistoricalCalibrationError(
                "calibration fold ids must be unique",
                context={"reason": "duplicate_fold_id"},
            )

        errors = [point.error for point in normalized]
        mean_bias = sum(errors) / len(errors)
        mae = sum(abs(error) for error in errors) / len(errors)
        rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
        max_abs = max(abs(error) for error in errors)
        slope, intercept, r_squared = HistoricalScoreCalibrator._fit_affine(normalized)
        calibration_bins = HistoricalScoreCalibrator._build_bins(normalized, bins=bins)
        payload = {
            "points": [
                {
                    "fold_id": point.fold_id,
                    "predicted": point.predicted_score,
                    "realized": point.realized_score,
                }
                for point in normalized
            ],
            "bin_count": bins,
            "mean_bias": mean_bias,
            "mae": mae,
            "rmse": rmse,
            "max_abs": max_abs,
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_squared,
        }
        return CalibrationReport(
            points=normalized,
            bins=calibration_bins,
            mean_bias=mean_bias,
            mean_absolute_error=mae,
            root_mean_squared_error=rmse,
            max_absolute_error=max_abs,
            slope=slope,
            intercept=intercept,
            r_squared=r_squared,
            report_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def _fit_affine(points: tuple[CalibrationPoint, ...]) -> tuple[float, float, float]:
        xs = [point.predicted_score for point in points]
        ys = [point.realized_score for point in points]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        variance_x = sum((x - mean_x) ** 2 for x in xs)
        if len(points) == 1 or variance_x <= _EPSILON:
            # Preserve score ordering and apply only the observed mean bias when
            # the dataset cannot identify a slope.
            slope = 1.0
            intercept = mean_y - mean_x
            fitted = [min(1.0, max(0.0, intercept + x)) for x in xs]
        else:
            covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
            slope = covariance / variance_x
            intercept = mean_y - slope * mean_x
            fitted = [min(1.0, max(0.0, intercept + slope * x)) for x in xs]

        ss_res = sum((y - fit) ** 2 for y, fit in zip(ys, fitted, strict=True))
        ss_tot = sum((y - mean_y) ** 2 for y in ys)
        if ss_tot <= _EPSILON:
            r_squared = 1.0 if ss_res <= _EPSILON else 0.0
        else:
            r_squared = 1.0 - ss_res / ss_tot
        return slope, intercept, r_squared

    @staticmethod
    def _build_bins(points: tuple[CalibrationPoint, ...], *, bins: int) -> tuple[CalibrationBin, ...]:
        buckets: list[list[CalibrationPoint]] = [[] for _ in range(bins)]
        for point in points:
            index = min(bins - 1, int(point.predicted_score * bins))
            buckets[index].append(point)
        result: list[CalibrationBin] = []
        for index, bucket in enumerate(buckets):
            if not bucket:
                continue
            lower = index / bins
            upper = (index + 1) / bins
            mean_predicted = sum(point.predicted_score for point in bucket) / len(bucket)
            mean_realized = sum(point.realized_score for point in bucket) / len(bucket)
            result.append(
                CalibrationBin(
                    lower=lower,
                    upper=upper,
                    count=len(bucket),
                    mean_predicted=mean_predicted,
                    mean_realized=mean_realized,
                    gap=mean_realized - mean_predicted,
                )
            )
        return tuple(result)


def summarize_calibration(report: CalibrationReport) -> dict[str, object]:
    return {
        "sample_count": report.sample_count,
        "mean_bias": report.mean_bias,
        "mean_absolute_error": report.mean_absolute_error,
        "root_mean_squared_error": report.root_mean_squared_error,
        "max_absolute_error": report.max_absolute_error,
        "slope": report.slope,
        "intercept": report.intercept,
        "r_squared": report.r_squared,
        "report_fingerprint": report.report_fingerprint,
        "bins": [
            {
                "lower": item.lower,
                "upper": item.upper,
                "count": item.count,
                "mean_predicted": item.mean_predicted,
                "mean_realized": item.mean_realized,
                "gap": item.gap,
            }
            for item in report.bins
        ],
    }