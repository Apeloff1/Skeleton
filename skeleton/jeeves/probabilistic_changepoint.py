"""Bayesian online change-point detection (BOCPD) for Jeeves.

This module implements a deterministic Adams-MacKay style run-length filter over
first changes of a scalar series. Each possible run length owns a conjugate
Normal-Inverse-Gamma posterior, yielding Student-t predictive evidence for the
next change. A constant hazard prior controls the expected segment duration.

The output is descriptive evidence about abrupt distributional shifts. It is not
an action signal and does not mutate Jeeves learning state.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .probabilistic_state_space import SeriesValues, StateSpaceError

_EPSILON = 1e-300


@dataclass(frozen=True, slots=True)
class ChangePointConfig:
    expected_run_length: float = 50.0
    max_run_length: int = 256
    prior_mean: float = 0.0
    prior_kappa: float = 0.25
    prior_alpha: float = 2.5
    prior_beta: float = 1.0
    change_alert_probability: float = 0.25

    def __post_init__(self) -> None:
        if _positive("expected_run_length", self.expected_run_length) <= 1.0:
            raise StateSpaceError(
                "expected_run_length must exceed 1",
                context={"reason": "invalid_changepoint_config", "field": "expected_run_length"},
            )
        if isinstance(self.max_run_length, bool) or not isinstance(self.max_run_length, int) or self.max_run_length < 2:
            raise StateSpaceError(
                "max_run_length must be an integer >= 2",
                context={"reason": "invalid_changepoint_config", "field": "max_run_length"},
            )
        _finite("prior_mean", self.prior_mean)
        _positive("prior_kappa", self.prior_kappa)
        if _positive("prior_alpha", self.prior_alpha) <= 1.0:
            raise StateSpaceError(
                "prior_alpha must exceed 1",
                context={"reason": "invalid_changepoint_config", "field": "prior_alpha"},
            )
        _positive("prior_beta", self.prior_beta)
        _open_interval("change_alert_probability", self.change_alert_probability, 0.0, 1.0)

    @property
    def hazard(self) -> float:
        return 1.0 / self.expected_run_length


@dataclass(frozen=True, slots=True)
class ConjugateRunState:
    mean: float
    kappa: float
    alpha: float
    beta: float
    samples: int

    def __post_init__(self) -> None:
        _finite("mean", self.mean)
        _positive("kappa", self.kappa)
        _positive("alpha", self.alpha)
        _positive("beta", self.beta)
        if isinstance(self.samples, bool) or not isinstance(self.samples, int) or self.samples < 0:
            raise StateSpaceError(
                "samples must be a non-negative integer",
                context={"reason": "invalid_run_state"},
            )

    @property
    def degrees_of_freedom(self) -> float:
        return 2.0 * self.alpha

    @property
    def predictive_scale_squared(self) -> float:
        return self.beta * (self.kappa + 1.0) / (self.alpha * self.kappa)

    @property
    def predictive_variance(self) -> float:
        nu = self.degrees_of_freedom
        return self.predictive_scale_squared * nu / max(_EPSILON, nu - 2.0)

    def log_predictive_density(self, value: float) -> float:
        return _student_t_log_density(
            value,
            mean=self.mean,
            degrees_of_freedom=self.degrees_of_freedom,
            scale_squared=self.predictive_scale_squared,
        )

    def update(self, value: float) -> "ConjugateRunState":
        value = _finite("value", value)
        new_kappa = self.kappa + 1.0
        delta = value - self.mean
        new_mean = self.mean + delta / new_kappa
        new_alpha = self.alpha + 0.5
        new_beta = self.beta + 0.5 * self.kappa * delta * delta / new_kappa
        return ConjugateRunState(
            mean=new_mean,
            kappa=new_kappa,
            alpha=new_alpha,
            beta=max(_EPSILON, new_beta),
            samples=self.samples + 1,
        )


@dataclass(frozen=True, slots=True)
class ChangePointStep:
    observation_index: int
    change: float
    change_probability: float
    expected_run_length: float
    map_run_length: int
    run_length_probabilities: tuple[float, ...]
    predictive_log_density: float
    alert: bool

    def __post_init__(self) -> None:
        if isinstance(self.observation_index, bool) or not isinstance(self.observation_index, int) or self.observation_index < 1:
            raise StateSpaceError(
                "observation_index must be >= 1",
                context={"reason": "invalid_changepoint_step"},
            )
        _finite("change", self.change)
        _closed_interval("change_probability", self.change_probability, 0.0, 1.0)
        _non_negative("expected_run_length", self.expected_run_length)
        if isinstance(self.map_run_length, bool) or not isinstance(self.map_run_length, int) or self.map_run_length < 0:
            raise StateSpaceError(
                "map_run_length must be non-negative",
                context={"reason": "invalid_changepoint_step"},
            )
        _validate_probability_vector(self.run_length_probabilities)
        _finite("predictive_log_density", self.predictive_log_density)


@dataclass(frozen=True, slots=True)
class ChangePointForecast:
    last_level: float
    mean_change: float
    variance_change: float
    mean_level: float
    variance_level: float
    change_probability: float
    run_length_entropy: float

    def log_density(self, actual_level: float) -> float:
        actual_level = _finite("actual_level", actual_level)
        error = actual_level - self.mean_level
        variance = max(_EPSILON, self.variance_level)
        return -0.5 * (
            math.log(2.0 * math.pi * variance) + error * error / variance
        )


@dataclass(frozen=True, slots=True)
class ChangePointFit:
    config: ChangePointConfig
    observations: tuple[float, ...]
    changes: tuple[float, ...]
    steps: tuple[ChangePointStep, ...]
    final_probabilities: tuple[float, ...]
    final_states: tuple[ConjugateRunState, ...]
    fingerprint: str

    @property
    def latest_change_probability(self) -> float:
        return self.steps[-1].change_probability

    @property
    def latest_expected_run_length(self) -> float:
        return self.steps[-1].expected_run_length

    @property
    def alerts(self) -> tuple[ChangePointStep, ...]:
        return tuple(step for step in self.steps if step.alert)

    def forecast(self) -> ChangePointForecast:
        return forecast_changepoint(self)


@dataclass(frozen=True, slots=True)
class ChangePointEvaluation:
    folds: int
    mean_log_score: float
    mae: float
    rmse: float
    mean_change_probability: float
    alert_rate: float
    fingerprint: str


def fit_changepoint(
    series: SeriesValues | Sequence[float],
    *,
    config: ChangePointConfig | None = None,
) -> ChangePointFit:
    """Run BOCPD across first changes of a scalar history."""

    actual_config = config or ChangePointConfig()
    values = _coerce_values(series)
    if len(values) < 3:
        raise StateSpaceError(
            "change-point fitting requires at least three observations",
            context={"reason": "insufficient_history"},
        )
    changes = tuple(right - left for left, right in zip(values, values[1:]))
    prior_state = _prior_state(actual_config)
    probabilities = (1.0,)
    states = (prior_state,)
    steps: list[ChangePointStep] = []

    for change_index, change in enumerate(changes, start=1):
        predictive_logs = tuple(state.log_predictive_density(change) for state in states)
        mixture_log_density = _logsumexp(
            tuple(
                math.log(max(_EPSILON, probability)) + log_density
                for probability, log_density in zip(probabilities, predictive_logs)
            )
        )

        log_growth: list[float] = []
        for probability, log_density in zip(probabilities, predictive_logs):
            log_growth.append(
                math.log(max(_EPSILON, probability))
                + math.log1p(-actual_config.hazard)
                + log_density
            )
        log_change = _logsumexp(
            tuple(
                math.log(max(_EPSILON, probability))
                + math.log(actual_config.hazard)
                + log_density
                for probability, log_density in zip(probabilities, predictive_logs)
            )
        )

        candidate_logs = [log_change, *log_growth]
        maximum = max(candidate_logs)
        raw = [math.exp(value - maximum) for value in candidate_logs]
        normalizer = sum(raw)
        next_probabilities = [value / normalizer for value in raw]

        next_states: list[ConjugateRunState] = [prior_state.update(change)]
        next_states.extend(state.update(change) for state in states)

        if len(next_probabilities) > actual_config.max_run_length + 1:
            retained = actual_config.max_run_length + 1
            tail_mass = sum(next_probabilities[retained - 1 :])
            next_probabilities = next_probabilities[: retained - 1] + [tail_mass]
            next_states = next_states[:retained]

        probability_total = sum(next_probabilities)
        next_probabilities = [value / probability_total for value in next_probabilities]
        if len(next_states) != len(next_probabilities):
            raise StateSpaceError(
                "run-length state/probability mismatch",
                context={"reason": "numerical_instability"},
            )

        change_probability = next_probabilities[0]
        expected_run_length = sum(
            run_length * probability
            for run_length, probability in enumerate(next_probabilities)
        )
        map_run_length = max(
            range(len(next_probabilities)),
            key=lambda run_length: (next_probabilities[run_length], run_length),
        )
        steps.append(
            ChangePointStep(
                observation_index=change_index,
                change=change,
                change_probability=change_probability,
                expected_run_length=expected_run_length,
                map_run_length=map_run_length,
                run_length_probabilities=tuple(next_probabilities),
                predictive_log_density=mixture_log_density,
                alert=change_probability >= actual_config.change_alert_probability,
            )
        )
        probabilities = tuple(next_probabilities)
        states = tuple(next_states)

    fingerprint = _fit_fingerprint(
        config=actual_config,
        values=values,
        steps=steps,
        probabilities=probabilities,
        states=states,
    )
    return ChangePointFit(
        config=actual_config,
        observations=values,
        changes=changes,
        steps=tuple(steps),
        final_probabilities=probabilities,
        final_states=states,
        fingerprint=fingerprint,
    )


def forecast_changepoint(fit: ChangePointFit) -> ChangePointForecast:
    """Moment-match the run-length posterior's next-change Student-t mixture."""

    probabilities = fit.final_probabilities
    states = fit.final_states
    if len(probabilities) != len(states):
        raise StateSpaceError(
            "run-length posterior is internally inconsistent",
            context={"reason": "invalid_changepoint_fit"},
        )

    means = [state.mean for state in states]
    variances = [state.predictive_variance for state in states]
    mean_change = sum(probability * mean for probability, mean in zip(probabilities, means))
    second_moment = sum(
        probability * (variance + mean * mean)
        for probability, mean, variance in zip(probabilities, means, variances)
    )
    variance_change = max(_EPSILON, second_moment - mean_change * mean_change)
    entropy = -sum(
        probability * math.log(max(_EPSILON, probability))
        for probability in probabilities
    )
    return ChangePointForecast(
        last_level=fit.observations[-1],
        mean_change=mean_change,
        variance_change=variance_change,
        mean_level=fit.observations[-1] + mean_change,
        variance_level=variance_change,
        change_probability=fit.latest_change_probability,
        run_length_entropy=entropy,
    )


