"""Paired out-of-sample model arena for Jeeves probabilistic forecasters.

Complexity must earn its place. This module compares the adaptive structural
Bayesian ensemble against the hidden-Markov regime model on *identical* forward
targets. The primary comparison uses proper log score and a Newey-West/HAC
standard error so serial correlation in forecast-score differences is not silently
ignored.

The result is an evidence object, not an activation command.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .probabilistic_ensemble import BayesianEnsembleConfig, OnlineBayesianEnsemble
from .probabilistic_regimes import RegimeHMMConfig, RegimeForecast, fit_regime_hmm
from .probabilistic_state_space import SeriesValues, StateSpaceConfig, StateSpaceError

_EPSILON = 1e-15


class ArenaCandidate(str, Enum):
    STRUCTURAL_BAYES = "structural_bayes"
    REGIME_HMM = "regime_hmm"


@dataclass(frozen=True, slots=True)
class PredictiveArenaConfig:
    min_train_size: int = 24
    step: int = 1
    min_folds: int = 20
    min_log_score_gain: float = 0.01
    max_p_value: float = 0.10
    max_relative_mae_regression: float = 0.03
    hac_lags: int | None = None

    def __post_init__(self) -> None:
        for field, value, minimum in (
            ("min_train_size", self.min_train_size, 6),
            ("step", self.step, 1),
            ("min_folds", self.min_folds, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise StateSpaceError(
                    f"{field} must be an integer >= {minimum}",
                    context={"reason": "invalid_arena_config", "field": field},
                )
        _finite("min_log_score_gain", self.min_log_score_gain)
        _closed_interval("max_p_value", self.max_p_value, 0.0, 1.0)
        if _finite("max_relative_mae_regression", self.max_relative_mae_regression) < 0.0:
            raise StateSpaceError(
                "max_relative_mae_regression must be non-negative",
                context={"reason": "invalid_arena_config", "field": "max_relative_mae_regression"},
            )
        if self.hac_lags is not None:
            if isinstance(self.hac_lags, bool) or not isinstance(self.hac_lags, int) or self.hac_lags < 0:
                raise StateSpaceError(
                    "hac_lags must be a non-negative integer or None",
                    context={"reason": "invalid_arena_config", "field": "hac_lags"},
                )


@dataclass(frozen=True, slots=True)
class ArenaFold:
    target_index: int
    actual: float
    baseline_mean: float
    challenger_mean: float
    baseline_log_score: float
    challenger_log_score: float
    baseline_absolute_error: float
    challenger_absolute_error: float
    baseline_squared_error: float
    challenger_squared_error: float
    log_score_difference: float


@dataclass(frozen=True, slots=True)
class HACComparison:
    mean_difference: float
    standard_error: float
    z_score: float
    two_sided_p_value: float
    lags: int


@dataclass(frozen=True, slots=True)
class ArenaMetrics:
    candidate: ArenaCandidate
    folds: int
    mean_log_score: float
    mae: float
    rmse: float


@dataclass(frozen=True, slots=True)
class PredictiveArenaDecision:
    baseline: ArenaCandidate
    challenger: ArenaCandidate
    accepted: bool
    reasons: tuple[str, ...]
    log_score_gain: float
    relative_mae_change: float
    comparison: HACComparison


@dataclass(frozen=True, slots=True)
class PredictiveArenaReport:
    config: PredictiveArenaConfig
    baseline: ArenaMetrics
    challenger: ArenaMetrics
    folds: tuple[ArenaFold, ...]
    decision: PredictiveArenaDecision
    fingerprint: str

    @property
    def selected(self) -> ArenaCandidate:
        return self.decision.challenger if self.decision.accepted else self.decision.baseline


def evaluate_predictive_arena(
    series: SeriesValues | Sequence[float],
    *,
    config: PredictiveArenaConfig | None = None,
    ensemble_config: BayesianEnsembleConfig | None = None,
    state_space_config: StateSpaceConfig | None = None,
    hmm_config: RegimeHMMConfig | None = None,
) -> PredictiveArenaReport:
    """Compare adaptive structural Bayes and HMM forecasts on common targets."""

    actual_config = config or PredictiveArenaConfig()
    values = _coerce_values(series)
    if len(values) <= actual_config.min_train_size:
        raise StateSpaceError(
            "series is too short for predictive arena",
            context={"reason": "insufficient_history"},
        )

    base_ensemble_config = ensemble_config or BayesianEnsembleConfig(
        min_train_size=actual_config.min_train_size,
        step=actual_config.step,
    )
    if (
        base_ensemble_config.min_train_size != actual_config.min_train_size
        or base_ensemble_config.step != actual_config.step
    ):
        raise StateSpaceError(
            "ensemble and arena fold grids must match exactly",
            context={"reason": "fold_grid_mismatch"},
        )

    ensemble = OnlineBayesianEnsemble(
        config=base_ensemble_config,
        state_space_config=state_space_config,
    ).evaluate(values)
    baseline_steps = {step.target_index: step for step in ensemble.steps}

    actual_hmm_config = hmm_config or RegimeHMMConfig()
    folds: list[ArenaFold] = []
    for target_index in range(
        actual_config.min_train_size,
        len(values),
        actual_config.step,
    ):
        baseline_step = baseline_steps.get(target_index)
        if baseline_step is None:
            raise StateSpaceError(
                "structural ensemble omitted an arena target",
                context={"reason": "fold_grid_mismatch", "target_index": target_index},
            )
        hmm_fit = fit_regime_hmm(values[:target_index], config=actual_hmm_config)
        challenger_forecast = hmm_fit.forecast(1)
        actual = values[target_index]

        baseline_error = baseline_step.predictive.mean - actual
        challenger_error = challenger_forecast.mean - actual
        baseline_log = baseline_step.predictive.log_density(actual)
        challenger_log = challenger_forecast.log_density(actual)
        folds.append(
            ArenaFold(
                target_index=target_index,
                actual=actual,
                baseline_mean=baseline_step.predictive.mean,
                challenger_mean=challenger_forecast.mean,
                baseline_log_score=baseline_log,
                challenger_log_score=challenger_log,
                baseline_absolute_error=abs(baseline_error),
                challenger_absolute_error=abs(challenger_error),
                baseline_squared_error=baseline_error * baseline_error,
                challenger_squared_error=challenger_error * challenger_error,
                log_score_difference=challenger_log - baseline_log,
            )
        )

    if not folds:
        raise StateSpaceError(
            "predictive arena produced no common folds",
            context={"reason": "no_folds"},
        )

    baseline_metrics = _metrics(ArenaCandidate.STRUCTURAL_BAYES, folds, challenger=False)
    challenger_metrics = _metrics(ArenaCandidate.REGIME_HMM, folds, challenger=True)
    differences = tuple(fold.log_score_difference for fold in folds)
    lags = actual_config.hac_lags
    if lags is None:
        lags = min(len(differences) - 1, max(0, int(round(len(differences) ** (1.0 / 3.0)))))
    comparison = newey_west_mean_test(differences, lags=lags)

    log_score_gain = challenger_metrics.mean_log_score - baseline_metrics.mean_log_score
    baseline_mae = max(_EPSILON, baseline_metrics.mae)
    relative_mae_change = (challenger_metrics.mae - baseline_metrics.mae) / baseline_mae
    reasons: list[str] = []
    if len(folds) < actual_config.min_folds:
        reasons.append("insufficient_common_folds")
    if log_score_gain < actual_config.min_log_score_gain:
        reasons.append("insufficient_log_score_gain")
    if comparison.two_sided_p_value > actual_config.max_p_value:
        reasons.append("log_score_gain_not_statistically_resolved")
    if relative_mae_change > actual_config.max_relative_mae_regression:
        reasons.append("mae_regression_above_gate")

    accepted = not reasons
    if accepted:
        reasons.append("regime_complexity_earned")
    decision = PredictiveArenaDecision(
        baseline=ArenaCandidate.STRUCTURAL_BAYES,
        challenger=ArenaCandidate.REGIME_HMM,
        accepted=accepted,
        reasons=tuple(reasons),
        log_score_gain=log_score_gain,
        relative_mae_change=relative_mae_change,
        comparison=comparison,
    )
    fingerprint = _fingerprint(actual_config, folds, baseline_metrics, challenger_metrics, decision)
    return PredictiveArenaReport(
        config=actual_config,
        baseline=baseline_metrics,
        challenger=challenger_metrics,
        folds=tuple(folds),
        decision=decision,
        fingerprint=fingerprint,
    )


def newey_west_mean_test(differences: Sequence[float], *, lags: int) -> HACComparison:
    """HAC test for whether a paired score-difference mean differs from zero.

    Bartlett weights are used for autocovariances through ``lags``. The returned
    normal approximation is a diagnostic, not a proof of independence or model
    correctness.
    """

    values = tuple(_finite("difference", value) for value in differences)
    if len(values) < 2:
        raise StateSpaceError(
            "HAC comparison requires at least two paired differences",
            context={"reason": "insufficient_hac_samples"},
        )
    if isinstance(lags, bool) or not isinstance(lags, int) or not 0 <= lags < len(values):
        raise StateSpaceError(
            "lags must be between zero and sample_count - 1",
            context={"reason": "invalid_hac_lags"},
        )

    mean = statistics.fmean(values)
    centered = tuple(value - mean for value in values)
    count = len(values)
    long_run_variance = sum(value * value for value in centered) / count
    for lag in range(1, lags + 1):
        covariance = sum(
            centered[index] * centered[index - lag]
            for index in range(lag, count)
        ) / count
        bartlett_weight = 1.0 - lag / (lags + 1.0)
        long_run_variance += 2.0 * bartlett_weight * covariance

    long_run_variance = max(0.0, long_run_variance)
    standard_error = math.sqrt(long_run_variance / count)
    if standard_error <= _EPSILON:
        if abs(mean) <= _EPSILON:
            z_score = 0.0
            p_value = 1.0
        else:
            z_score = math.copysign(math.inf, mean)
            p_value = 0.0
    else:
        z_score = mean / standard_error
        p_value = math.erfc(abs(z_score) / math.sqrt(2.0))

    return HACComparison(
        mean_difference=mean,
        standard_error=standard_error,
        z_score=z_score,
        two_sided_p_value=min(1.0, max(0.0, p_value)),
        lags=lags,
    )


def regime_forecast_crps(forecast: RegimeForecast, actual: float) -> float:
    """Exact one-step CRPS for an HMM's Gaussian state mixture."""

    actual = _finite("actual", actual)
    if forecast.horizon != 1 or not forecast.components:
        raise StateSpaceError(
            "exact regime CRPS is available for one-step mixture forecasts only",
            context={"reason": "unsupported_regime_crps_horizon"},
        )
    first = sum(
        component.probability
        * _expected_abs_normal(actual - component.mean_level, component.variance_level)
        for component in forecast.components
    )
    second = 0.0
    for left in forecast.components:
        for right in forecast.components:
            second += (
                left.probability
                * right.probability
                * _expected_abs_normal(
                    left.mean_level - right.mean_level,
                    left.variance_level + right.variance_level,
                )
            )
    return max(0.0, first - 0.5 * second)


