"""Deterministic multiscale harmonic forecasting for Jeeves.

The model is intentionally offline and dependency-light.  It discovers periodic
structure only from the supplied training prefix, fits a robust ridge-regularized
harmonic regression, and exposes Gaussian predictive uncertainty derived from
both residual noise and coefficient uncertainty.

This is not a market-data adapter or trading surface.  It is an evaluation
primitive designed for leakage-safe historical forecasting experiments.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from .probabilistic_state_space import GaussianForecast, SeriesValues, StateSpaceError

_EPSILON = 1e-12
_TWO_PI = 2.0 * math.pi


@dataclass(frozen=True, slots=True)
class SpectralConfig:
    """Configuration for robust multiscale harmonic regression."""

    max_harmonics: int = 4
    min_period: float = 3.0
    max_period_fraction: float = 0.50
    frequency_separation_bins: int = 1
    ridge_penalty: float = 1e-6
    robust_iterations: int = 4
    huber_delta: float = 2.5
    min_variance: float = 1e-9
    include_trend: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_harmonics, bool)
            or not isinstance(self.max_harmonics, int)
            or not 0 <= self.max_harmonics <= 16
        ):
            raise StateSpaceError(
                "max_harmonics must be an integer between 0 and 16",
                context={"reason": "invalid_spectral_config", "field": "max_harmonics"},
            )
        _positive("min_period", self.min_period)
        if self.min_period < 2.0:
            raise StateSpaceError(
                "min_period must be >= 2",
                context={"reason": "invalid_spectral_config", "field": "min_period"},
            )
        fraction = _positive("max_period_fraction", self.max_period_fraction)
        if not 0.05 <= fraction <= 1.0:
            raise StateSpaceError(
                "max_period_fraction must be between 0.05 and 1",
                context={"reason": "invalid_spectral_config", "field": "max_period_fraction"},
            )
        if (
            isinstance(self.frequency_separation_bins, bool)
            or not isinstance(self.frequency_separation_bins, int)
            or self.frequency_separation_bins < 0
        ):
            raise StateSpaceError(
                "frequency_separation_bins must be a non-negative integer",
                context={"reason": "invalid_spectral_config", "field": "frequency_separation_bins"},
            )
        _non_negative("ridge_penalty", self.ridge_penalty)
        if (
            isinstance(self.robust_iterations, bool)
            or not isinstance(self.robust_iterations, int)
            or not 1 <= self.robust_iterations <= 20
        ):
            raise StateSpaceError(
                "robust_iterations must be an integer between 1 and 20",
                context={"reason": "invalid_spectral_config", "field": "robust_iterations"},
            )
        delta = _positive("huber_delta", self.huber_delta)
        if delta > 20.0:
            raise StateSpaceError(
                "huber_delta must be <= 20",
                context={"reason": "invalid_spectral_config", "field": "huber_delta"},
            )
        _positive("min_variance", self.min_variance)
        if not isinstance(self.include_trend, bool):
            raise StateSpaceError(
                "include_trend must be boolean",
                context={"reason": "invalid_spectral_config", "field": "include_trend"},
            )


@dataclass(frozen=True, slots=True)
class SpectralPeak:
    """One selected periodogram peak before regression."""

    bin_index: int
    frequency: float
    period: float
    normalized_power: float

    def __post_init__(self) -> None:
        if isinstance(self.bin_index, bool) or not isinstance(self.bin_index, int) or self.bin_index <= 0:
            raise StateSpaceError(
                "spectral bin index must be positive",
                context={"reason": "invalid_spectral_peak"},
            )
        _positive("frequency", self.frequency)
        _positive("period", self.period)
        _non_negative("normalized_power", self.normalized_power)


@dataclass(frozen=True, slots=True)
class HarmonicComponent:
    """Interpretable sinusoidal component fitted by the robust regression."""

    bin_index: int
    frequency: float
    period: float
    sine_coefficient: float
    cosine_coefficient: float
    amplitude: float
    phase: float
    discovery_power: float


@dataclass(frozen=True, slots=True)
class SpectralFit:
    """Immutable fitted multiscale harmonic model."""

    config: SpectralConfig
    observations: tuple[float, ...]
    center_time: float
    time_scale: float
    intercept: float
    trend: float
    peaks: tuple[SpectralPeak, ...]
    components: tuple[HarmonicComponent, ...]
    coefficients: tuple[float, ...]
    normal_matrix: tuple[tuple[float, ...], ...]
    residual_variance: float
    effective_sample_size: float
    robust_scale: float
    fingerprint: str

    @property
    def sample_count(self) -> int:
        return len(self.observations)

    @property
    def harmonic_count(self) -> int:
        return len(self.components)

    def forecast(self, horizon: int = 1) -> GaussianForecast:
        return forecast_spectral(self, horizon=horizon)

    def forecast_path(self, horizons: Iterable[int]) -> tuple[GaussianForecast, ...]:
        requested = tuple(horizons)
        if not requested:
            raise StateSpaceError(
                "at least one spectral forecast horizon is required",
                context={"reason": "empty_horizon_grid"},
            )
        if len(set(requested)) != len(requested):
            raise StateSpaceError(
                "spectral forecast horizons must be unique",
                context={"reason": "duplicate_horizon"},
            )
        return tuple(self.forecast(horizon) for horizon in requested)


@dataclass(frozen=True, slots=True)
class SpectralScore:
    """Leakage-safe prequential score for one harmonic complexity."""

    harmonics: int
    folds: int
    mean_log_score: float
    rmse: float
    mae: float
    coverage_95: float
    average_interval_width_95: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SpectralTournament:
    """Prequential comparison of harmonic complexities."""

    scores: tuple[SpectralScore, ...]
    ranking: tuple[int, ...]
    selected_harmonics: int
    fingerprint: str

    def by_harmonics(self, harmonics: int) -> SpectralScore:
        for score in self.scores:
            if score.harmonics == harmonics:
                return score
        raise StateSpaceError(
            "harmonic complexity was not evaluated",
            context={"reason": "missing_harmonic_complexity", "harmonics": harmonics},
        )


def discover_spectral_peaks(
    series: SeriesValues | Sequence[float],
    *,
    config: SpectralConfig | None = None,
) -> tuple[SpectralPeak, ...]:
    """Discover separated DFT-grid peaks from a detrended training prefix.

    The DFT is evaluated only on the supplied values. No target or suffix is
    inspected, making this safe to call independently inside walk-forward folds.
    """

    actual_config = config or SpectralConfig()
    values = _coerce_values(series)
    if len(values) < 8:
        raise StateSpaceError(
            "spectral discovery requires at least eight observations",
            context={"reason": "insufficient_history"},
        )
    if actual_config.max_harmonics == 0:
        return ()

    residuals = _linear_detrend(values, include_trend=actual_config.include_trend)
    energy = sum(value * value for value in residuals)
    if energy <= _EPSILON:
        return ()

    count = len(values)
    min_bin = max(1, int(math.ceil(1.0 / actual_config.max_period_fraction)))
    max_bin = min(
        count // 2,
        int(math.floor(count / actual_config.min_period)),
    )
    if max_bin < min_bin:
        return ()

    candidates: list[SpectralPeak] = []
    for bin_index in range(min_bin, max_bin + 1):
        frequency = bin_index / count
        sine_projection = 0.0
        cosine_projection = 0.0
        for index, residual in enumerate(residuals):
            angle = _TWO_PI * frequency * index
            sine_projection += residual * math.sin(angle)
            cosine_projection += residual * math.cos(angle)
        power = (sine_projection * sine_projection + cosine_projection * cosine_projection) / (
            max(_EPSILON, energy) * count
        )
        candidates.append(
            SpectralPeak(
                bin_index=bin_index,
                frequency=frequency,
                period=1.0 / frequency,
                normalized_power=max(0.0, power),
            )
        )

    ordered = sorted(candidates, key=lambda peak: (-peak.normalized_power, peak.bin_index))
    selected: list[SpectralPeak] = []
    separation = actual_config.frequency_separation_bins
    for peak in ordered:
        if any(abs(peak.bin_index - prior.bin_index) <= separation for prior in selected):
            continue
        selected.append(peak)
        if len(selected) >= actual_config.max_harmonics:
            break
    return tuple(sorted(selected, key=lambda peak: peak.frequency))


def fit_spectral_model(
    series: SeriesValues | Sequence[float],
    *,
    config: SpectralConfig | None = None,
) -> SpectralFit:
    """Fit robust ridge harmonic regression to one training prefix."""

    actual_config = config or SpectralConfig()
    values = _coerce_values(series)
    if len(values) < 8:
        raise StateSpaceError(
            "spectral fitting requires at least eight observations",
            context={"reason": "insufficient_history"},
        )

    peaks = discover_spectral_peaks(values, config=actual_config)
    center_time = (len(values) - 1.0) / 2.0
    time_scale = max(1.0, float(len(values)))
    design = tuple(
        _feature_vector(
            index,
            center_time=center_time,
            time_scale=time_scale,
            peaks=peaks,
            include_trend=actual_config.include_trend,
        )
        for index in range(len(values))
    )
    parameter_count = len(design[0])
    weights = [1.0] * len(values)
    coefficients: tuple[float, ...] = ()
    normal_matrix: tuple[tuple[float, ...], ...] = ()
    robust_scale = math.sqrt(actual_config.min_variance)

    for iteration in range(actual_config.robust_iterations):
        normal_matrix, rhs = _weighted_normal_equations(
            design,
            values,
            weights,
            ridge_penalty=actual_config.ridge_penalty,
        )
        coefficients = _solve_spd(normal_matrix, rhs)
        residuals = tuple(
            observed - _dot(row, coefficients)
            for row, observed in zip(design, values)
        )
        robust_scale = _robust_residual_scale(residuals, actual_config.min_variance)
        if iteration + 1 < actual_config.robust_iterations:
            cutoff = actual_config.huber_delta * robust_scale
            weights = [
                1.0 if abs(residual) <= cutoff else cutoff / max(abs(residual), _EPSILON)
                for residual in residuals
            ]

    residuals = tuple(
        observed - _dot(row, coefficients)
        for row, observed in zip(design, values)
    )
    effective_sample_size = sum(weights)
    denominator = max(1.0, effective_sample_size - parameter_count)
    residual_variance = max(
        actual_config.min_variance,
        sum(weight * residual * residual for weight, residual in zip(weights, residuals)) / denominator,
    )

    coefficient_offset = 1
    trend = 0.0
    if actual_config.include_trend:
        trend = coefficients[1] / time_scale
        coefficient_offset = 2

    components: list[HarmonicComponent] = []
    for component_index, peak in enumerate(peaks):
        sine_coefficient = coefficients[coefficient_offset + 2 * component_index]
        cosine_coefficient = coefficients[coefficient_offset + 2 * component_index + 1]
        components.append(
            HarmonicComponent(
                bin_index=peak.bin_index,
                frequency=peak.frequency,
                period=peak.period,
                sine_coefficient=sine_coefficient,
                cosine_coefficient=cosine_coefficient,
                amplitude=math.hypot(sine_coefficient, cosine_coefficient),
                phase=math.atan2(cosine_coefficient, sine_coefficient),
                discovery_power=peak.normalized_power,
            )
        )

    fingerprint = _fit_fingerprint(
        config=actual_config,
        values=values,
        peaks=peaks,
        coefficients=coefficients,
        residual_variance=residual_variance,
        robust_scale=robust_scale,
    )
    return SpectralFit(
        config=actual_config,
        observations=values,
        center_time=center_time,
        time_scale=time_scale,
        intercept=coefficients[0],
        trend=trend,
        peaks=peaks,
        components=tuple(components),
        coefficients=coefficients,
        normal_matrix=normal_matrix,
        residual_variance=residual_variance,
        effective_sample_size=effective_sample_size,
        robust_scale=robust_scale,
        fingerprint=fingerprint,
    )


def forecast_spectral(fit: SpectralFit, *, horizon: int = 1) -> GaussianForecast:
    """Forecast from a fitted harmonic model with parameter uncertainty."""

    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise StateSpaceError(
            "spectral forecast horizon must be a positive integer",
            context={"reason": "invalid_horizon"},
        )
    target_index = len(fit.observations) - 1 + horizon
    features = _feature_vector(
        target_index,
        center_time=fit.center_time,
        time_scale=fit.time_scale,
        peaks=fit.peaks,
        include_trend=fit.config.include_trend,
    )
    mean = _dot(features, fit.coefficients)
    parameter_solution = _solve_spd(fit.normal_matrix, features)
    leverage = max(0.0, _dot(features, parameter_solution))
    variance = max(
        fit.config.min_variance,
        fit.residual_variance * (1.0 + leverage),
    )
    return GaussianForecast(horizon=horizon, mean=mean, variance=variance)


def evaluate_spectral_complexities(
    series: SeriesValues | Sequence[float],
    *,
    min_train_size: int = 32,
    step: int = 1,
    max_harmonics: int | None = None,
    base_config: SpectralConfig | None = None,
) -> SpectralTournament:
    """Leakage-safe walk-forward tournament over harmonic complexities.

    For every target and complexity, frequency discovery and coefficient
    estimation run from scratch on the prefix strictly before that target.
    Ranking uses mean log score first, followed by RMSE, MAE, interval width,
    then smaller harmonic count as the deterministic complexity tie-break.
    """

    values = _coerce_values(series)
    if isinstance(min_train_size, bool) or not isinstance(min_train_size, int) or min_train_size < 8:
        raise StateSpaceError(
            "min_train_size must be an integer >= 8",
            context={"reason": "invalid_spectral_tournament_config"},
        )
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise StateSpaceError(
            "step must be a positive integer",
            context={"reason": "invalid_spectral_tournament_config"},
        )
    if len(values) <= min_train_size:
        raise StateSpaceError(
            "series is too short for spectral tournament",
            context={"reason": "insufficient_history"},
        )

    template = base_config or SpectralConfig()
    maximum = template.max_harmonics if max_harmonics is None else max_harmonics
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 0 <= maximum <= 16:
        raise StateSpaceError(
            "max_harmonics must be an integer between 0 and 16",
            context={"reason": "invalid_spectral_tournament_config"},
        )

    scores: list[SpectralScore] = []
    for harmonic_count in range(maximum + 1):
        config = _replace_harmonic_count(template, harmonic_count)
        absolute_errors: list[float] = []
        squared_errors: list[float] = []
        log_scores: list[float] = []
        coverage: list[float] = []
        widths: list[float] = []

        for target_index in range(min_train_size, len(values), step):
            fit = fit_spectral_model(values[:target_index], config=config)
            forecast = fit.forecast(1)
            actual = values[target_index]
            error = forecast.mean - actual
            absolute_errors.append(abs(error))
            squared_errors.append(error * error)
            log_scores.append(forecast.log_density(actual))
            lower, upper = forecast.interval()
            coverage.append(1.0 if lower <= actual <= upper else 0.0)
            widths.append(upper - lower)

        fingerprint = _score_fingerprint(
            harmonics=harmonic_count,
            log_scores=log_scores,
            absolute_errors=absolute_errors,
            squared_errors=squared_errors,
            coverage=coverage,
            widths=widths,
        )
        scores.append(
            SpectralScore(
                harmonics=harmonic_count,
                folds=len(log_scores),
                mean_log_score=statistics.fmean(log_scores),
                rmse=math.sqrt(statistics.fmean(squared_errors)),
                mae=statistics.fmean(absolute_errors),
                coverage_95=statistics.fmean(coverage),
                average_interval_width_95=statistics.fmean(widths),
                fingerprint=fingerprint,
            )
        )

    ranking = tuple(
        score.harmonics
        for score in sorted(
            scores,
            key=lambda score: (
                -score.mean_log_score,
                score.rmse,
                score.mae,
                score.average_interval_width_95,
                score.harmonics,
            ),
        )
    )
    tournament_fingerprint = hashlib.sha256(
        "|".join(
            (
                "jeeves-spectral-tournament-v1",
                repr(template),
                str(min_train_size),
                str(step),
                ",".join(str(value) for value in ranking),
                *(score.fingerprint for score in scores),
            )
        ).encode("utf-8")
    ).hexdigest()
    return SpectralTournament(
        scores=tuple(scores),
        ranking=ranking,
        selected_harmonics=ranking[0],
        fingerprint=tournament_fingerprint,
    )


def _replace_harmonic_count(config: SpectralConfig, count: int) -> SpectralConfig:
    return SpectralConfig(
        max_harmonics=count,
        min_period=config.min_period,
        max_period_fraction=config.max_period_fraction,
        frequency_separation_bins=config.frequency_separation_bins,
        ridge_penalty=config.ridge_penalty,
        robust_iterations=config.robust_iterations,
        huber_delta=config.huber_delta,
        min_variance=config.min_variance,
        include_trend=config.include_trend,
    )


def _feature_vector(
    index: int,
    *,
    center_time: float,
    time_scale: float,
    peaks: Sequence[SpectralPeak],
    include_trend: bool,
) -> tuple[float, ...]:
    features = [1.0]
    if include_trend:
        features.append((index - center_time) / time_scale)
    for peak in peaks:
        angle = _TWO_PI * peak.frequency * index
        features.extend((math.sin(angle), math.cos(angle)))
    return tuple(features)


def _linear_detrend(values: Sequence[float], *, include_trend: bool) -> tuple[float, ...]:
    mean = statistics.fmean(values)
    if not include_trend or len(values) < 2:
        return tuple(value - mean for value in values)
    center = (len(values) - 1.0) / 2.0
    denominator = sum((index - center) ** 2 for index in range(len(values)))
    if denominator <= _EPSILON:
        return tuple(value - mean for value in values)
    slope = sum((index - center) * (value - mean) for index, value in enumerate(values)) / denominator
    return tuple(
        value - (mean + slope * (index - center))
        for index, value in enumerate(values)
    )


def _weighted_normal_equations(
    design: Sequence[Sequence[float]],
    values: Sequence[float],
    weights: Sequence[float],
    *,
    ridge_penalty: float,
) -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]:
    columns = len(design[0])
    matrix = [[0.0] * columns for _ in range(columns)]
    rhs = [0.0] * columns
    for row, observed, weight in zip(design, values, weights):
        for left in range(columns):
            weighted_left = weight * row[left]
            rhs[left] += weighted_left * observed
            for right in range(left, columns):
                matrix[left][right] += weighted_left * row[right]
    for left in range(columns):
        for right in range(left):
            matrix[left][right] = matrix[right][left]
        if left > 0:
            matrix[left][left] += ridge_penalty
    jitter = max(_EPSILON, ridge_penalty * 1e-6)
    for index in range(columns):
        matrix[index][index] += jitter
    return tuple(tuple(row) for row in matrix), tuple(rhs)


def _solve_spd(
    matrix: Sequence[Sequence[float]],
    rhs: Sequence[float],
) -> tuple[float, ...]:
    """Solve a symmetric positive-definite system with Cholesky factorization."""

    size = len(matrix)
    if size == 0 or len(rhs) != size or any(len(row) != size for row in matrix):
        raise StateSpaceError(
            "spectral linear system has invalid shape",
            context={"reason": "invalid_linear_system"},
        )
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            subtotal = sum(lower[row][k] * lower[column][k] for k in range(column))
            if row == column:
                diagonal = matrix[row][row] - subtotal
                if not math.isfinite(diagonal) or diagonal <= _EPSILON:
                    raise StateSpaceError(
                        "spectral normal matrix is not positive definite",
                        context={"reason": "numerical_instability"},
                    )
                lower[row][column] = math.sqrt(diagonal)
            else:
                lower[row][column] = (matrix[row][column] - subtotal) / lower[column][column]

    forward = [0.0] * size
    for row in range(size):
        forward[row] = (
            rhs[row] - sum(lower[row][column] * forward[column] for column in range(row))
        ) / lower[row][row]

    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        solution[row] = (
            forward[row]
            - sum(lower[column][row] * solution[column] for column in range(row + 1, size))
        ) / lower[row][row]
    if any(not math.isfinite(value) for value in solution):
        raise StateSpaceError(
            "spectral linear solve produced non-finite coefficients",
            context={"reason": "numerical_instability"},
        )
    return tuple(solution)


def _robust_residual_scale(residuals: Sequence[float], min_variance: float) -> float:
    median = float(statistics.median(residuals))
    mad = float(statistics.median(abs(value - median) for value in residuals))
    scale = 1.4826 * mad
    if scale <= _EPSILON:
        scale = math.sqrt(max(min_variance, statistics.fmean(value * value for value in residuals)))
    return max(math.sqrt(min_variance), scale)


def _fit_fingerprint(
    *,
    config: SpectralConfig,
    values: Sequence[float],
    peaks: Sequence[SpectralPeak],
    coefficients: Sequence[float],
    residual_variance: float,
    robust_scale: float,
) -> str:
    parts = [
        "jeeves-spectral-fit-v1",
        repr(config),
        ",".join(format(value, ".17g") for value in values),
        ",".join(str(peak.bin_index) for peak in peaks),
        ",".join(format(value, ".17g") for value in coefficients),
        format(residual_variance, ".17g"),
        format(robust_scale, ".17g"),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _score_fingerprint(
    *,
    harmonics: int,
    log_scores: Sequence[float],
    absolute_errors: Sequence[float],
    squared_errors: Sequence[float],
    coverage: Sequence[float],
    widths: Sequence[float],
) -> str:
    parts = [
        "jeeves-spectral-score-v1",
        str(harmonics),
        ",".join(format(value, ".17g") for value in log_scores),
        ",".join(format(value, ".17g") for value in absolute_errors),
        ",".join(format(value, ".17g") for value in squared_errors),
        ",".join(format(value, ".17g") for value in coverage),
        ",".join(format(value, ".17g") for value in widths),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _coerce_values(series: SeriesValues | Sequence[float]) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "spectral series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "spectral series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "spectral series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


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
    "HarmonicComponent",
    "SpectralConfig",
    "SpectralFit",
    "SpectralPeak",
    "SpectralScore",
    "SpectralTournament",
    "discover_spectral_peaks",
    "evaluate_spectral_complexities",
    "fit_spectral_model",
    "forecast_spectral",
]