def evaluate_changepoint_prequential(
    series: SeriesValues | Sequence[float],
    *,
    min_train_size: int = 12,
    step: int = 1,
    config: ChangePointConfig | None = None,
) -> ChangePointEvaluation:
    """Leakage-safe one-step evaluation by rerunning BOCPD on each prefix."""

    values = _coerce_values(series)
    if isinstance(min_train_size, bool) or not isinstance(min_train_size, int) or min_train_size < 3:
        raise StateSpaceError(
            "min_train_size must be an integer >= 3",
            context={"reason": "invalid_changepoint_eval_config"},
        )
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise StateSpaceError(
            "step must be a positive integer",
            context={"reason": "invalid_changepoint_eval_config"},
        )
    if len(values) <= min_train_size:
        raise StateSpaceError(
            "series is too short for change-point evaluation",
            context={"reason": "insufficient_history"},
        )

    actual_config = config or ChangePointConfig()
    log_scores: list[float] = []
    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    probabilities: list[float] = []
    alerts: list[float] = []

    for target_index in range(min_train_size, len(values), step):
        fit = fit_changepoint(values[:target_index], config=actual_config)
        forecast = fit.forecast()
        actual = values[target_index]
        error = forecast.mean_level - actual
        log_scores.append(forecast.log_density(actual))
        absolute_errors.append(abs(error))
        squared_errors.append(error * error)
        probabilities.append(forecast.change_probability)
        alerts.append(1.0 if fit.steps[-1].alert else 0.0)

    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-changepoint-eval-v1",
                repr(actual_config),
                str(min_train_size),
                str(step),
                ",".join(format(value, ".17g") for value in log_scores),
                ",".join(format(value, ".17g") for value in absolute_errors),
                ",".join(format(value, ".17g") for value in probabilities),
            )
        ).encode("utf-8")
    ).hexdigest()
    return ChangePointEvaluation(
        folds=len(log_scores),
        mean_log_score=statistics.fmean(log_scores),
        mae=statistics.fmean(absolute_errors),
        rmse=math.sqrt(statistics.fmean(squared_errors)),
        mean_change_probability=statistics.fmean(probabilities),
        alert_rate=statistics.fmean(alerts),
        fingerprint=fingerprint,
    )


