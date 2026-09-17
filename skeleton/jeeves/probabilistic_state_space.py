"""Probabilistic state-space forecasting for Jeeves.

Robust local-linear-trend Kalman filters, Bayesian regime mixtures, exact
Gaussian-mixture scoring, calibrated intervals, and leakage-safe walk-forward
evaluation. Offline only: no provider calls, fetching, execution, or learning
mutation.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass, replace
from statistics import NormalDist
from typing import Iterable, Sequence

from .historical_modes import HistoricalModeError, HistoricalSeries

_EPS = 1e-12
_LOG_2PI = math.log(2.0 * math.pi)
_NORMAL = NormalDist()


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


def _probability(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 < number < 1.0:
        raise HistoricalModeError(
            f"{name} must be strictly between 0 and 1",
            context={"reason": "invalid_probability", "field": name},
        )
    return number


def _bounded_variance(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value):
        return maximum
    return min(maximum, max(minimum, value))


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise HistoricalModeError(
            "logsumexp requires values",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    if maximum == -math.inf:
        return maximum
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


@dataclass(frozen=True, slots=True)
class StateSpaceConfig:
    observation_variance: float = 1.0
    level_process_variance: float = 0.05
    trend_process_variance: float = 0.01
    initial_level_variance: float = 10.0
    initial_trend_variance: float = 10.0
    robust_clip_sigma: float = 4.0
    adaptive_rate: float = 0.03
    minimum_variance: float = 1e-8
    maximum_variance: float = 1e12

    def __post_init__(self) -> None:
        for field in (
            "observation_variance",
            "level_process_variance",
            "trend_process_variance",
            "initial_level_variance",
            "initial_trend_variance",
            "minimum_variance",
            "maximum_variance",
        ):
            _positive(field, getattr(self, field))
        if self.minimum_variance >= self.maximum_variance:
            raise HistoricalModeError(
                "minimum variance must be below maximum variance",
                context={"reason": "invalid_state_space_config"},
            )
        if not math.isfinite(self.robust_clip_sigma) or self.robust_clip_sigma < 1.0:
            raise HistoricalModeError(
                "robust_clip_sigma must be finite and at least one",
                context={"reason": "invalid_state_space_config"},
            )
        if not math.isfinite(self.adaptive_rate) or not 0.0 <= self.adaptive_rate <= 1.0:
            raise HistoricalModeError(
                "adaptive_rate must be between zero and one",
                context={"reason": "invalid_state_space_config"},
            )


@dataclass(frozen=True, slots=True)
class GaussianForecast:
    mean: float
    variance: float
    horizon: int
    model: str

    def __post_init__(self) -> None:
        _finite("mean", self.mean)
        _positive("variance", self.variance)
        _positive_int("horizon", self.horizon)
        if not isinstance(self.model, str) or not self.model.strip():
            raise HistoricalModeError(
                "model must be non-empty",
                context={"reason": "invalid_forecast_model"},
            )

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(self.variance)

    def logpdf(self, value: float) -> float:
        actual = _finite("value", value)
        error = actual - self.mean
        return -0.5 * (_LOG_2PI + math.log(self.variance) + error * error / self.variance)

    def nll(self, value: float) -> float:
        return -self.logpdf(value)

    def cdf(self, value: float) -> float:
        z = (_finite("value", value) - self.mean) / self.standard_deviation
        return _NORMAL.cdf(z)

    def quantile(self, probability: float) -> float:
        p = _probability("probability", probability)
        return self.mean + self.standard_deviation * _NORMAL.inv_cdf(p)

    def interval(self, coverage: float) -> tuple[float, float]:
        level = _probability("coverage", coverage)
        tail = (1.0 - level) / 2.0
        return self.quantile(tail), self.quantile(1.0 - tail)

    def crps(self, value: float) -> float:
        return gaussian_crps(self.mean, self.standard_deviation, value)


@dataclass(frozen=True, slots=True)
class FilterSnapshot:
    observations: int
    level: float
    trend: float
    p00: float
    p01: float
    p10: float
    p11: float
    observation_variance: float
    level_process_variance: float
    trend_process_variance: float
    cumulative_log_likelihood: float
    clipped_updates: int


class LocalLinearTrendFilter:
    """Adaptive robust two-state Kalman filter for level and trend."""

    def __init__(self, first_value: float, *, config: StateSpaceConfig | None = None) -> None:
        self.config = config or StateSpaceConfig()
        self.level = _finite("first_value", first_value)
        self.trend = 0.0
        self.p00 = self.config.initial_level_variance
        self.p01 = 0.0
        self.p10 = 0.0
        self.p11 = self.config.initial_trend_variance
        self.observation_variance = self.config.observation_variance
        self.level_process_variance = self.config.level_process_variance
        self.trend_process_variance = self.config.trend_process_variance
        self.observations = 1
        self.cumulative_log_likelihood = 0.0
        self.clipped_updates = 0

    @classmethod
    def fit(
        cls,
        values: Iterable[float],
        *,
        config: StateSpaceConfig | None = None,
    ) -> "LocalLinearTrendFilter":
        clean = tuple(_finite("value", value) for value in values)
        if not clean:
            raise HistoricalModeError(
                "state-space fit requires observations",
                context={"reason": "empty_series"},
            )
        model = cls(clean[0], config=config)
        if len(clean) >= 2:
            model.trend = clean[1] - clean[0]
        for value in clean[1:]:
            model.update(value)
        return model

    def snapshot(self) -> FilterSnapshot:
        return FilterSnapshot(
            observations=self.observations,
            level=self.level,
            trend=self.trend,
            p00=self.p00,
            p01=self.p01,
            p10=self.p10,
            p11=self.p11,
            observation_variance=self.observation_variance,
            level_process_variance=self.level_process_variance,
            trend_process_variance=self.trend_process_variance,
            cumulative_log_likelihood=self.cumulative_log_likelihood,
            clipped_updates=self.clipped_updates,
        )

    def _project(self, horizon: int) -> tuple[float, float, float, float, float, float]:
        _positive_int("horizon", horizon)
        level, trend = self.level, self.trend
        p00, p01, p10, p11 = self.p00, self.p01, self.p10, self.p11
        for _ in range(horizon):
            level += trend
            next_p00 = p00 + p01 + p10 + p11 + self.level_process_variance
            next_p01 = p01 + p11
            next_p10 = p10 + p11
            next_p11 = p11 + self.trend_process_variance
            p00 = _bounded_variance(
                next_p00, self.config.minimum_variance, self.config.maximum_variance
            )
            p01, p10 = next_p01, next_p10
            p11 = _bounded_variance(
                next_p11, self.config.minimum_variance, self.config.maximum_variance
            )
        cross = 0.5 * (p01 + p10)
        return level, trend, p00, cross, cross, p11

    def forecast(self, horizon: int = 1) -> GaussianForecast:
        level, _, p00, _, _, _ = self._project(horizon)
        variance = _bounded_variance(
            p00 + self.observation_variance,
            self.config.minimum_variance,
            self.config.maximum_variance,
        )
        return GaussianForecast(level, variance, horizon, "local_linear_trend")

    def update(self, observation: float) -> GaussianForecast:
        actual = _finite("observation", observation)
        prior = self.forecast(1)
        level, trend, p00, p01, p10, p11 = self._project(1)
        innovation = actual - level
        innovation_scale = math.sqrt(max(prior.variance, self.config.minimum_variance))
        limit = self.config.robust_clip_sigma * innovation_scale
        clipped = max(-limit, min(limit, innovation))
        if abs(clipped - innovation) > _EPS:
            self.clipped_updates += 1

        s = _bounded_variance(
            p00 + self.observation_variance,
            self.config.minimum_variance,
            self.config.maximum_variance,
        )
        k0, k1 = p00 / s, p10 / s
        old_trend = self.trend
        self.level = level + k0 * clipped
        self.trend = trend + k1 * clipped

        # Joseph covariance update: (I-KH)P(I-KH)' + KRK'.
        a00, a10 = 1.0 - k0, -k1
        m00, m01 = a00 * p00, a00 * p01
        m10, m11 = a10 * p00 + p10, a10 * p01 + p11
        n00 = m00 * a00 + k0 * k0 * self.observation_variance
        n01 = m00 * a10 + m01 + k0 * k1 * self.observation_variance
        n10 = m10 * a00 + k1 * k0 * self.observation_variance
        n11 = m10 * a10 + m11 + k1 * k1 * self.observation_variance
        self.p00 = _bounded_variance(
            n00, self.config.minimum_variance, self.config.maximum_variance
        )
        self.p01 = self.p10 = 0.5 * (n01 + n10)
        self.p11 = _bounded_variance(
            n11, self.config.minimum_variance, self.config.maximum_variance
        )

        self.cumulative_log_likelihood += prior.logpdf(actual)
        self.observations += 1
        self._adapt(innovation, p00, self.trend - old_trend)
        return prior

    def _adapt(self, innovation: float, predicted_state_variance: float, trend_delta: float) -> None:
        rate = self.config.adaptive_rate
        if rate <= 0.0:
            return
        observation_target = max(
            self.config.minimum_variance,
            innovation * innovation - max(0.0, predicted_state_variance),
        )
        level_target = max(self.config.minimum_variance, 0.05 * innovation * innovation)
        trend_target = max(self.config.minimum_variance, trend_delta * trend_delta)
        for field, target in (
            ("observation_variance", observation_target),
            ("level_process_variance", level_target),
            ("trend_process_variance", trend_target),
        ):
            current = getattr(self, field)
            updated = (1.0 - rate) * current + rate * target
            setattr(
                self,
                field,
                _bounded_variance(
                    updated, self.config.minimum_variance, self.config.maximum_variance
                ),
            )


@dataclass(frozen=True, slots=True)
class RegimeModelSpec:
    name: str
    config: StateSpaceConfig

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise HistoricalModeError(
                "regime model name must be non-empty",
                context={"reason": "invalid_regime_spec"},
            )


@dataclass(frozen=True, slots=True)
class RegimeMixtureConfig:
    forgetting: float = 0.01
    evidence_temperature: float = 1.0
    minimum_weight: float = 1e-9

    def __post_init__(self) -> None:
        if not math.isfinite(self.forgetting) or not 0.0 <= self.forgetting < 1.0:
            raise HistoricalModeError(
                "forgetting must be in [0, 1)",
                context={"reason": "invalid_mixture_config"},
            )
        _positive("evidence_temperature", self.evidence_temperature)
        _positive("minimum_weight", self.minimum_weight)
        if self.minimum_weight >= 1.0:
            raise HistoricalModeError(
                "minimum_weight must be below one",
                context={"reason": "invalid_mixture_config"},
            )


@dataclass(frozen=True, slots=True)
class ComponentForecast:
    name: str
    weight: float
    forecast: GaussianForecast


@dataclass(frozen=True, slots=True)
class MixtureForecast:
    components: tuple[ComponentForecast, ...]
    horizon: int

    def __post_init__(self) -> None:
        _positive_int("horizon", self.horizon)
        if not self.components:
            raise HistoricalModeError(
                "mixture requires components",
                context={"reason": "empty_mixture"},
            )
        total = sum(component.weight for component in self.components)
        if any(component.weight < 0.0 for component in self.components) or abs(total - 1.0) > 1e-8:
            raise HistoricalModeError(
                "mixture weights must be non-negative and sum to one",
                context={"reason": "invalid_component_weight", "sum": total},
            )

    @property
    def mean(self) -> float:
        return sum(item.weight * item.forecast.mean for item in self.components)

    @property
    def variance(self) -> float:
        mean = self.mean
        second = sum(
            item.weight * (item.forecast.variance + item.forecast.mean**2)
            for item in self.components
        )
        return max(_EPS, second - mean * mean)

    @property
    def standard_deviation(self) -> float:
        return math.sqrt(self.variance)

    @property
    def weight_entropy(self) -> float:
        return -sum(
            item.weight * math.log(item.weight)
            for item in self.components
            if item.weight > _EPS
        )

    @property
    def effective_components(self) -> float:
        return 1.0 / max(_EPS, sum(item.weight**2 for item in self.components))

    def logpdf(self, value: float) -> float:
        actual = _finite("value", value)
        return _logsumexp(
            [
                math.log(max(item.weight, _EPS)) + item.forecast.logpdf(actual)
                for item in self.components
            ]
        )

    def nll(self, value: float) -> float:
        return -self.logpdf(value)

    def cdf(self, value: float) -> float:
        actual = _finite("value", value)
        return sum(item.weight * item.forecast.cdf(actual) for item in self.components)

    def quantile(self, probability: float) -> float:
        p = _probability("probability", probability)
        lower = min(
            item.forecast.mean - 12.0 * item.forecast.standard_deviation
            for item in self.components
        )
        upper = max(
            item.forecast.mean + 12.0 * item.forecast.standard_deviation
            for item in self.components
        )
        for _ in range(96):
            midpoint = 0.5 * (lower + upper)
            if self.cdf(midpoint) < p:
                lower = midpoint
            else:
                upper = midpoint
        return 0.5 * (lower + upper)

    def interval(self, coverage: float) -> tuple[float, float]:
        level = _probability("coverage", coverage)
        tail = (1.0 - level) / 2.0
        return self.quantile(tail), self.quantile(1.0 - tail)

    def crps(self, value: float) -> float:
        actual = _finite("value", value)
        first = sum(
            item.weight
            * _normal_abs_expectation(
                item.forecast.mean - actual,
                item.forecast.standard_deviation,
            )
            for item in self.components
        )
        second = 0.0
        for left in self.components:
            for right in self.components:
                second += (
                    left.weight
                    * right.weight
                    * _normal_abs_expectation(
                        left.forecast.mean - right.forecast.mean,
                        math.sqrt(left.forecast.variance + right.forecast.variance),
                    )
                )
        return first - 0.5 * second


class BayesianRegimeMixture:
    """Bayesian model averaging over diverse local-dynamics hypotheses."""

    def __init__(
        self,
        first_value: float,
        *,
        specs: Sequence[RegimeModelSpec] | None = None,
        config: RegimeMixtureConfig | None = None,
    ) -> None:
        self.specs = tuple(specs or default_regime_specs())
        if len(self.specs) < 2 or len({item.name for item in self.specs}) != len(self.specs):
            raise HistoricalModeError(
                "mixture requires at least two uniquely named models",
                context={"reason": "invalid_regime_components"},
            )
        self.config = config or RegimeMixtureConfig()
        self.filters = [
            LocalLinearTrendFilter(first_value, config=item.config) for item in self.specs
        ]
        self.weights = [1.0 / len(self.specs)] * len(self.specs)
        self.observations = 1
        self.last_surprise = 0.0
        self.cumulative_log_likelihood = 0.0

    @classmethod
    def fit(
        cls,
        values: Iterable[float],
        *,
        specs: Sequence[RegimeModelSpec] | None = None,
        config: RegimeMixtureConfig | None = None,
    ) -> "BayesianRegimeMixture":
        clean = tuple(_finite("value", value) for value in values)
        if not clean:
            raise HistoricalModeError(
                "mixture fit requires observations",
                context={"reason": "empty_series"},
            )
        model = cls(clean[0], specs=specs, config=config)
        if len(clean) >= 2:
            slope = clean[1] - clean[0]
            for filter_ in model.filters:
                filter_.trend = slope
        for value in clean[1:]:
            model.update(value)
        return model

    def forecast(self, horizon: int = 1) -> MixtureForecast:
        _positive_int("horizon", horizon)
        return MixtureForecast(
            components=tuple(
                ComponentForecast(
                    item.name,
                    weight,
                    replace(filter_.forecast(horizon), model=item.name),
                )
                for item, weight, filter_ in zip(self.specs, self.weights, self.filters)
            ),
            horizon=horizon,
        )

    def update(self, observation: float) -> MixtureForecast:
        actual = _finite("observation", observation)
        predictive = self.forecast(1)
        self.last_surprise = predictive.nll(actual)
        self.cumulative_log_likelihood += predictive.logpdf(actual)
        uniform = 1.0 / len(self.weights)
        log_weights: list[float] = []
        for weight, filter_ in zip(self.weights, self.filters):
            prior = (1.0 - self.config.forgetting) * weight + self.config.forgetting * uniform
            evidence = filter_.forecast(1).logpdf(actual) / self.config.evidence_temperature
            log_weights.append(math.log(max(prior, self.config.minimum_weight)) + evidence)
        normalizer = _logsumexp(log_weights)
        raw = [math.exp(value - normalizer) for value in log_weights]
        floored = [max(self.config.minimum_weight, value) for value in raw]
        total = sum(floored)
        self.weights = [value / total for value in floored]
        for filter_ in self.filters:
            filter_.update(actual)
        self.observations += 1
        return predictive

    def component_weights(self) -> tuple[tuple[str, float], ...]:
        return tuple((item.name, weight) for item, weight in zip(self.specs, self.weights))


def default_regime_specs() -> tuple[RegimeModelSpec, ...]:
    return (
        RegimeModelSpec(
            "steady",
            StateSpaceConfig(
                observation_variance=0.75,
                level_process_variance=0.01,
                trend_process_variance=0.001,
                robust_clip_sigma=3.5,
                adaptive_rate=0.02,
            ),
        ),
        RegimeModelSpec(
            "adaptive_trend",
            StateSpaceConfig(
                observation_variance=1.0,
                level_process_variance=0.08,
                trend_process_variance=0.02,
                robust_clip_sigma=4.0,
                adaptive_rate=0.04,
            ),
        ),
        RegimeModelSpec(
            "volatile",
            StateSpaceConfig(
                observation_variance=2.0,
                level_process_variance=0.35,
                trend_process_variance=0.08,
                robust_clip_sigma=5.0,
                adaptive_rate=0.08,
            ),
        ),
        RegimeModelSpec(
            "shock_robust",
            StateSpaceConfig(
                observation_variance=1.5,
                level_process_variance=0.15,
                trend_process_variance=0.03,
                robust_clip_sigma=2.5,
                adaptive_rate=0.05,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class ProbabilisticEvaluationConfig:
    min_train_size: int = 24
    horizon: int = 1
    step: int = 1
    interval_levels: tuple[float, ...] = (0.50, 0.80, 0.90, 0.95)
    min_folds: int = 12
    min_relative_crps_improvement: float = 0.02
    max_relative_nll_regression: float = 0.05
    max_mean_calibration_error: float = 0.15

    def __post_init__(self) -> None:
        for field in ("min_train_size", "horizon", "step", "min_folds"):
            _positive_int(field, getattr(self, field))
        if not self.interval_levels:
            raise HistoricalModeError(
                "interval levels cannot be empty",
                context={"reason": "invalid_probabilistic_config"},
            )
        previous = 0.0
        for level in self.interval_levels:
            _probability("interval_level", level)
            if level <= previous:
                raise HistoricalModeError(
                    "interval levels must increase",
                    context={"reason": "invalid_probabilistic_config"},
                )
            previous = level
        for field in ("min_relative_crps_improvement", "max_mean_calibration_error"):
            value = _finite(field, getattr(self, field))
            if not 0.0 <= value <= 1.0:
                raise HistoricalModeError(
                    f"{field} must be between zero and one",
                    context={"reason": "invalid_probabilistic_config"},
                )
        if _finite("max_relative_nll_regression", self.max_relative_nll_regression) < 0.0:
            raise HistoricalModeError(
                "max_relative_nll_regression cannot be negative",
                context={"reason": "invalid_probabilistic_config"},
            )


@dataclass(frozen=True, slots=True)
class ProbabilisticFold:
    train_end: int
    target_index: int
    actual: float
    candidate_mean: float
    candidate_variance: float
    candidate_nll: float
    candidate_crps: float
    baseline_mean: float
    baseline_variance: float
    baseline_nll: float
    baseline_crps: float
    interval_hits: tuple[tuple[float, bool], ...]
    interval_widths: tuple[tuple[float, float], ...]
    regime_weights: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if self.target_index <= self.train_end:
            raise HistoricalModeError(
                "target must be after training boundary",
                context={"reason": "leakage_boundary"},
            )


@dataclass(frozen=True, slots=True)
class CoverageMetric:
    level: float
    empirical_coverage: float
    average_width: float
    absolute_calibration_error: float


@dataclass(frozen=True, slots=True)
class ProbabilisticMetrics:
    folds: int
    mae: float
    rmse: float
    mean_nll: float
    mean_crps: float
    mean_predictive_std: float
    coverage: tuple[CoverageMetric, ...]
    mean_calibration_error: float


@dataclass(frozen=True, slots=True)
class ProbabilisticPromotionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    relative_crps_improvement: float
    relative_nll_change: float
    candidate: ProbabilisticMetrics
    baseline: ProbabilisticMetrics


@dataclass(frozen=True, slots=True)
class ProbabilisticEvaluationReport:
    series_label: str
    config: ProbabilisticEvaluationConfig
    folds: tuple[ProbabilisticFold, ...]
    candidate_metrics: ProbabilisticMetrics
    baseline_metrics: ProbabilisticMetrics
    decision: ProbabilisticPromotionDecision
    fingerprint: str

    def as_payload(self) -> dict[str, object]:
        return {
            "series_label": self.series_label,
            "folds": self.candidate_metrics.folds,
            "probabilistic_promotion_accepted": self.decision.accepted,
            "candidate_crps": self.candidate_metrics.mean_crps,
            "baseline_crps": self.baseline_metrics.mean_crps,
            "candidate_nll": self.candidate_metrics.mean_nll,
            "baseline_nll": self.baseline_metrics.mean_nll,
            "calibration_error": self.candidate_metrics.mean_calibration_error,
            "fingerprint": self.fingerprint,
        }


def persistence_distribution(values: Sequence[float], horizon: int = 1) -> GaussianForecast:
    _positive_int("horizon", horizon)
    clean = tuple(_finite("value", value) for value in values)
    if not clean:
        raise HistoricalModeError(
            "persistence distribution requires history",
            context={"reason": "empty_series"},
        )
    if len(clean) < 2:
        variance = 1.0
    else:
        differences = tuple(right - left for left, right in zip(clean, clean[1:]))
        center = float(statistics.median(differences))
        mad = float(statistics.median(abs(value - center) for value in differences))
        sigma = 1.4826 * mad
        if sigma <= 1e-6:
            sigma = statistics.pstdev(differences) if len(differences) > 1 else abs(differences[0])
        sigma = max(sigma, 1e-3)
        variance = sigma * sigma * horizon
    return GaussianForecast(clean[-1], max(variance, 1e-8), horizon, "probabilistic_persistence")


def gaussian_crps(mean: float, sigma: float, value: float) -> float:
    mu = _finite("mean", mean)
    scale = _positive("sigma", sigma)
    actual = _finite("value", value)
    z = (actual - mu) / scale
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return scale * (
        z * (2.0 * _NORMAL.cdf(z) - 1.0)
        + 2.0 * phi
        - 1.0 / math.sqrt(math.pi)
    )


def _normal_abs_expectation(location: float, scale: float) -> float:
    sigma = _positive("scale", scale)
    delta = _finite("location", location)
    z = delta / sigma
    phi = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return 2.0 * sigma * phi + delta * (2.0 * _NORMAL.cdf(z) - 1.0)


def evaluate_probabilistic_state_space(
    series: HistoricalSeries,
    *,
    config: ProbabilisticEvaluationConfig | None = None,
    specs: Sequence[RegimeModelSpec] | None = None,
    mixture_config: RegimeMixtureConfig | None = None,
) -> ProbabilisticEvaluationReport:
    actual_config = config or ProbabilisticEvaluationConfig()
    values = series.values
    required = actual_config.min_train_size + actual_config.horizon
    if len(values) < required:
        raise HistoricalModeError(
            "series is too short for probabilistic evaluation",
            context={"reason": "insufficient_history", "samples": len(values), "required": required},
        )

    folds: list[ProbabilisticFold] = []
    for train_end in range(
        actual_config.min_train_size - 1,
        len(values) - actual_config.horizon,
        actual_config.step,
    ):
        target_index = train_end + actual_config.horizon
        training = values[: train_end + 1]
        actual = values[target_index]
        model = BayesianRegimeMixture.fit(training, specs=specs, config=mixture_config)
        candidate = model.forecast(actual_config.horizon)
        baseline = persistence_distribution(training, actual_config.horizon)

        hits: list[tuple[float, bool]] = []
        widths: list[tuple[float, float]] = []
        for level in actual_config.interval_levels:
            lower, upper = candidate.interval(level)
            hits.append((level, lower - _EPS <= actual <= upper + _EPS))
            widths.append((level, upper - lower))

        folds.append(
            ProbabilisticFold(
                train_end=train_end,
                target_index=target_index,
                actual=actual,
                candidate_mean=candidate.mean,
                candidate_variance=candidate.variance,
                candidate_nll=candidate.nll(actual),
                candidate_crps=candidate.crps(actual),
                baseline_mean=baseline.mean,
                baseline_variance=baseline.variance,
                baseline_nll=baseline.nll(actual),
                baseline_crps=baseline.crps(actual),
                interval_hits=tuple(hits),
                interval_widths=tuple(widths),
                regime_weights=model.component_weights(),
            )
        )

    candidate_metrics = _aggregate(folds, actual_config.interval_levels, candidate=True)
    baseline_metrics = _aggregate(folds, actual_config.interval_levels, candidate=False)
    decision = _promote(candidate_metrics, baseline_metrics, actual_config)
    fingerprint = _fingerprint(series, actual_config, folds, decision)
    return ProbabilisticEvaluationReport(
        series_label=series.label,
        config=actual_config,
        folds=tuple(folds),
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
        decision=decision,
        fingerprint=fingerprint,
    )


def _aggregate(
    folds: Sequence[ProbabilisticFold],
    levels: Sequence[float],
    *,
    candidate: bool,
) -> ProbabilisticMetrics:
    if not folds:
        raise HistoricalModeError(
            "cannot aggregate zero folds",
            context={"reason": "no_folds"},
        )
    if candidate:
        errors = [fold.candidate_mean - fold.actual for fold in folds]
        nll = [fold.candidate_nll for fold in folds]
        crps = [fold.candidate_crps for fold in folds]
        std = [math.sqrt(fold.candidate_variance) for fold in folds]
        coverage = []
        for level in levels:
            empirical = statistics.fmean(
                1.0 if dict(fold.interval_hits)[level] else 0.0 for fold in folds
            )
            width = statistics.fmean(dict(fold.interval_widths)[level] for fold in folds)
            coverage.append(CoverageMetric(level, empirical, width, abs(empirical - level)))
    else:
        errors = [fold.baseline_mean - fold.actual for fold in folds]
        nll = [fold.baseline_nll for fold in folds]
        crps = [fold.baseline_crps for fold in folds]
        std = [math.sqrt(fold.baseline_variance) for fold in folds]
        coverage = []
        for level in levels:
            hits, widths = [], []
            for fold in folds:
                dist = GaussianForecast(
                    fold.baseline_mean,
                    fold.baseline_variance,
                    1,
                    "probabilistic_persistence",
                )
                lower, upper = dist.interval(level)
                hits.append(1.0 if lower - _EPS <= fold.actual <= upper + _EPS else 0.0)
                widths.append(upper - lower)
            empirical = statistics.fmean(hits)
            coverage.append(
                CoverageMetric(level, empirical, statistics.fmean(widths), abs(empirical - level))
            )
    return ProbabilisticMetrics(
        folds=len(folds),
        mae=statistics.fmean(abs(error) for error in errors),
        rmse=math.sqrt(statistics.fmean(error * error for error in errors)),
        mean_nll=statistics.fmean(nll),
        mean_crps=statistics.fmean(crps),
        mean_predictive_std=statistics.fmean(std),
        coverage=tuple(coverage),
        mean_calibration_error=statistics.fmean(item.absolute_calibration_error for item in coverage),
    )


def _promote(
    candidate: ProbabilisticMetrics,
    baseline: ProbabilisticMetrics,
    config: ProbabilisticEvaluationConfig,
) -> ProbabilisticPromotionDecision:
    reasons: list[str] = []
    if candidate.folds < config.min_folds:
        reasons.append("insufficient_folds")
    if baseline.mean_crps <= _EPS:
        relative_crps = 0.0 if candidate.mean_crps <= _EPS else -math.inf
    else:
        relative_crps = (baseline.mean_crps - candidate.mean_crps) / baseline.mean_crps
    if relative_crps < config.min_relative_crps_improvement:
        reasons.append("insufficient_crps_improvement")
    nll_scale = max(abs(baseline.mean_nll), 1.0)
    relative_nll_change = (candidate.mean_nll - baseline.mean_nll) / nll_scale
    if relative_nll_change > config.max_relative_nll_regression:
        reasons.append("nll_regression")
    if candidate.mean_calibration_error > config.max_mean_calibration_error:
        reasons.append("interval_miscalibration")
    accepted = not reasons
    if accepted:
        reasons.append("probabilistic_gate_passed")
    return ProbabilisticPromotionDecision(
        accepted,
        tuple(reasons),
        relative_crps,
        relative_nll_change,
        candidate,
        baseline,
    )


def _fingerprint(
    series: HistoricalSeries,
    config: ProbabilisticEvaluationConfig,
    folds: Sequence[ProbabilisticFold],
    decision: ProbabilisticPromotionDecision,
) -> str:
    parts = [
        "jeeves-probabilistic-state-space-v1",
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
                format(fold.actual, ".17g"),
                format(fold.candidate_mean, ".17g"),
                format(fold.candidate_variance, ".17g"),
                format(fold.candidate_crps, ".17g"),
                ";".join(f"{name}:{format(weight, '.17g')}" for name, weight in fold.regime_weights),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


__all__ = [
    "BayesianRegimeMixture",
    "ComponentForecast",
    "CoverageMetric",
    "FilterSnapshot",
    "GaussianForecast",
    "LocalLinearTrendFilter",
    "MixtureForecast",
    "ProbabilisticEvaluationConfig",
    "ProbabilisticEvaluationReport",
    "ProbabilisticFold",
    "ProbabilisticMetrics",
    "ProbabilisticPromotionDecision",
    "RegimeMixtureConfig",
    "RegimeModelSpec",
    "StateSpaceConfig",
    "default_regime_specs",
    "evaluate_probabilistic_state_space",
    "gaussian_crps",
    "persistence_distribution",
]
