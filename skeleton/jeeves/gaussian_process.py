"""Nonparametric Gaussian-process forecasting for Jeeves.

The implementation is dependency-light and deterministic: a linear mean
function captures global drift while a positive-semidefinite kernel portfolio
models residual structure. Training uses Cholesky factorisation, exact Gaussian
log marginal likelihood, and bounded history. Evaluation is walk-forward and
never admits target values into a training prefix.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from .historical_modes import HistoricalModeError, HistoricalSeries
from .probabilistic_state_space import GaussianForecast, persistence_distribution

_EPS = 1e-12
_LOG_2PI = math.log(2.0 * math.pi)


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


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise HistoricalModeError(
            f"{name} must be positive",
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


class KernelKind(str, Enum):
    RBF = "rbf"
    MATERN32 = "matern32"
    RATIONAL_QUADRATIC = "rational_quadratic"
    PERIODIC = "periodic"


@dataclass(frozen=True, slots=True)
class KernelSpec:
    kind: KernelKind
    amplitude: float = 1.0
    length_scale: float = 8.0
    alpha: float = 1.0
    period: float = 7.0
    weight: float = 1.0

    def __post_init__(self) -> None:
        _positive("amplitude", self.amplitude)
        _positive("length_scale", self.length_scale)
        _positive("alpha", self.alpha)
        _positive("period", self.period)
        _positive("weight", self.weight)

    def covariance(self, left: float, right: float) -> float:
        distance = abs(_finite("left", left) - _finite("right", right))
        amplitude2 = self.amplitude * self.amplitude
        if self.kind is KernelKind.RBF:
            ratio = distance / self.length_scale
            value = amplitude2 * math.exp(-0.5 * ratio * ratio)
        elif self.kind is KernelKind.MATERN32:
            ratio = math.sqrt(3.0) * distance / self.length_scale
            value = amplitude2 * (1.0 + ratio) * math.exp(-ratio)
        elif self.kind is KernelKind.RATIONAL_QUADRATIC:
            ratio2 = distance * distance / (
                2.0 * self.alpha * self.length_scale * self.length_scale
            )
            value = amplitude2 * (1.0 + ratio2) ** (-self.alpha)
        elif self.kind is KernelKind.PERIODIC:
            sine = math.sin(math.pi * distance / self.period)
            value = amplitude2 * math.exp(
                -2.0 * sine * sine / (self.length_scale * self.length_scale)
            )
        else:
            raise HistoricalModeError(
                "unsupported Gaussian-process kernel",
                context={"reason": "unsupported_kernel", "kernel": str(self.kind)},
            )
        return self.weight * value


@dataclass(frozen=True, slots=True)
class GaussianProcessConfig:
    kernels: tuple[KernelSpec, ...] = ()
    observation_variance: float = 0.05
    jitter: float = 1e-8
    max_jitter: float = 1e-2
    max_train_points: int = 160
    include_observation_noise: bool = True

    def __post_init__(self) -> None:
        if not self.kernels:
            object.__setattr__(self, "kernels", default_kernel_portfolio())
        if len(self.kernels) > 16:
            raise HistoricalModeError(
                "too many Gaussian-process kernels",
                context={"reason": "kernel_budget_exceeded"},
            )
        _positive("observation_variance", self.observation_variance)
        _positive("jitter", self.jitter)
        _positive("max_jitter", self.max_jitter)
        _positive_int("max_train_points", self.max_train_points)
        if self.jitter > self.max_jitter:
            raise HistoricalModeError(
                "jitter cannot exceed max_jitter",
                context={"reason": "invalid_gp_config"},
            )


@dataclass(frozen=True, slots=True)
class GaussianProcessSnapshot:
    observations: int
    retained_observations: int
    trend_intercept: float
    trend_slope: float
    log_marginal_likelihood: float
    effective_jitter: float
    residual_scale: float


class GaussianProcessForecaster:
    """Exact scalar GP over a bounded trailing history."""

    def __init__(
        self,
        x: Sequence[float],
        y: Sequence[float],
        *,
        config: GaussianProcessConfig | None = None,
    ) -> None:
        self.config = config or GaussianProcessConfig()
        if len(x) != len(y) or not x:
            raise HistoricalModeError(
                "Gaussian-process x and y must be non-empty and equal length",
                context={"reason": "invalid_gp_training_data"},
            )
        clean_x = tuple(_finite("x", value) for value in x)
        clean_y = tuple(_finite("y", value) for value in y)
        if any(right <= left for left, right in zip(clean_x, clean_x[1:])):
            raise HistoricalModeError(
                "Gaussian-process x values must be strictly increasing",
                context={"reason": "non_monotonic_time"},
            )
        self.original_observations = len(clean_x)
        if len(clean_x) > self.config.max_train_points:
            clean_x = clean_x[-self.config.max_train_points :]
            clean_y = clean_y[-self.config.max_train_points :]
        self.x = clean_x
        self.y = clean_y
        self.trend_intercept, self.trend_slope = _linear_mean_fit(clean_x, clean_y)
        residuals = tuple(
            value - self.mean_function(point) for point, value in zip(clean_x, clean_y)
        )
        self.residual_scale = _robust_scale(residuals)
        self._scaled_kernels = tuple(
            KernelSpec(
                spec.kind,
                amplitude=max(spec.amplitude * self.residual_scale, 1e-6),
                length_scale=spec.length_scale,
                alpha=spec.alpha,
                period=spec.period,
                weight=spec.weight,
            )
            for spec in self.config.kernels
        )
        matrix = self._training_covariance()
        self._chol, self.effective_jitter = _stable_cholesky(
            matrix,
            initial_jitter=self.config.jitter,
            max_jitter=self.config.max_jitter,
        )
        self._alpha = _cholesky_solve(self._chol, residuals)
        quadratic = sum(value * coefficient for value, coefficient in zip(residuals, self._alpha))
        log_det_half = sum(math.log(self._chol[index][index]) for index in range(len(self._chol)))
        self.log_marginal_likelihood = (
            -0.5 * quadratic
            - log_det_half
            - 0.5 * len(residuals) * _LOG_2PI
        )

    @classmethod
    def fit_series(
        cls,
        series: HistoricalSeries,
        *,
        config: GaussianProcessConfig | None = None,
    ) -> "GaussianProcessForecaster":
        x = (
            tuple(float(index) for index in range(len(series.values)))
            if series.timestamps is None
            else series.timestamps
        )
        return cls(x, series.values, config=config)

    def mean_function(self, x: float) -> float:
        point = _finite("x", x)
        return self.trend_intercept + self.trend_slope * point

    def covariance(self, left: float, right: float) -> float:
        return sum(spec.covariance(left, right) for spec in self._scaled_kernels)

    def _training_covariance(self) -> list[list[float]]:
        size = len(self.x)
        matrix = [[0.0] * size for _ in range(size)]
        for row in range(size):
            for column in range(row + 1):
                value = self.covariance(self.x[row], self.x[column])
                if row == column:
                    value += self.config.observation_variance
                matrix[row][column] = value
                matrix[column][row] = value
        return matrix

    def predict_at(self, x_future: float, *, horizon: int = 1) -> GaussianForecast:
        point = _finite("x_future", x_future)
        _positive_int("horizon", horizon)
        cross = [self.covariance(point, train_x) for train_x in self.x]
        residual_mean = sum(weight * coefficient for weight, coefficient in zip(cross, self._alpha))
        mean = self.mean_function(point) + residual_mean
        solved = _forward_substitute(self._chol, cross)
        latent_variance = self.covariance(point, point) - sum(value * value for value in solved)
        variance = max(_EPS, latent_variance)
        if self.config.include_observation_noise:
            variance += self.config.observation_variance
        return GaussianForecast(
            mean=mean,
            variance=max(_EPS, variance),
            horizon=horizon,
            model="gaussian_process",
        )

    def forecast(self, horizon: int = 1) -> GaussianForecast:
        _positive_int("horizon", horizon)
        step = _median_step(self.x)
        point = self.x[-1] + horizon * step
        return self.predict_at(point, horizon=horizon)

    def snapshot(self) -> GaussianProcessSnapshot:
        return GaussianProcessSnapshot(
            observations=self.original_observations,
            retained_observations=len(self.x),
            trend_intercept=self.trend_intercept,
            trend_slope=self.trend_slope,
            log_marginal_likelihood=self.log_marginal_likelihood,
            effective_jitter=self.effective_jitter,
            residual_scale=self.residual_scale,
        )


@dataclass(frozen=True, slots=True)
class KernelPortfolioCandidate:
    name: str
    kernels: tuple[KernelSpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or not self.kernels:
            raise HistoricalModeError(
                "kernel portfolio must have a name and kernels",
                context={"reason": "invalid_kernel_portfolio"},
            )


@dataclass(frozen=True, slots=True)
class KernelSelection:
    name: str
    log_marginal_likelihood: float
    complexity_penalty: float
    selection_score: float


@dataclass(frozen=True, slots=True)
class SelectedGaussianProcess:
    model: GaussianProcessForecaster
    selected_name: str
    ranking: tuple[KernelSelection, ...]


class GaussianProcessSelector:
    """Select a kernel portfolio only from a supplied training prefix."""

    def __init__(
        self,
        *,
        candidates: Sequence[KernelPortfolioCandidate] | None = None,
        base_config: GaussianProcessConfig | None = None,
    ) -> None:
        self.candidates = tuple(candidates or default_kernel_candidates())
        if len(self.candidates) < 2 or len({item.name for item in self.candidates}) != len(self.candidates):
            raise HistoricalModeError(
                "GP selector requires uniquely named candidate portfolios",
                context={"reason": "invalid_kernel_candidates"},
            )
        self.base_config = base_config or GaussianProcessConfig()

    def fit_series(self, series: HistoricalSeries) -> SelectedGaussianProcess:
        x = (
            tuple(float(index) for index in range(len(series.values)))
            if series.timestamps is None
            else series.timestamps
        )
        fitted: list[tuple[KernelSelection, GaussianProcessForecaster]] = []
        for candidate in self.candidates:
            config = GaussianProcessConfig(
                kernels=candidate.kernels,
                observation_variance=self.base_config.observation_variance,
                jitter=self.base_config.jitter,
                max_jitter=self.base_config.max_jitter,
                max_train_points=self.base_config.max_train_points,
                include_observation_noise=self.base_config.include_observation_noise,
            )
            model = GaussianProcessForecaster(x, series.values, config=config)
            parameter_count = 2 + 4 * len(candidate.kernels)
            penalty = 0.5 * parameter_count * math.log(max(2, len(model.x)))
            score = model.log_marginal_likelihood - penalty
            fitted.append(
                (
                    KernelSelection(
                        candidate.name,
                        model.log_marginal_likelihood,
                        penalty,
                        score,
                    ),
                    model,
                )
            )
        fitted.sort(key=lambda item: (-item[0].selection_score, item[0].name))
        return SelectedGaussianProcess(
            model=fitted[0][1],
            selected_name=fitted[0][0].name,
            ranking=tuple(item[0] for item in fitted),
        )


@dataclass(frozen=True, slots=True)
class GaussianProcessEvaluationConfig:
    min_train_size: int = 24
    horizon: int = 1
    step: int = 1
    min_folds: int = 8
    min_relative_crps_improvement: float = 0.01
    max_relative_nll_regression: float = 0.10

    def __post_init__(self) -> None:
        for field in ("min_train_size", "horizon", "step", "min_folds"):
            _positive_int(field, getattr(self, field))
        improvement = _finite("min_relative_crps_improvement", self.min_relative_crps_improvement)
        if not 0.0 <= improvement <= 1.0:
            raise HistoricalModeError(
                "min_relative_crps_improvement must be between zero and one",
                context={"reason": "invalid_gp_evaluation_config"},
            )
        if _finite("max_relative_nll_regression", self.max_relative_nll_regression) < 0.0:
            raise HistoricalModeError(
                "max_relative_nll_regression cannot be negative",
                context={"reason": "invalid_gp_evaluation_config"},
            )


@dataclass(frozen=True, slots=True)
class GaussianProcessFold:
    train_end: int
    target_index: int
    actual: float
    predicted_mean: float
    predicted_variance: float
    crps: float
    nll: float
    baseline_crps: float
    baseline_nll: float
    selected_portfolio: str
    log_marginal_likelihood: float


@dataclass(frozen=True, slots=True)
class GaussianProcessMetrics:
    folds: int
    mae: float
    rmse: float
    mean_crps: float
    mean_nll: float
    mean_predictive_std: float


@dataclass(frozen=True, slots=True)
class GaussianProcessDecision:
    accepted: bool
    reasons: tuple[str, ...]
    relative_crps_improvement: float
    relative_nll_change: float


@dataclass(frozen=True, slots=True)
class GaussianProcessEvaluationReport:
    series_label: str
    config: GaussianProcessEvaluationConfig
    folds: tuple[GaussianProcessFold, ...]
    candidate: GaussianProcessMetrics
    baseline: GaussianProcessMetrics
    decision: GaussianProcessDecision
    fingerprint: str

    def as_payload(self) -> dict[str, object]:
        return {
            "series_label": self.series_label,
            "folds": self.candidate.folds,
            "promotion_accepted": self.decision.accepted,
            "candidate_crps": self.candidate.mean_crps,
            "baseline_crps": self.baseline.mean_crps,
            "candidate_nll": self.candidate.mean_nll,
            "baseline_nll": self.baseline.mean_nll,
            "fingerprint": self.fingerprint,
        }


def evaluate_gaussian_process(
    series: HistoricalSeries,
    *,
    config: GaussianProcessEvaluationConfig | None = None,
    selector: GaussianProcessSelector | None = None,
) -> GaussianProcessEvaluationReport:
    actual_config = config or GaussianProcessEvaluationConfig()
    actual_selector = selector or GaussianProcessSelector()
    values = series.values
    if len(values) < actual_config.min_train_size + actual_config.horizon:
        raise HistoricalModeError(
            "series is too short for GP evaluation",
            context={"reason": "insufficient_history"},
        )
    full_x = (
        tuple(float(index) for index in range(len(values)))
        if series.timestamps is None
        else series.timestamps
    )
    folds: list[GaussianProcessFold] = []
    for train_end in range(
        actual_config.min_train_size - 1,
        len(values) - actual_config.horizon,
        actual_config.step,
    ):
        target_index = train_end + actual_config.horizon
        prefix = HistoricalSeries(
            values=values[: train_end + 1],
            timestamps=None if series.timestamps is None else series.timestamps[: train_end + 1],
            label=series.label,
        )
        selected = actual_selector.fit_series(prefix)
        forecast = selected.model.predict_at(full_x[target_index], horizon=actual_config.horizon)
        baseline = persistence_distribution(prefix.values, actual_config.horizon)
        actual = values[target_index]
        folds.append(
            GaussianProcessFold(
                train_end=train_end,
                target_index=target_index,
                actual=actual,
                predicted_mean=forecast.mean,
                predicted_variance=forecast.variance,
                crps=forecast.crps(actual),
                nll=forecast.nll(actual),
                baseline_crps=baseline.crps(actual),
                baseline_nll=baseline.nll(actual),
                selected_portfolio=selected.selected_name,
                log_marginal_likelihood=selected.model.log_marginal_likelihood,
            )
        )
    candidate = _aggregate_gp(folds, candidate=True)
    baseline_metrics = _aggregate_gp(folds, candidate=False)
    decision = _gp_decision(candidate, baseline_metrics, actual_config)
    fingerprint = _gp_fingerprint(series, actual_config, folds, decision)
    return GaussianProcessEvaluationReport(
        series.label,
        actual_config,
        tuple(folds),
        candidate,
        baseline_metrics,
        decision,
        fingerprint,
    )


def default_kernel_portfolio() -> tuple[KernelSpec, ...]:
    return (
        KernelSpec(KernelKind.MATERN32, amplitude=1.0, length_scale=8.0, weight=0.55),
        KernelSpec(KernelKind.RATIONAL_QUADRATIC, amplitude=1.0, length_scale=16.0, alpha=1.0, weight=0.30),
        KernelSpec(KernelKind.PERIODIC, amplitude=0.7, length_scale=1.2, period=7.0, weight=0.15),
    )


def default_kernel_candidates() -> tuple[KernelPortfolioCandidate, ...]:
    return (
        KernelPortfolioCandidate(
            "smooth",
            (
                KernelSpec(KernelKind.RBF, amplitude=1.0, length_scale=10.0, weight=0.7),
                KernelSpec(KernelKind.RATIONAL_QUADRATIC, amplitude=0.7, length_scale=20.0, alpha=1.0, weight=0.3),
            ),
        ),
        KernelPortfolioCandidate(
            "rough",
            (
                KernelSpec(KernelKind.MATERN32, amplitude=1.0, length_scale=5.0, weight=0.75),
                KernelSpec(KernelKind.RATIONAL_QUADRATIC, amplitude=0.7, length_scale=12.0, alpha=0.7, weight=0.25),
            ),
        ),
        KernelPortfolioCandidate(
            "seasonal",
            (
                KernelSpec(KernelKind.MATERN32, amplitude=0.8, length_scale=8.0, weight=0.45),
                KernelSpec(KernelKind.PERIODIC, amplitude=1.0, length_scale=1.0, period=7.0, weight=0.55),
            ),
        ),
    )


def _linear_mean_fit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    if len(x) == 1:
        return y[0], 0.0
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    denominator = sum((point - mean_x) ** 2 for point in x)
    if denominator <= _EPS:
        return mean_y, 0.0
    slope = sum((point - mean_x) * (value - mean_y) for point, value in zip(x, y)) / denominator
    return mean_y - slope * mean_x, slope


def _robust_scale(values: Sequence[float]) -> float:
    if not values:
        return 1.0
    center = float(statistics.median(values))
    mad = float(statistics.median(abs(value - center) for value in values))
    scale = 1.4826 * mad
    if scale <= 1e-6:
        scale = statistics.pstdev(values) if len(values) > 1 else abs(values[0])
    return max(scale, 1e-3)


def _median_step(x: Sequence[float]) -> float:
    if len(x) < 2:
        return 1.0
    return float(statistics.median(right - left for left, right in zip(x, x[1:])))


def _stable_cholesky(
    matrix: Sequence[Sequence[float]],
    *,
    initial_jitter: float,
    max_jitter: float,
) -> tuple[list[list[float]], float]:
    jitter = initial_jitter
    while jitter <= max_jitter * (1.0 + 1e-12):
        try:
            return _cholesky(matrix, jitter), jitter
        except ArithmeticError:
            jitter *= 10.0
    raise HistoricalModeError(
        "Gaussian-process covariance is not numerically positive definite",
        context={"reason": "gp_cholesky_failed", "max_jitter": max_jitter},
    )


def _cholesky(matrix: Sequence[Sequence[float]], jitter: float) -> list[list[float]]:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ArithmeticError("matrix must be square")
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            value = float(matrix[row][column])
            if row == column:
                value += jitter
            value -= sum(lower[row][k] * lower[column][k] for k in range(column))
            if row == column:
                if value <= 0.0 or not math.isfinite(value):
                    raise ArithmeticError("matrix is not positive definite")
                lower[row][column] = math.sqrt(value)
            else:
                pivot = lower[column][column]
                if pivot <= 0.0:
                    raise ArithmeticError("zero pivot")
                lower[row][column] = value / pivot
    return lower


def _forward_substitute(lower: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    size = len(lower)
    if len(vector) != size:
        raise HistoricalModeError(
            "triangular solve dimension mismatch",
            context={"reason": "gp_dimension_mismatch"},
        )
    result = [0.0] * size
    for row in range(size):
        remainder = vector[row] - sum(lower[row][column] * result[column] for column in range(row))
        result[row] = remainder / lower[row][row]
    return result


def _back_substitute_from_lower_transpose(
    lower: Sequence[Sequence[float]], vector: Sequence[float]
) -> list[float]:
    size = len(lower)
    result = [0.0] * size
    for row in range(size - 1, -1, -1):
        remainder = vector[row] - sum(lower[column][row] * result[column] for column in range(row + 1, size))
        result[row] = remainder / lower[row][row]
    return result


def _cholesky_solve(lower: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    return _back_substitute_from_lower_transpose(lower, _forward_substitute(lower, vector))


def _aggregate_gp(folds: Sequence[GaussianProcessFold], *, candidate: bool) -> GaussianProcessMetrics:
    if not folds:
        raise HistoricalModeError(
            "cannot aggregate zero GP folds",
            context={"reason": "no_folds"},
        )
    if candidate:
        errors = [fold.predicted_mean - fold.actual for fold in folds]
        crps = [fold.crps for fold in folds]
        nll = [fold.nll for fold in folds]
        std = [math.sqrt(fold.predicted_variance) for fold in folds]
    else:
        errors = [fold.predicted_mean - fold.actual for fold in folds]
        crps = [fold.baseline_crps for fold in folds]
        nll = [fold.baseline_nll for fold in folds]
        # Baseline dispersion is not retained per fold; score comparison is primary.
        std = [0.0 for _ in folds]
    return GaussianProcessMetrics(
        folds=len(folds),
        mae=statistics.fmean(abs(error) for error in errors),
        rmse=math.sqrt(statistics.fmean(error * error for error in errors)),
        mean_crps=statistics.fmean(crps),
        mean_nll=statistics.fmean(nll),
        mean_predictive_std=statistics.fmean(std),
    )


def _gp_decision(
    candidate: GaussianProcessMetrics,
    baseline: GaussianProcessMetrics,
    config: GaussianProcessEvaluationConfig,
) -> GaussianProcessDecision:
    reasons: list[str] = []
    if candidate.folds < config.min_folds:
        reasons.append("insufficient_folds")
    if baseline.mean_crps <= _EPS:
        relative_crps = 0.0 if candidate.mean_crps <= _EPS else -math.inf
    else:
        relative_crps = (baseline.mean_crps - candidate.mean_crps) / baseline.mean_crps
    if relative_crps < config.min_relative_crps_improvement:
        reasons.append("insufficient_crps_improvement")
    scale = max(1.0, abs(baseline.mean_nll))
    relative_nll = (candidate.mean_nll - baseline.mean_nll) / scale
    if relative_nll > config.max_relative_nll_regression:
        reasons.append("nll_regression")
    accepted = not reasons
    if accepted:
        reasons.append("gaussian_process_gate_passed")
    return GaussianProcessDecision(accepted, tuple(reasons), relative_crps, relative_nll)


def _gp_fingerprint(
    series: HistoricalSeries,
    config: GaussianProcessEvaluationConfig,
    folds: Sequence[GaussianProcessFold],
    decision: GaussianProcessDecision,
) -> str:
    parts = [
        "jeeves-gp-v1",
        series.label,
        ",".join(format(value, ".17g") for value in series.values),
        repr(config),
        str(decision.accepted),
        ",".join(decision.reasons),
    ]
    for fold in folds:
        parts.extend(
            (
                str(fold.train_end),
                str(fold.target_index),
                format(fold.predicted_mean, ".17g"),
                format(fold.predicted_variance, ".17g"),
                fold.selected_portfolio,
                format(fold.log_marginal_likelihood, ".17g"),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "GaussianProcessConfig",
    "GaussianProcessDecision",
    "GaussianProcessEvaluationConfig",
    "GaussianProcessEvaluationReport",
    "GaussianProcessFold",
    "GaussianProcessForecaster",
    "GaussianProcessMetrics",
    "GaussianProcessSelector",
    "GaussianProcessSnapshot",
    "KernelKind",
    "KernelPortfolioCandidate",
    "KernelSelection",
    "KernelSpec",
    "SelectedGaussianProcess",
    "default_kernel_candidates",
    "default_kernel_portfolio",
    "evaluate_gaussian_process",
]