def _prior_state(config: ChangePointConfig) -> ConjugateRunState:
    return ConjugateRunState(
        mean=config.prior_mean,
        kappa=config.prior_kappa,
        alpha=config.prior_alpha,
        beta=config.prior_beta,
        samples=0,
    )


def _student_t_log_density(
    value: float,
    *,
    mean: float,
    degrees_of_freedom: float,
    scale_squared: float,
) -> float:
    value = _finite("value", value)
    nu = _positive("degrees_of_freedom", degrees_of_freedom)
    scale_squared = _positive("scale_squared", scale_squared)
    centered = value - mean
    return (
        math.lgamma((nu + 1.0) / 2.0)
        - math.lgamma(nu / 2.0)
        - 0.5 * math.log(nu * math.pi * scale_squared)
        - ((nu + 1.0) / 2.0)
        * math.log1p(centered * centered / (nu * scale_squared))
    )


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise StateSpaceError(
            "logsumexp requires values",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    if not math.isfinite(maximum):
        raise StateSpaceError(
            "change-point log probabilities became non-finite",
            context={"reason": "numerical_instability"},
        )
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def _validate_probability_vector(values: Sequence[float]) -> None:
    if not values:
        raise StateSpaceError(
            "run-length probability vector cannot be empty",
            context={"reason": "invalid_probability_vector"},
        )
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise StateSpaceError(
            "run-length probabilities must be finite and non-negative",
            context={"reason": "invalid_probability_vector"},
        )
    if abs(sum(values) - 1.0) > 1e-8:
        raise StateSpaceError(
            "run-length probabilities must sum to one",
            context={"reason": "invalid_probability_vector"},
        )


def _fit_fingerprint(
    *,
    config: ChangePointConfig,
    values: Sequence[float],
    steps: Sequence[ChangePointStep],
    probabilities: Sequence[float],
    states: Sequence[ConjugateRunState],
) -> str:
    parts = [
        "jeeves-bocpd-v1",
        repr(config),
        ",".join(format(value, ".17g") for value in values),
        ",".join(format(value, ".17g") for value in probabilities),
    ]
    for step in steps:
        parts.extend(
            (
                str(step.observation_index),
                format(step.change, ".17g"),
                format(step.change_probability, ".17g"),
                format(step.expected_run_length, ".17g"),
                str(step.map_run_length),
            )
        )
    for state in states:
        parts.extend(
            (
                format(state.mean, ".17g"),
                format(state.kappa, ".17g"),
                format(state.alpha, ".17g"),
                format(state.beta, ".17g"),
                str(state.samples),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "change-point series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "change-point series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "change-point series cannot be empty",
            context={"reason": "empty_series"},
        )
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


def _positive(name: str, value: object) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _non_negative(name: str, value: object) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_number", "field": name},
        )
    return number


def _open_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum < number < maximum:
        raise StateSpaceError(
            f"{name} must be strictly between {minimum} and {maximum}",
            context={"reason": "out_of_range", "field": name},
        )
    return number


def _closed_interval(name: str, value: object, minimum: float, maximum: float) -> float:
    number = _finite(name, value)
    if not minimum <= number <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "out_of_range", "field": name},
        )
    return number


__all__ = [
    "ChangePointConfig",
    "ChangePointEvaluation",
    "ChangePointFit",
    "ChangePointForecast",
    "ChangePointStep",
    "ConjugateRunState",
    "evaluate_changepoint_prequential",
    "fit_changepoint",
    "forecast_changepoint",
]