def _metrics(candidate: ArenaCandidate, folds: Sequence[ArenaFold], *, challenger: bool) -> ArenaMetrics:
    if challenger:
        logs = [fold.challenger_log_score for fold in folds]
        absolute = [fold.challenger_absolute_error for fold in folds]
        squared = [fold.challenger_squared_error for fold in folds]
    else:
        logs = [fold.baseline_log_score for fold in folds]
        absolute = [fold.baseline_absolute_error for fold in folds]
        squared = [fold.baseline_squared_error for fold in folds]
    return ArenaMetrics(
        candidate=candidate,
        folds=len(folds),
        mean_log_score=statistics.fmean(logs),
        mae=statistics.fmean(absolute),
        rmse=math.sqrt(statistics.fmean(squared)),
    )


def _expected_abs_normal(delta: float, variance: float) -> float:
    variance = max(_EPSILON, variance)
    sigma = math.sqrt(variance)
    z = delta / sigma
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return 2.0 * sigma * phi + delta * (2.0 * cdf - 1.0)


def _fingerprint(
    config: PredictiveArenaConfig,
    folds: Sequence[ArenaFold],
    baseline: ArenaMetrics,
    challenger: ArenaMetrics,
    decision: PredictiveArenaDecision,
) -> str:
    parts = [
        "jeeves-predictive-arena-v1",
        repr(config),
        repr(baseline),
        repr(challenger),
        repr(decision),
    ]
    for fold in folds:
        parts.extend(
            (
                str(fold.target_index),
                format(fold.actual, ".17g"),
                format(fold.baseline_mean, ".17g"),
                format(fold.challenger_mean, ".17g"),
                format(fold.baseline_log_score, ".17g"),
                format(fold.challenger_log_score, ".17g"),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError("arena series must be numeric", context={"reason": "invalid_series"})
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError("arena series must be iterable", context={"reason": "invalid_series"}) from exc
    if not values:
        raise StateSpaceError("arena series cannot be empty", context={"reason": "empty_series"})
    return tuple(_finite("value", value) for value in values)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum <= number <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_arena_config", "field": name},
        )
    return number


__all__ = [
    "ArenaCandidate",
    "ArenaFold",
    "ArenaMetrics",
    "HACComparison",
    "PredictiveArenaConfig",
    "PredictiveArenaDecision",
    "PredictiveArenaReport",
    "evaluate_predictive_arena",
    "newey_west_mean_test",
    "regime_forecast_crps",
]
