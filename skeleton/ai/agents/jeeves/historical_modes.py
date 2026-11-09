"""Offline historical-mode evaluation for Jeeves.

The historical lab answers a narrow question: which deterministic forecasting mode
has earned the right to be considered on a supplied history?

The module deliberately does *not*:
- call live models or providers,
- fetch market data,
- place trades or produce financial advice,
- mutate Jeeves learning state,
- let future samples leak into training folds.

It is a research/evaluation primitive. Callers may turn its immutable reports
into learning evidence through ``skeleton.learning.evidence`` if desired.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from skeleton.kernel.errors import KernelError

_EPSILON = 1e-12
_MAX_SERIES = 1_000_000
_DEFAULT_MIN_TRAIN = 12


class HistoricalModeError(KernelError):
    """Fail-closed validation error for the historical mode laboratory."""

    code = "JEEVES.HISTORICAL_MODE"
    http_status = 422


class HistoricalMode(str, Enum):
    """Deterministic forecasting families available to the offline evaluator."""

    PERSISTENCE = "persistence"
    GLOBAL_MEAN = "global_mean"
    ROBUST_MEDIAN = "robust_median"
    ROLLING_MEAN = "rolling_mean"
    EWMA = "ewma"
    DRIFT = "drift"
    LINEAR_TREND = "linear_trend"
    AR1 = "ar1"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    SEASONAL_NAIVE = "seasonal_naive"
    ADAPTIVE_ENSEMBLE = "adaptive_ensemble"


BASE_MODES: tuple[HistoricalMode, ...] = (
    HistoricalMode.PERSISTENCE,
    HistoricalMode.GLOBAL_MEAN,
    HistoricalMode.ROBUST_MEDIAN,
    HistoricalMode.ROLLING_MEAN,
    HistoricalMode.EWMA,
    HistoricalMode.DRIFT,
    HistoricalMode.LINEAR_TREND,
    HistoricalMode.AR1,
    HistoricalMode.MOMENTUM,
    HistoricalMode.MEAN_REVERSION,
    HistoricalMode.SEASONAL_NAIVE,
)


class Regime(str, Enum):
    """Descriptive shape of the training history, never a market-state claim."""

    INSUFFICIENT = "insufficient"
    QUIET = "quiet"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    VOLATILE = "volatile"
    OSCILLATING = "oscillating"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class HistoricalSeries:
    """Strictly ordered scalar history used by the evaluator."""

    values: tuple[float, ...]
    timestamps: tuple[float, ...] | None = None
    label: str = "series"

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise HistoricalModeError(
                "label must be a non-empty string",
                context={"reason": "invalid_label"},
            )
        if not self.values:
            raise HistoricalModeError(
                "historical series must contain at least one value",
                context={"reason": "empty_series"},
            )
        if len(self.values) > _MAX_SERIES:
            raise HistoricalModeError(
                "historical series is too large",
                context={"reason": "series_too_large", "max_samples": _MAX_SERIES},
            )

        clean_values = tuple(_finite("value", value) for value in self.values)
        object.__setattr__(self, "values", clean_values)

        if self.timestamps is None:
            return
        if len(self.timestamps) != len(clean_values):
            raise HistoricalModeError(
                "timestamps and values must have equal length",
                context={"reason": "length_mismatch"},
            )
        clean_timestamps = tuple(_finite("timestamp", value) for value in self.timestamps)
        if any(right <= left for left, right in zip(clean_timestamps, clean_timestamps[1:])):
            raise HistoricalModeError(
                "timestamps must be strictly increasing",
                context={"reason": "non_monotonic_time"},
            )
        object.__setattr__(self, "timestamps", clean_timestamps)

    @classmethod
    def from_values(
        cls,
        values: Iterable[float],
        *,
        timestamps: Iterable[float] | None = None,
        label: str = "series",
    ) -> "HistoricalSeries":
        return cls(
            values=tuple(values),
            timestamps=None if timestamps is None else tuple(timestamps),
            label=label,
        )

    def prefix(self, stop: int) -> "HistoricalSeries":
        if isinstance(stop, bool) or not isinstance(stop, int) or stop <= 0:
            raise HistoricalModeError(
                "prefix stop must be a positive integer",
                context={"reason": "invalid_prefix"},
            )
        if stop > len(self.values):
            raise HistoricalModeError(
                "prefix stop exceeds available history",
                context={"reason": "invalid_prefix", "stop": stop, "size": len(self.values)},
            )
        timestamps = None if self.timestamps is None else self.timestamps[:stop]
        return HistoricalSeries(self.values[:stop], timestamps=timestamps, label=self.label)


@dataclass(frozen=True, slots=True)
class Forecast:
    """One deterministic forecast emitted from a training prefix."""

    mode: HistoricalMode
    predicted: float
    train_size: int
    horizon: int
    regime: Regime
    metadata: tuple[tuple[str, float | int | str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicted", _finite("predicted", self.predicted))
        _positive_int("train_size", self.train_size)
        _positive_int("horizon", self.horizon)


@dataclass(frozen=True, slots=True)
class FoldResult:
    """Out-of-sample result for exactly one walk-forward fold."""

    mode: HistoricalMode
    train_end: int
    target_index: int
    predicted: float
    actual: float
    absolute_error: float
    squared_error: float
    directional_hit: bool | None
    regime: Regime

    def __post_init__(self) -> None:
        if self.target_index <= self.train_end:
            raise HistoricalModeError(
                "target must be strictly after the training boundary",
                context={"reason": "leakage_boundary"},
            )


@dataclass(frozen=True, slots=True)
class ModeMetrics:
    """Aggregated walk-forward metrics for a mode."""

    folds: int
    mae: float
    rmse: float
    smape: float
    bias: float
    directional_accuracy: float | None
    worst_absolute_error: float
    stability: float

    def score(self) -> float:
        """Lower-is-better composite with modest instability penalty."""

        direction_penalty = 0.0
        if self.directional_accuracy is not None:
            direction_penalty = max(0.0, 0.5 - self.directional_accuracy) * self.mae
        return self.mae + 0.15 * self.rmse + 0.05 * abs(self.bias) + 0.10 * self.stability + direction_penalty


@dataclass(frozen=True, slots=True)
class ModeReport:
    """Per-mode evaluation report."""

    mode: HistoricalMode
    metrics: ModeMetrics
    folds: tuple[FoldResult, ...]
    regime_metrics: tuple[tuple[Regime, ModeMetrics], ...] = ()

    def metrics_for(self, regime: Regime) -> ModeMetrics | None:
        for current, metrics in self.regime_metrics:
            if current is regime:
                return metrics
        return None


@dataclass(frozen=True, slots=True)
class SelectionGate:
    """Conditions a candidate must satisfy before historical promotion."""

    min_folds: int = 8
    min_relative_improvement: float = 0.02
    max_relative_worst_error: float = 1.50
    require_regime_coverage: bool = False

    def __post_init__(self) -> None:
        _positive_int("min_folds", self.min_folds)
        _unit_interval("min_relative_improvement", self.min_relative_improvement)
        if _finite("max_relative_worst_error", self.max_relative_worst_error) < 1.0:
            raise HistoricalModeError(
                "max_relative_worst_error must be at least 1",
                context={"reason": "invalid_gate"},
            )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Auditable offline decision against the persistence baseline."""

    candidate: HistoricalMode
    baseline: HistoricalMode
    accepted: bool
    reasons: tuple[str, ...]
    relative_mae_improvement: float
    candidate_metrics: ModeMetrics
    baseline_metrics: ModeMetrics


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Complete deterministic output from a historical lab run."""

    series_label: str
    config: "WalkForwardConfig"
    reports: tuple[ModeReport, ...]
    ranking: tuple[HistoricalMode, ...]
    promotion: PromotionDecision
    fingerprint: str

    def by_mode(self, mode: HistoricalMode) -> ModeReport:
        for report in self.reports:
            if report.mode is mode:
                return report
        raise HistoricalModeError(
            "requested mode is absent from evaluation",
            context={"reason": "unknown_mode", "mode": mode.value},
        )

    @property
    def selected_mode(self) -> HistoricalMode:
        return self.promotion.candidate if self.promotion.accepted else self.promotion.baseline

    def as_payload(self) -> dict[str, object]:
        """JSON-scalar-friendly summary suitable for evidence recording."""

        selected = self.by_mode(self.selected_mode)
        return {
            "series_label": self.series_label,
            "selected_mode": self.selected_mode.value,
            "promotion_accepted": self.promotion.accepted,
            "folds": selected.metrics.folds,
            "mae": selected.metrics.mae,
            "rmse": selected.metrics.rmse,
            "smape": selected.metrics.smape,
            "bias": selected.metrics.bias,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    """Leakage-safe walk-forward configuration."""

    min_train_size: int = _DEFAULT_MIN_TRAIN
    horizon: int = 1
    step: int = 1
    rolling_window: int = 8
    seasonal_period: int = 7
    ewma_alpha: float = 0.35
    momentum_window: int = 4
    reversion_window: int = 8
    ensemble_history: int = 8
    ensemble_top_k: int = 4

    def __post_init__(self) -> None:
        _positive_int("min_train_size", self.min_train_size)
        _positive_int("horizon", self.horizon)
        _positive_int("step", self.step)
        _positive_int("rolling_window", self.rolling_window)
        _positive_int("seasonal_period", self.seasonal_period)
        _open_unit("ewma_alpha", self.ewma_alpha)
        _positive_int("momentum_window", self.momentum_window)
        _positive_int("reversion_window", self.reversion_window)
        _positive_int("ensemble_history", self.ensemble_history)
        _positive_int("ensemble_top_k", self.ensemble_top_k)


@dataclass(frozen=True, slots=True)
class RegimeProfile:
    regime: Regime
    slope: float
    volatility: float
    lag1_autocorrelation: float
    normalized_slope: float


class HistoricalModeLab:
    """Evaluate deterministic historical modes with strict temporal custody."""

    def __init__(
        self,
        *,
        config: WalkForwardConfig | None = None,
        gate: SelectionGate | None = None,
        modes: Sequence[HistoricalMode] | None = None,
    ) -> None:
        self.config = config or WalkForwardConfig()
        self.gate = gate or SelectionGate()
        requested = tuple(modes or BASE_MODES)
        if not requested:
            raise HistoricalModeError(
                "at least one historical mode is required",
                context={"reason": "no_modes"},
            )
        if HistoricalMode.PERSISTENCE not in requested:
            requested = (HistoricalMode.PERSISTENCE, *requested)
        if HistoricalMode.ADAPTIVE_ENSEMBLE in requested:
            raise HistoricalModeError(
                "adaptive_ensemble is synthesized by the evaluator and must not be supplied as a base mode",
                context={"reason": "invalid_mode"},
            )
        if len(set(requested)) != len(requested):
            raise HistoricalModeError(
                "historical modes must be unique",
                context={"reason": "duplicate_mode"},
            )
        self.modes = requested

    def forecast(
        self,
        series: HistoricalSeries,
        mode: HistoricalMode,
        *,
        horizon: int | None = None,
    ) -> Forecast:
        """Forecast from *only* the supplied history."""

        actual_horizon = self.config.horizon if horizon is None else horizon
        _positive_int("horizon", actual_horizon)
        values = series.values
        if len(values) < 2 and mode not in {
            HistoricalMode.PERSISTENCE,
            HistoricalMode.GLOBAL_MEAN,
            HistoricalMode.ROBUST_MEDIAN,
        }:
            raise HistoricalModeError(
                "mode requires at least two training samples",
                context={"reason": "insufficient_history", "mode": mode.value},
            )
        profile = classify_regime(values)
        prediction, metadata = self._predict(values, mode, actual_horizon)
        return Forecast(
            mode=mode,
            predicted=prediction,
            train_size=len(values),
            horizon=actual_horizon,
            regime=profile.regime,
            metadata=tuple(sorted(metadata.items())),
        )

    def evaluate(self, series: HistoricalSeries) -> EvaluationReport:
        config = self.config
        if len(series.values) <= config.min_train_size + config.horizon - 1:
            raise HistoricalModeError(
                "series is too short for configured walk-forward evaluation",
                context={
                    "reason": "insufficient_history",
                    "samples": len(series.values),
                    "min_train_size": config.min_train_size,
                    "horizon": config.horizon,
                },
            )

        fold_map: dict[HistoricalMode, list[FoldResult]] = {mode: [] for mode in self.modes}
        ensemble_folds: list[FoldResult] = []

        for train_end in range(
            config.min_train_size - 1,
            len(series.values) - config.horizon,
            config.step,
        ):
            target_index = train_end + config.horizon
            training = series.values[: train_end + 1]
            actual = series.values[target_index]
            previous_actual = series.values[train_end]
            regime = classify_regime(training).regime

            predictions: dict[HistoricalMode, float] = {}
            for mode in self.modes:
                prediction, _ = self._predict(training, mode, config.horizon)
                predictions[mode] = prediction
                fold_map[mode].append(
                    _make_fold(
                        mode=mode,
                        train_end=train_end,
                        target_index=target_index,
                        predicted=prediction,
                        actual=actual,
                        previous_actual=previous_actual,
                        regime=regime,
                    )
                )

            ensemble_prediction = self._adaptive_ensemble_prediction(
                predictions=predictions,
                fold_map=fold_map,
                train_end=train_end,
            )
            ensemble_folds.append(
                _make_fold(
                    mode=HistoricalMode.ADAPTIVE_ENSEMBLE,
                    train_end=train_end,
                    target_index=target_index,
                    predicted=ensemble_prediction,
                    actual=actual,
                    previous_actual=previous_actual,
                    regime=regime,
                )
            )

        reports = [_build_mode_report(mode, tuple(folds)) for mode, folds in fold_map.items()]
        reports.append(_build_mode_report(HistoricalMode.ADAPTIVE_ENSEMBLE, tuple(ensemble_folds)))
        reports_tuple = tuple(reports)
        ranking = tuple(
            report.mode
            for report in sorted(
                reports_tuple,
                key=lambda report: (
                    report.metrics.score(),
                    report.metrics.mae,
                    report.metrics.rmse,
                    report.mode.value,
                ),
            )
        )
        baseline = _report_by_mode(reports_tuple, HistoricalMode.PERSISTENCE)
        candidate = _report_by_mode(reports_tuple, ranking[0])
        promotion = _promotion_decision(candidate, baseline, self.gate)
        fingerprint = _report_fingerprint(series, config, reports_tuple, ranking, promotion)
        return EvaluationReport(
            series_label=series.label,
            config=config,
            reports=reports_tuple,
            ranking=ranking,
            promotion=promotion,
            fingerprint=fingerprint,
        )

    def _predict(
        self,
        values: Sequence[float],
        mode: HistoricalMode,
        horizon: int,
    ) -> tuple[float, dict[str, float | int | str]]:
        config = self.config
        if mode is HistoricalMode.PERSISTENCE:
            return values[-1], {}
        if mode is HistoricalMode.GLOBAL_MEAN:
            return statistics.fmean(values), {}
        if mode is HistoricalMode.ROBUST_MEDIAN:
            return float(statistics.median(values)), {}
        if mode is HistoricalMode.ROLLING_MEAN:
            window = min(config.rolling_window, len(values))
            return statistics.fmean(values[-window:]), {"window": window}
        if mode is HistoricalMode.EWMA:
            estimate = values[0]
            alpha = config.ewma_alpha
            for value in values[1:]:
                estimate = alpha * value + (1.0 - alpha) * estimate
            return estimate, {"alpha": alpha}
        if mode is HistoricalMode.DRIFT:
            if len(values) < 2:
                return values[-1], {"fallback": "persistence"}
            per_step = (values[-1] - values[0]) / (len(values) - 1)
            return values[-1] + per_step * horizon, {"per_step": per_step}
        if mode is HistoricalMode.LINEAR_TREND:
            intercept, slope = _linear_fit(values)
            x = (len(values) - 1) + horizon
            return intercept + slope * x, {"slope": slope}
        if mode is HistoricalMode.AR1:
            return _ar1_forecast(values, horizon)
        if mode is HistoricalMode.MOMENTUM:
            window = min(config.momentum_window, len(values) - 1)
            if window <= 0:
                return values[-1], {"fallback": "persistence"}
            deltas = [values[index] - values[index - 1] for index in range(len(values) - window, len(values))]
            velocity = statistics.fmean(deltas)
            return values[-1] + velocity * horizon, {"window": window, "velocity": velocity}
        if mode is HistoricalMode.MEAN_REVERSION:
            window = min(config.reversion_window, len(values))
            center = statistics.fmean(values[-window:])
            lag1 = _lag1_autocorrelation(values[-window:])
            strength = min(0.75, max(0.0, -lag1))
            predicted = values[-1] + strength * (center - values[-1]) * min(horizon, 3)
            return predicted, {"window": window, "center": center, "strength": strength}
        if mode is HistoricalMode.SEASONAL_NAIVE:
            period = config.seasonal_period
            index = len(values) - period + ((horizon - 1) % period)
            if period <= len(values) and 0 <= index < len(values):
                return values[index], {"period": period}
            return values[-1], {"fallback": "persistence", "period": period}
        raise HistoricalModeError(
            "unsupported historical mode",
            context={"reason": "unsupported_mode", "mode": str(mode)},
        )

    def _adaptive_ensemble_prediction(
        self,
        *,
        predictions: Mapping[HistoricalMode, float],
        fold_map: Mapping[HistoricalMode, Sequence[FoldResult]],
        train_end: int,
    ) -> float:
        """Combine base modes using only errors observed before this fold.

        On the first fold there is no prior out-of-sample evidence, so all base
        models receive equal weight. Later folds use inverse recent MAE and
        keep only the strongest ``ensemble_top_k`` modes. The current fold's
        target is never used to compute its own weights.
        """

        history = self.config.ensemble_history
        scored: list[tuple[float, HistoricalMode]] = []
        for mode, prediction in predictions.items():
            del prediction
            prior = [fold for fold in fold_map[mode][:-1] if fold.train_end < train_end]
            if not prior:
                score = 1.0
            else:
                recent = prior[-history:]
                mae = statistics.fmean(fold.absolute_error for fold in recent)
                score = 1.0 / max(mae, _EPSILON)
            scored.append((score, mode))

        scored.sort(key=lambda item: (-item[0], item[1].value))
        selected = scored[: min(self.config.ensemble_top_k, len(scored))]
        total = sum(weight for weight, _ in selected)
        if total <= _EPSILON:
            return statistics.fmean(predictions[mode] for _, mode in selected)
        return sum(weight * predictions[mode] for weight, mode in selected) / total


def classify_regime(values: Sequence[float]) -> RegimeProfile:
    """Classify numeric shape using scale-normalized, deterministic statistics."""

    clean = tuple(_finite("value", value) for value in values)
    if len(clean) < 3:
        return RegimeProfile(
            regime=Regime.INSUFFICIENT,
            slope=0.0,
            volatility=0.0,
            lag1_autocorrelation=0.0,
            normalized_slope=0.0,
        )

    _, slope = _linear_fit(clean)
    deltas = tuple(right - left for left, right in zip(clean, clean[1:]))
    volatility = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
    scale = max(statistics.fmean(abs(value) for value in clean), 1.0, volatility)
    normalized_slope = slope / scale
    autocorr = _lag1_autocorrelation(clean)

    slope_signal = abs(normalized_slope)
    relative_volatility = volatility / scale

    if relative_volatility >= 0.20:
        regime = Regime.VOLATILE
    elif slope_signal >= 0.025:
        regime = Regime.TRENDING_UP if normalized_slope > 0 else Regime.TRENDING_DOWN
    elif autocorr <= -0.35:
        regime = Regime.OSCILLATING
    elif relative_volatility <= 0.01 and slope_signal <= 0.005:
        regime = Regime.QUIET
    else:
        regime = Regime.MIXED

    return RegimeProfile(
        regime=regime,
        slope=slope,
        volatility=volatility,
        lag1_autocorrelation=autocorr,
        normalized_slope=normalized_slope,
    )


def _build_mode_report(mode: HistoricalMode, folds: tuple[FoldResult, ...]) -> ModeReport:
    metrics = _aggregate_metrics(folds)
    by_regime: list[tuple[Regime, ModeMetrics]] = []
    for regime in Regime:
        selected = tuple(fold for fold in folds if fold.regime is regime)
        if selected:
            by_regime.append((regime, _aggregate_metrics(selected)))
    return ModeReport(
        mode=mode,
        metrics=metrics,
        folds=folds,
        regime_metrics=tuple(by_regime),
    )


def _aggregate_metrics(folds: Sequence[FoldResult]) -> ModeMetrics:
    if not folds:
        raise HistoricalModeError(
            "cannot aggregate zero folds",
            context={"reason": "no_folds"},
        )
    absolute = [fold.absolute_error for fold in folds]
    squared = [fold.squared_error for fold in folds]
    errors = [fold.predicted - fold.actual for fold in folds]
    smape_terms = []
    directional = []
    for fold in folds:
        denominator = abs(fold.actual) + abs(fold.predicted)
        smape_terms.append(0.0 if denominator <= _EPSILON else 2.0 * fold.absolute_error / denominator)
        if fold.directional_hit is not None:
            directional.append(1.0 if fold.directional_hit else 0.0)
    return ModeMetrics(
        folds=len(folds),
        mae=statistics.fmean(absolute),
        rmse=math.sqrt(statistics.fmean(squared)),
        smape=statistics.fmean(smape_terms),
        bias=statistics.fmean(errors),
        directional_accuracy=None if not directional else statistics.fmean(directional),
        worst_absolute_error=max(absolute),
        stability=statistics.pstdev(absolute) if len(absolute) > 1 else 0.0,
    )


def _make_fold(
    *,
    mode: HistoricalMode,
    train_end: int,
    target_index: int,
    predicted: float,
    actual: float,
    previous_actual: float,
    regime: Regime,
) -> FoldResult:
    predicted = _finite("predicted", predicted)
    actual = _finite("actual", actual)
    previous_actual = _finite("previous_actual", previous_actual)
    error = predicted - actual
    actual_direction = _sign(actual - previous_actual)
    predicted_direction = _sign(predicted - previous_actual)
    directional_hit: bool | None
    if actual_direction == 0:
        directional_hit = None
    else:
        directional_hit = predicted_direction == actual_direction
    return FoldResult(
        mode=mode,
        train_end=train_end,
        target_index=target_index,
        predicted=predicted,
        actual=actual,
        absolute_error=abs(error),
        squared_error=error * error,
        directional_hit=directional_hit,
        regime=regime,
    )


def _promotion_decision(
    candidate: ModeReport,
    baseline: ModeReport,
    gate: SelectionGate,
) -> PromotionDecision:
    reasons: list[str] = []
    baseline_mae = baseline.metrics.mae
    if baseline_mae <= _EPSILON:
        relative = 0.0 if candidate.metrics.mae <= _EPSILON else -math.inf
    else:
        relative = (baseline_mae - candidate.metrics.mae) / baseline_mae

    if candidate.mode is baseline.mode:
        reasons.append("baseline_already_best")
    if candidate.metrics.folds < gate.min_folds:
        reasons.append("insufficient_folds")
    if candidate.mode is not baseline.mode and relative < gate.min_relative_improvement:
        reasons.append("insufficient_mae_improvement")

    baseline_worst = max(baseline.metrics.worst_absolute_error, _EPSILON)
    relative_worst = candidate.metrics.worst_absolute_error / baseline_worst
    if relative_worst > gate.max_relative_worst_error:
        reasons.append("worst_error_regression")

    if gate.require_regime_coverage:
        baseline_regimes = {regime for regime, _ in baseline.regime_metrics}
        candidate_regimes = {regime for regime, _ in candidate.regime_metrics}
        if candidate_regimes != baseline_regimes:
            reasons.append("incomplete_regime_coverage")

    accepted = candidate.mode is not baseline.mode and not reasons
    if accepted:
        reasons.append("historical_gate_passed")
    return PromotionDecision(
        candidate=candidate.mode,
        baseline=baseline.mode,
        accepted=accepted,
        reasons=tuple(reasons),
        relative_mae_improvement=relative,
        candidate_metrics=candidate.metrics,
        baseline_metrics=baseline.metrics,
    )


def _report_by_mode(reports: Sequence[ModeReport], mode: HistoricalMode) -> ModeReport:
    for report in reports:
        if report.mode is mode:
            return report
    raise HistoricalModeError(
        "required baseline mode was not evaluated",
        context={"reason": "missing_baseline", "mode": mode.value},
    )


def _report_fingerprint(
    series: HistoricalSeries,
    config: WalkForwardConfig,
    reports: Sequence[ModeReport],
    ranking: Sequence[HistoricalMode],
    promotion: PromotionDecision,
) -> str:
    """Small stable FNV-1a digest; no crypto/security semantics are implied."""

    parts = [
        series.label,
        ",".join(format(value, ".17g") for value in series.values),
        repr(config),
        ",".join(mode.value for mode in ranking),
        promotion.candidate.value,
        str(promotion.accepted),
    ]
    for report in reports:
        parts.extend(
            [
                report.mode.value,
                format(report.metrics.mae, ".17g"),
                format(report.metrics.rmse, ".17g"),
                format(report.metrics.bias, ".17g"),
                str(report.metrics.folds),
            ]
        )
    data = "|".join(parts).encode("utf-8")
    digest = 1469598103934665603
    for byte in data:
        digest ^= byte
        digest = (digest * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{digest:016x}"


def _linear_fit(values: Sequence[float]) -> tuple[float, float]:
    count = len(values)
    if count == 1:
        return values[0], 0.0
    mean_x = (count - 1) / 2.0
    mean_y = statistics.fmean(values)
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    if denominator <= _EPSILON:
        return mean_y, 0.0
    slope = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values)) / denominator
    intercept = mean_y - slope * mean_x
    return intercept, slope


def _ar1_forecast(values: Sequence[float], horizon: int) -> tuple[float, dict[str, float | int | str]]:
    if len(values) < 3:
        return values[-1], {"fallback": "persistence"}
    x = values[:-1]
    y = values[1:]
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    denominator = sum((value - mean_x) ** 2 for value in x)
    if denominator <= _EPSILON:
        return mean_y, {"fallback": "mean"}
    phi = sum((left - mean_x) * (right - mean_y) for left, right in zip(x, y)) / denominator
    phi = max(-1.25, min(1.25, phi))
    intercept = mean_y - phi * mean_x
    estimate = values[-1]
    for _ in range(horizon):
        estimate = intercept + phi * estimate
    return estimate, {"phi": phi, "intercept": intercept}


def _lag1_autocorrelation(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = statistics.fmean(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator <= _EPSILON:
        return 0.0
    numerator = sum((left - mean) * (right - mean) for left, right in zip(values, values[1:]))
    return max(-1.0, min(1.0, numerator / denominator))


def _sign(value: float) -> int:
    if value > _EPSILON:
        return 1
    if value < -_EPSILON:
        return -1
    return 0


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalModeError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise HistoricalModeError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalModeError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_number", "field": name},
        )
    return value


def _unit_interval(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalModeError(
            f"{name} must be between 0 and 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _open_unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 < number <= 1.0:
        raise HistoricalModeError(
            f"{name} must be greater than 0 and at most 1",
            context={"reason": "out_of_range", "field": name},
        )
    return number


__all__ = [
    "BASE_MODES",
    "EvaluationReport",
    "FoldResult",
    "Forecast",
    "HistoricalMode",
    "HistoricalModeError",
    "HistoricalModeLab",
    "HistoricalSeries",
    "ModeMetrics",
    "ModeReport",
    "PromotionDecision",
    "Regime",
    "RegimeProfile",
    "SelectionGate",
    "WalkForwardConfig",
    "classify_regime",
]
