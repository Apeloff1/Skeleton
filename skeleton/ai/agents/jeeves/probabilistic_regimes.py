"""Hidden-Markov regime modeling for Jeeves probabilistic forecasts.

This module fits a finite-state Gaussian hidden Markov model (HMM) to first
changes of a scalar series using deterministic Baum-Welch expectation
maximization. It is an offline mathematical primitive: no provider calls, market
data fetching, actions, or learning-state mutation occur here.

Key properties:
- log-shifted scaled forward/backward recursions for numerical stability,
- sticky transition regularization to discourage pathological one-step regimes,
- deterministic state ordering by emission mean to avoid label switching,
- posterior state probabilities and entropy,
- exact one-step Gaussian-mixture density,
- multi-step level mean/variance through Markov reward moment recursion,
- immutable fingerprints for reproducibility.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .probabilistic_state_space import SeriesValues, StateSpaceError

_EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class RegimeHMMConfig:
    states: int = 3
    max_iterations: int = 60
    tolerance: float = 1e-7
    min_variance: float = 1e-6
    sticky_prior: float = 2.0
    transition_prior: float = 0.10

    def __post_init__(self) -> None:
        if isinstance(self.states, bool) or not isinstance(self.states, int) or not 2 <= self.states <= 8:
            raise StateSpaceError(
                "states must be an integer between 2 and 8",
                context={"reason": "invalid_hmm_config", "field": "states"},
            )
        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or self.max_iterations < 1:
            raise StateSpaceError(
                "max_iterations must be a positive integer",
                context={"reason": "invalid_hmm_config", "field": "max_iterations"},
            )
        _positive("tolerance", self.tolerance)
        _positive("min_variance", self.min_variance)
        _non_negative("sticky_prior", self.sticky_prior)
        _non_negative("transition_prior", self.transition_prior)


@dataclass(frozen=True, slots=True)
class GaussianRegime:
    index: int
    mean_change: float
    variance_change: float

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise StateSpaceError(
                "regime index must be non-negative",
                context={"reason": "invalid_regime"},
            )
        _finite("mean_change", self.mean_change)
        _positive("variance_change", self.variance_change)


@dataclass(frozen=True, slots=True)
class RegimeHMMModel:
    regimes: tuple[GaussianRegime, ...]
    transition: tuple[tuple[float, ...], ...]
    initial: tuple[float, ...]

    def __post_init__(self) -> None:
        states = len(self.regimes)
        if states < 2:
            raise StateSpaceError(
                "HMM requires at least two regimes",
                context={"reason": "invalid_hmm_model"},
            )
        if tuple(regime.index for regime in self.regimes) != tuple(range(states)):
            raise StateSpaceError(
                "regime indices must be contiguous and ordered",
                context={"reason": "invalid_hmm_model"},
            )
        if len(self.transition) != states or any(len(row) != states for row in self.transition):
            raise StateSpaceError(
                "transition matrix has invalid shape",
                context={"reason": "invalid_hmm_model"},
            )
        if len(self.initial) != states:
            raise StateSpaceError(
                "initial probabilities have invalid shape",
                context={"reason": "invalid_hmm_model"},
            )
        _validate_probability_vector(self.initial, field="initial")
        for row in self.transition:
            _validate_probability_vector(row, field="transition")


@dataclass(frozen=True, slots=True)
class RegimePosteriorStep:
    observation_index: int
    change: float
    probabilities: tuple[float, ...]
    entropy: float
    dominant_state: int

    def __post_init__(self) -> None:
        if isinstance(self.observation_index, bool) or not isinstance(self.observation_index, int) or self.observation_index < 1:
            raise StateSpaceError(
                "observation_index must be >= 1",
                context={"reason": "invalid_regime_posterior"},
            )
        _finite("change", self.change)
        _validate_probability_vector(self.probabilities, field="posterior")
        _non_negative("entropy", self.entropy)
        if not 0 <= self.dominant_state < len(self.probabilities):
            raise StateSpaceError(
                "dominant_state is outside posterior support",
                context={"reason": "invalid_regime_posterior"},
            )


@dataclass(frozen=True, slots=True)
class RegimeForecastComponent:
    state: int
    probability: float
    mean_level: float
    variance_level: float


@dataclass(frozen=True, slots=True)
class RegimeForecast:
    horizon: int
    last_level: float
    mean: float
    variance: float
    state_probabilities: tuple[float, ...]
    components: tuple[RegimeForecastComponent, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, int) or self.horizon <= 0:
            raise StateSpaceError(
                "horizon must be a positive integer",
                context={"reason": "invalid_regime_forecast"},
            )
        _finite("last_level", self.last_level)
        _finite("mean", self.mean)
        _positive("variance", self.variance)
        _validate_probability_vector(self.state_probabilities, field="forecast_state_probabilities")

    def moment_interval(self, z: float = 1.959963984540054) -> tuple[float, float]:
        z = _positive("z", z)
        radius = z * math.sqrt(self.variance)
        return self.mean - radius, self.mean + radius

    def log_density(self, actual_level: float) -> float:
        """Exact one-step mixture log density; moment Gaussian for longer horizons."""

        actual_level = _finite("actual_level", actual_level)
        if self.horizon == 1 and self.components:
            terms = [
                math.log(max(_EPSILON, component.probability))
                + _gaussian_log_density(
                    actual_level - component.mean_level,
                    component.variance_level,
                )
                for component in self.components
            ]
            return _logsumexp(terms)
        return _gaussian_log_density(actual_level - self.mean, self.variance)


@dataclass(frozen=True, slots=True)
class RegimeHMMFit:
    config: RegimeHMMConfig
    observations: tuple[float, ...]
    changes: tuple[float, ...]
    model: RegimeHMMModel
    posteriors: tuple[RegimePosteriorStep, ...]
    log_likelihood: float
    iterations: int
    converged: bool
    fingerprint: str

    @property
    def last_posterior(self) -> tuple[float, ...]:
        return self.posteriors[-1].probabilities

    @property
    def average_entropy(self) -> float:
        return statistics.fmean(step.entropy for step in self.posteriors)

    def forecast(self, horizon: int = 1) -> RegimeForecast:
        return forecast_regime_hmm(self, horizon=horizon)


@dataclass(frozen=True, slots=True)
class RegimePrequentialScore:
    folds: int
    mean_log_score: float
    mae: float
    rmse: float
    average_entropy: float
    fingerprint: str


def fit_regime_hmm(
    series: SeriesValues | Sequence[float],
    *,
    config: RegimeHMMConfig | None = None,
) -> RegimeHMMFit:
    """Fit a deterministic Gaussian HMM to first changes using Baum-Welch EM."""

    actual_config = config or RegimeHMMConfig()
    values = _coerce_values(series)
    if len(values) < max(6, actual_config.states + 2):
        raise StateSpaceError(
            "series is too short for regime HMM fitting",
            context={"reason": "insufficient_history", "samples": len(values)},
        )
    changes = tuple(right - left for left, right in zip(values, values[1:]))
    if len(changes) < actual_config.states:
        raise StateSpaceError(
            "insufficient changes for requested HMM states",
            context={"reason": "insufficient_history"},
        )

    model = _initialize_model(changes, actual_config)
    previous_log_likelihood: float | None = None
    converged = False
    iterations = 0

    for iteration in range(1, actual_config.max_iterations + 1):
        alpha, scales, log_likelihood = _forward(changes, model)
        beta = _backward(changes, model, scales)
        gamma = _gamma(alpha, beta)
        xi = _xi(changes, model, alpha, beta, scales)
        updated = _m_step(changes, gamma, xi, actual_config)
        model = _ordered_model(updated)
        iterations = iteration

        if previous_log_likelihood is not None:
            delta = abs(log_likelihood - previous_log_likelihood)
            scale = max(1.0, abs(previous_log_likelihood))
            if delta <= actual_config.tolerance * scale:
                converged = True
                break
        previous_log_likelihood = log_likelihood

    alpha, scales, log_likelihood = _forward(changes, model)
    beta = _backward(changes, model, scales)
    gamma = _gamma(alpha, beta)
    posteriors = tuple(
        RegimePosteriorStep(
            observation_index=index + 1,
            change=change,
            probabilities=tuple(probabilities),
            entropy=_entropy(probabilities),
            dominant_state=max(range(len(probabilities)), key=lambda state: (probabilities[state], -state)),
        )
        for index, (change, probabilities) in enumerate(zip(changes, gamma))
    )
    fingerprint = _fit_fingerprint(
        config=actual_config,
        values=values,
        model=model,
        posteriors=posteriors,
        log_likelihood=log_likelihood,
        iterations=iterations,
        converged=converged,
    )
    return RegimeHMMFit(
        config=actual_config,
        observations=values,
        changes=changes,
        model=model,
        posteriors=posteriors,
        log_likelihood=log_likelihood,
        iterations=iterations,
        converged=converged,
        fingerprint=fingerprint,
    )


def forecast_regime_hmm(fit: RegimeHMMFit, *, horizon: int = 1) -> RegimeForecast:
    """Forecast future level moments under the fitted Markov reward process."""

    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "horizon must be a positive integer",
            context={"reason": "invalid_horizon"},
        )

    states = len(fit.model.regimes)
    probabilities = list(fit.last_posterior)
    first_moment_mass = [0.0] * states
    second_moment_mass = [0.0] * states
    one_step_components: tuple[RegimeForecastComponent, ...] = ()

    for step in range(1, horizon + 1):
        next_probabilities = [0.0] * states
        next_first = [0.0] * states
        next_second = [0.0] * states

        for source in range(states):
            for target in range(states):
                transition = fit.model.transition[source][target]
                mass = probabilities[source] * transition
                if mass <= 0.0:
                    continue
                regime = fit.model.regimes[target]
                mean = regime.mean_change
                variance = regime.variance_change
                next_probabilities[target] += mass
                next_first[target] += transition * (
                    first_moment_mass[source] + probabilities[source] * mean
                )
                next_second[target] += transition * (
                    second_moment_mass[source]
                    + 2.0 * mean * first_moment_mass[source]
                    + probabilities[source] * (variance + mean * mean)
                )

        total = sum(next_probabilities)
        if total <= _EPSILON:
            raise StateSpaceError(
                "regime forecast lost all probability mass",
                context={"reason": "numerical_instability"},
            )
        probabilities = [value / total for value in next_probabilities]
        first_moment_mass = [value / total for value in next_first]
        second_moment_mass = [value / total for value in next_second]

        if step == 1:
            one_step_components = tuple(
                RegimeForecastComponent(
                    state=state,
                    probability=probabilities[state],
                    mean_level=fit.observations[-1] + fit.model.regimes[state].mean_change,
                    variance_level=fit.model.regimes[state].variance_change,
                )
                for state in range(states)
            )

    change_mean = sum(first_moment_mass)
    change_second = sum(second_moment_mass)
    change_variance = max(_EPSILON, change_second - change_mean * change_mean)
    return RegimeForecast(
        horizon=horizon,
        last_level=fit.observations[-1],
        mean=fit.observations[-1] + change_mean,
        variance=change_variance,
        state_probabilities=tuple(probabilities),
        components=one_step_components if horizon == 1 else (),
    )


def evaluate_regime_hmm_prequential(
    series: SeriesValues | Sequence[float],
    *,
    min_train_size: int = 24,
    step: int = 1,
    config: RegimeHMMConfig | None = None,
) -> RegimePrequentialScore:
    """Leakage-safe one-step evaluation by refitting on each training prefix."""

    values = _coerce_values(series)
    if isinstance(min_train_size, bool) or not isinstance(min_train_size, int) or min_train_size < 6:
        raise StateSpaceError(
            "min_train_size must be an integer >= 6",
            context={"reason": "invalid_prequential_config"},
        )
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise StateSpaceError(
            "step must be a positive integer",
            context={"reason": "invalid_prequential_config"},
        )
    if len(values) <= min_train_size:
        raise StateSpaceError(
            "series is too short for regime prequential evaluation",
            context={"reason": "insufficient_history"},
        )

    actual_config = config or RegimeHMMConfig()
    log_scores: list[float] = []
    absolute_errors: list[float] = []
    squared_errors: list[float] = []
    entropies: list[float] = []

    for target_index in range(min_train_size, len(values), step):
        fit = fit_regime_hmm(values[:target_index], config=actual_config)
        forecast = fit.forecast(1)
        actual = values[target_index]
        error = forecast.mean - actual
        log_scores.append(forecast.log_density(actual))
        absolute_errors.append(abs(error))
        squared_errors.append(error * error)
        entropies.append(_entropy(forecast.state_probabilities))

    fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-regime-prequential-v1",
                repr(actual_config),
                str(min_train_size),
                str(step),
                ",".join(format(value, ".17g") for value in log_scores),
                ",".join(format(value, ".17g") for value in absolute_errors),
                ",".join(format(value, ".17g") for value in squared_errors),
                ",".join(format(value, ".17g") for value in entropies),
            )
        ).encode("utf-8")
    ).hexdigest()
    return RegimePrequentialScore(
        folds=len(log_scores),
        mean_log_score=statistics.fmean(log_scores),
        mae=statistics.fmean(absolute_errors),
        rmse=math.sqrt(statistics.fmean(squared_errors)),
        average_entropy=statistics.fmean(entropies),
        fingerprint=fingerprint,
    )


def _initialize_model(changes: Sequence[float], config: RegimeHMMConfig) -> RegimeHMMModel:
    states = config.states
    ordered = sorted(changes)
    means: list[float] = []
    for state in range(states):
        probability = (state + 0.5) / states
        index = min(len(ordered) - 1, max(0, int(probability * len(ordered))))
        means.append(ordered[index])

    global_variance = statistics.pvariance(changes) if len(changes) > 1 else config.min_variance
    global_variance = max(config.min_variance, global_variance)
    regimes = tuple(
        GaussianRegime(index=state, mean_change=means[state], variance_change=global_variance)
        for state in range(states)
    )
    if states == 1:
        transition = ((1.0,),)
    else:
        diagonal = 0.80
        off = (1.0 - diagonal) / (states - 1)
        transition = tuple(
            tuple(diagonal if source == target else off for target in range(states))
            for source in range(states)
        )
    initial = tuple(1.0 / states for _ in range(states))
    return _ordered_model(RegimeHMMModel(regimes=regimes, transition=transition, initial=initial))


def _forward(
    observations: Sequence[float],
    model: RegimeHMMModel,
) -> tuple[list[list[float]], list[float], float]:
    states = len(model.regimes)
    alpha = [[0.0] * states for _ in observations]
    scales = [0.0] * len(observations)
    log_likelihood = 0.0

    emissions, log_offset = _shifted_emissions(observations[0], model.regimes)
    for state in range(states):
        alpha[0][state] = model.initial[state] * emissions[state]
    scales[0] = sum(alpha[0])
    _require_positive_scale(scales[0])
    alpha[0] = [value / scales[0] for value in alpha[0]]
    log_likelihood += math.log(scales[0]) + log_offset

    for t in range(1, len(observations)):
        emissions, log_offset = _shifted_emissions(observations[t], model.regimes)
        for target in range(states):
            predicted = sum(
                alpha[t - 1][source] * model.transition[source][target]
                for source in range(states)
            )
            alpha[t][target] = predicted * emissions[target]
        scales[t] = sum(alpha[t])
        _require_positive_scale(scales[t])
        alpha[t] = [value / scales[t] for value in alpha[t]]
        log_likelihood += math.log(scales[t]) + log_offset

    return alpha, scales, log_likelihood


def _backward(
    observations: Sequence[float],
    model: RegimeHMMModel,
    scales: Sequence[float],
) -> list[list[float]]:
    states = len(model.regimes)
    beta = [[0.0] * states for _ in observations]
    beta[-1] = [1.0] * states

    for t in range(len(observations) - 2, -1, -1):
        emissions, _ = _shifted_emissions(observations[t + 1], model.regimes)
        for source in range(states):
            beta[t][source] = sum(
                model.transition[source][target]
                * emissions[target]
                * beta[t + 1][target]
                for target in range(states)
            ) / scales[t + 1]
    return beta


def _gamma(alpha: Sequence[Sequence[float]], beta: Sequence[Sequence[float]]) -> list[list[float]]:
    gamma: list[list[float]] = []
    for alpha_row, beta_row in zip(alpha, beta):
        raw = [left * right for left, right in zip(alpha_row, beta_row)]
        total = sum(raw)
        _require_positive_scale(total)
        gamma.append([value / total for value in raw])
    return gamma


def _xi(
    observations: Sequence[float],
    model: RegimeHMMModel,
    alpha: Sequence[Sequence[float]],
    beta: Sequence[Sequence[float]],
    scales: Sequence[float],
) -> list[list[list[float]]]:
    del scales
    states = len(model.regimes)
    result: list[list[list[float]]] = []
    for t in range(len(observations) - 1):
        emissions, _ = _shifted_emissions(observations[t + 1], model.regimes)
        matrix = [[0.0] * states for _ in range(states)]
        total = 0.0
        for source in range(states):
            for target in range(states):
                value = (
                    alpha[t][source]
                    * model.transition[source][target]
                    * emissions[target]
                    * beta[t + 1][target]
                )
                matrix[source][target] = value
                total += value
        _require_positive_scale(total)
        result.append([[value / total for value in row] for row in matrix])
    return result


def _m_step(
    observations: Sequence[float],
    gamma: Sequence[Sequence[float]],
    xi: Sequence[Sequence[Sequence[float]]],
    config: RegimeHMMConfig,
) -> RegimeHMMModel:
    states = config.states
    initial = _normalize(tuple(gamma[0]))

    transition_rows: list[tuple[float, ...]] = []
    for source in range(states):
        numerators = []
        for target in range(states):
            count = sum(matrix[source][target] for matrix in xi)
            prior = config.transition_prior + (config.sticky_prior if source == target else 0.0)
            numerators.append(count + prior)
        transition_rows.append(_normalize(tuple(numerators)))

    regimes: list[GaussianRegime] = []
    for state in range(states):
        mass = sum(row[state] for row in gamma)
        if mass <= _EPSILON:
            raise StateSpaceError(
                "HMM state lost all posterior mass",
                context={"reason": "degenerate_hmm_state", "state": state},
            )
        mean = sum(row[state] * observation for row, observation in zip(gamma, observations)) / mass
        variance = sum(
            row[state] * (observation - mean) ** 2
            for row, observation in zip(gamma, observations)
        ) / mass
        regimes.append(
            GaussianRegime(
                index=state,
                mean_change=mean,
                variance_change=max(config.min_variance, variance),
            )
        )

    return RegimeHMMModel(
        regimes=tuple(regimes),
        transition=tuple(transition_rows),
        initial=initial,
    )


def _ordered_model(model: RegimeHMMModel) -> RegimeHMMModel:
    order = sorted(
        range(len(model.regimes)),
        key=lambda state: (
            model.regimes[state].mean_change,
            model.regimes[state].variance_change,
            state,
        ),
    )
    inverse = {old: new for new, old in enumerate(order)}
    del inverse
    regimes = tuple(
        GaussianRegime(
            index=new,
            mean_change=model.regimes[old].mean_change,
            variance_change=model.regimes[old].variance_change,
        )
        for new, old in enumerate(order)
    )
    initial = tuple(model.initial[old] for old in order)
    transition = tuple(
        tuple(model.transition[old_source][old_target] for old_target in order)
        for old_source in order
    )
    return RegimeHMMModel(regimes=regimes, transition=transition, initial=initial)


def _shifted_emissions(
    value: float,
    regimes: Sequence[GaussianRegime],
) -> tuple[tuple[float, ...], float]:
    """Return Gaussian emission weights after subtracting the largest log density.

    The common log offset is accumulated by the forward pass, so this preserves
    the exact sequence log likelihood while preventing all state densities from
    underflowing together on an extreme observation.
    """

    log_densities = tuple(
        _gaussian_log_density(value - regime.mean_change, regime.variance_change)
        for regime in regimes
    )
    maximum = max(log_densities)
    if not math.isfinite(maximum):
        raise StateSpaceError(
            "HMM emission log density is non-finite",
            context={"reason": "numerical_instability"},
        )
    weights = tuple(math.exp(log_density - maximum) for log_density in log_densities)
    if any(not math.isfinite(weight) or weight < 0.0 for weight in weights):
        raise StateSpaceError(
            "HMM shifted emission weight is invalid",
            context={"reason": "numerical_instability"},
        )
    if max(weights) != 1.0:
        raise StateSpaceError(
            "HMM shifted emissions lost their normalization anchor",
            context={"reason": "numerical_instability"},
        )
    return weights, maximum


def _gaussian_log_density(error: float, variance: float) -> float:
    variance = max(_EPSILON, variance)
    return -0.5 * (math.log(2.0 * math.pi * variance) + error * error / variance)


def _entropy(probabilities: Sequence[float]) -> float:
    return -sum(value * math.log(max(_EPSILON, value)) for value in probabilities)


def _normalize(values: Sequence[float]) -> tuple[float, ...]:
    total = sum(values)
    if not math.isfinite(total) or total <= _EPSILON:
        raise StateSpaceError(
            "probability normalization failed",
            context={"reason": "numerical_instability"},
        )
    return tuple(value / total for value in values)


def _validate_probability_vector(values: Sequence[float], *, field: str) -> None:
    if not values:
        raise StateSpaceError(
            "probability vector cannot be empty",
            context={"reason": "invalid_probability_vector", "field": field},
        )
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise StateSpaceError(
            "probabilities must be finite and non-negative",
            context={"reason": "invalid_probability_vector", "field": field},
        )
    if abs(sum(values) - 1.0) > 1e-8:
        raise StateSpaceError(
            "probability vector must sum to one",
            context={"reason": "invalid_probability_vector", "field": field},
        )


def _require_positive_scale(value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise StateSpaceError(
            "HMM forward/backward scale collapsed",
            context={"reason": "numerical_instability"},
        )


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "regime series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "regime series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "regime series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _fit_fingerprint(
    *,
    config: RegimeHMMConfig,
    values: Sequence[float],
    model: RegimeHMMModel,
    posteriors: Sequence[RegimePosteriorStep],
    log_likelihood: float,
    iterations: int,
    converged: bool,
) -> str:
    parts = [
        "jeeves-regime-hmm-v1",
        repr(config),
        ",".join(format(value, ".17g") for value in values),
        format(log_likelihood, ".17g"),
        str(iterations),
        str(converged),
        ",".join(format(value, ".17g") for value in model.initial),
    ]
    for regime in model.regimes:
        parts.extend(
            (
                str(regime.index),
                format(regime.mean_change, ".17g"),
                format(regime.variance_change, ".17g"),
            )
        )
    for row in model.transition:
        parts.append(",".join(format(value, ".17g") for value in row))
    for posterior in posteriors:
        parts.extend(
            (
                str(posterior.observation_index),
                ",".join(format(value, ".17g") for value in posterior.probabilities),
            )
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


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


__all__ = [
    "GaussianRegime",
    "RegimeForecast",
    "RegimeForecastComponent",
    "RegimeHMMConfig",
    "RegimeHMMFit",
    "RegimeHMMModel",
    "RegimePosteriorStep",
    "RegimePrequentialScore",
    "evaluate_regime_hmm_prequential",
    "fit_regime_hmm",
    "forecast_regime_hmm",
]
