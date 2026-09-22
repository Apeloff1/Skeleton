"""Leakage-safe joint trajectory evidence for Jeeves multi-horizon forecasts.

Jeeves already produces well-scored marginal predictive distributions for each
forecast horizon and measures empirical cross-horizon error dependence.  Those
objects do not, by themselves, define a joint path distribution.  This module
adds an explicit empirical-residual scenario layer without pretending otherwise.

For a forecast issued at origin ``t`` the scenario library contains only older
aligned forecast-error vectors whose *latest* target matured strictly before
``t``.  Standardized residual vectors are clipped for robustness, optionally
centered, optionally rescaled to unit weighted dispersion, and then transported
onto the current horizon-specific predictive means and standard deviations.
The complete residual vector is transported as one object, preserving empirical
cross-horizon dependence rather than independently resampling each horizon.

Historical joint forecasts are evaluated with the multivariate energy score and
variogram score.  Both are proper-scoring evidence for the scenario distribution;
they are not authorization for live action.  The transported scenarios preserve
current marginal first/second moments under the default centering/normalization
policy, but they do not claim to reproduce the exact heterogeneous marginal
densities of the underlying cross-family mixtures.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from .probabilistic_horizon_integrity import validate_multihorizon_report
from .probabilistic_horizons import (
    HorizonForecast,
    HorizonLadder,
    HorizonSettlement,
    MultiHorizonReport,
    _ladder_fingerprint,
)
from .probabilistic_state_space import StateSpaceError

_EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class JointPathConfig:
    """Controls empirical residual-path construction and scoring."""

    min_history: int = 12
    history_window: int = 96
    recency_decay: float = 0.985
    center_residuals: bool = True
    normalize_residual_dispersion: bool = True
    standardized_clip: float = 8.0
    min_scale: float = 1e-8
    variogram_power: float = 0.5

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_history, bool)
            or not isinstance(self.min_history, int)
            or self.min_history < 4
        ):
            raise StateSpaceError(
                "min_history must be an integer >= 4",
                context={"reason": "invalid_joint_path_config", "field": "min_history"},
            )
        if (
            isinstance(self.history_window, bool)
            or not isinstance(self.history_window, int)
            or self.history_window < self.min_history
        ):
            raise StateSpaceError(
                "history_window must be >= min_history",
                context={
                    "reason": "invalid_joint_path_config",
                    "field": "history_window",
                },
            )
        _open_closed_interval("recency_decay", self.recency_decay, 0.0, 1.0)
        if not isinstance(self.center_residuals, bool):
            raise StateSpaceError(
                "center_residuals must be boolean",
                context={
                    "reason": "invalid_joint_path_config",
                    "field": "center_residuals",
                },
            )
        if not isinstance(self.normalize_residual_dispersion, bool):
            raise StateSpaceError(
                "normalize_residual_dispersion must be boolean",
                context={
                    "reason": "invalid_joint_path_config",
                    "field": "normalize_residual_dispersion",
                },
            )
        _positive("standardized_clip", self.standardized_clip)
        _positive("min_scale", self.min_scale)
        power = _positive("variogram_power", self.variogram_power)
        if power > 2.0:
            raise StateSpaceError(
                "variogram_power must be <= 2",
                context={
                    "reason": "invalid_joint_path_config",
                    "field": "variogram_power",
                },
            )


@dataclass(frozen=True, slots=True)
class ResidualPath:
    """One fully matured aligned standardized-error vector."""

    origin_cutoff: int
    target_indices: tuple[int, ...]
    standardized_errors: tuple[float, ...]

    def __post_init__(self) -> None:
        _positive_integer("origin_cutoff", self.origin_cutoff)
        if not self.target_indices or len(self.target_indices) != len(
            self.standardized_errors
        ):
            raise StateSpaceError(
                "residual path geometry is inconsistent",
                context={"reason": "invalid_residual_path"},
            )
        previous = self.origin_cutoff - 1
        for target in self.target_indices:
            if isinstance(target, bool) or not isinstance(target, int) or target < 1:
                raise StateSpaceError(
                    "residual target indices must be positive integers",
                    context={"reason": "invalid_residual_path"},
                )
            if target <= previous:
                raise StateSpaceError(
                    "residual target indices must be strictly increasing",
                    context={"reason": "invalid_residual_path"},
                )
            previous = target
        for value in self.standardized_errors:
            _finite("standardized_error", value)

    @property
    def maturity_index(self) -> int:
        return self.target_indices[-1]


@dataclass(frozen=True, slots=True)
class JointPathScenario:
    """One weighted future trajectory transported from a residual path."""

    source_origin_cutoff: int
    weight: float
    standardized_residuals: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        _positive_integer("source_origin_cutoff", self.source_origin_cutoff)
        weight = _finite("scenario_weight", self.weight)
        if weight <= 0.0 or weight > 1.0:
            raise StateSpaceError(
                "scenario weight must lie in (0, 1]",
                context={"reason": "invalid_joint_path_scenario"},
            )
        if not self.values or len(self.values) != len(self.standardized_residuals):
            raise StateSpaceError(
                "scenario dimensions are inconsistent",
                context={"reason": "invalid_joint_path_scenario"},
            )
        for value in self.standardized_residuals:
            _finite("scenario_standardized_residual", value)
        for value in self.values:
            _finite("scenario_value", value)


@dataclass(frozen=True, slots=True)
class JointPathForecast:
    """A deterministic weighted empirical distribution over future paths."""

    origin_cutoff: int
    horizons: tuple[int, ...]
    target_indices: tuple[int, ...]
    marginal_means: tuple[float, ...]
    marginal_variances: tuple[float, ...]
    residual_location: tuple[float, ...]
    residual_dispersion: tuple[float, ...]
    scenarios: tuple[JointPathScenario, ...]
    covariance: tuple[tuple[float, ...], ...]
    correlation: tuple[tuple[float, ...], ...]
    effective_history_size: float
    source_configuration_fingerprint: str
    source_report_fingerprint: str | None
    fingerprint: str

    def __post_init__(self) -> None:
        _positive_integer("origin_cutoff", self.origin_cutoff)
        _validate_horizons(self.horizons)
        dimensions = len(self.horizons)
        if dimensions < 2:
            raise StateSpaceError(
                "joint path forecast requires at least two horizons",
                context={"reason": "insufficient_joint_dimensions"},
            )
        expected_targets = tuple(
            self.origin_cutoff + horizon - 1 for horizon in self.horizons
        )
        if self.target_indices != expected_targets:
            raise StateSpaceError(
                "joint path target indices disagree with horizons",
                context={"reason": "invalid_joint_path_geometry"},
            )
        for values, field in (
            (self.marginal_means, "marginal_means"),
            (self.marginal_variances, "marginal_variances"),
            (self.residual_location, "residual_location"),
            (self.residual_dispersion, "residual_dispersion"),
        ):
            if len(values) != dimensions:
                raise StateSpaceError(
                    f"{field} must match horizon count",
                    context={"reason": "invalid_joint_path_geometry", "field": field},
                )
            for value in values:
                _finite(field, value)
        if any(value <= 0.0 for value in self.marginal_variances):
            raise StateSpaceError(
                "marginal variances must be positive",
                context={"reason": "invalid_joint_path_geometry"},
            )
        if any(value <= 0.0 for value in self.residual_dispersion):
            raise StateSpaceError(
                "residual dispersions must be positive",
                context={"reason": "invalid_joint_path_geometry"},
            )
        if not self.scenarios:
            raise StateSpaceError(
                "joint path forecast requires scenarios",
                context={"reason": "empty_joint_path_forecast"},
            )
        if any(len(item.values) != dimensions for item in self.scenarios):
            raise StateSpaceError(
                "scenario dimension disagrees with horizon count",
                context={"reason": "invalid_joint_path_geometry"},
            )
        if not math.isclose(
            sum(item.weight for item in self.scenarios),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise StateSpaceError(
                "scenario weights must sum to one",
                context={"reason": "invalid_joint_path_weights"},
            )
        _validate_matrix("covariance", self.covariance, dimensions)
        _validate_matrix("correlation", self.correlation, dimensions)
        for left in range(dimensions):
            if self.covariance[left][left] < -1e-12:
                raise StateSpaceError(
                    "scenario covariance diagonal must be non-negative",
                    context={"reason": "invalid_joint_path_covariance"},
                )
            for right in range(dimensions):
                if not math.isclose(
                    self.covariance[left][right],
                    self.covariance[right][left],
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    raise StateSpaceError(
                        "scenario covariance must be symmetric",
                        context={"reason": "invalid_joint_path_covariance"},
                    )
                if not -1.0 <= self.correlation[left][right] <= 1.0:
                    raise StateSpaceError(
                        "scenario correlation must lie in [-1, 1]",
                        context={"reason": "invalid_joint_path_correlation"},
                    )
        size = _finite("effective_history_size", self.effective_history_size)
        if size < 1.0 or size > len(self.scenarios) + 1e-9:
            raise StateSpaceError(
                "effective history size is inconsistent with scenario weights",
                context={"reason": "invalid_joint_path_history"},
            )
        _sha256(
            "source_configuration_fingerprint",
            self.source_configuration_fingerprint,
        )
        if self.source_report_fingerprint is not None:
            _sha256("source_report_fingerprint", self.source_report_fingerprint)
        _sha256("fingerprint", self.fingerprint)

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    @property
    def expected_path(self) -> tuple[float, ...]:
        return tuple(
            sum(item.weight * item.values[index] for item in self.scenarios)
            for index in range(len(self.horizons))
        )


@dataclass(frozen=True, slots=True)
class JointPathStep:
    """One historical joint forecast scored after every horizon matured."""

    actuals: tuple[float, ...]
    forecast: JointPathForecast
    energy_score: float
    variogram_score: float

    def __post_init__(self) -> None:
        if len(self.actuals) != len(self.forecast.horizons):
            raise StateSpaceError(
                "joint path actual vector has the wrong dimension",
                context={"reason": "invalid_joint_path_step"},
            )
        for value in self.actuals:
            _finite("joint_actual", value)
        if _finite("energy_score", self.energy_score) < 0.0:
            raise StateSpaceError(
                "energy score must be non-negative",
                context={"reason": "invalid_joint_path_step"},
            )
        if _finite("variogram_score", self.variogram_score) < 0.0:
            raise StateSpaceError(
                "variogram score must be non-negative",
                context={"reason": "invalid_joint_path_step"},
            )

    @property
    def origin_cutoff(self) -> int:
        return self.forecast.origin_cutoff


@dataclass(frozen=True, slots=True)
class JointPathReport:
    """Prequential multivariate scenario evidence over historical origins."""

    config: JointPathConfig
    configuration_fingerprint: str
    source_report_fingerprint: str
    source_configuration_fingerprint: str
    horizons: tuple[int, ...]
    steps: tuple[JointPathStep, ...]
    mean_energy_score: float
    mean_variogram_score: float
    fingerprint: str

    def __post_init__(self) -> None:
        _sha256("configuration_fingerprint", self.configuration_fingerprint)
        _sha256("source_report_fingerprint", self.source_report_fingerprint)
        _sha256(
            "source_configuration_fingerprint",
            self.source_configuration_fingerprint,
        )
        _validate_horizons(self.horizons)
        if len(self.horizons) < 2:
            raise StateSpaceError(
                "joint path report requires at least two horizons",
                context={"reason": "insufficient_joint_dimensions"},
            )
        if not self.steps:
            raise StateSpaceError(
                "joint path report requires scored steps",
                context={"reason": "empty_joint_path_report"},
            )
        if any(step.forecast.horizons != self.horizons for step in self.steps):
            raise StateSpaceError(
                "joint path report contains foreign horizon geometry",
                context={"reason": "joint_path_horizon_mismatch"},
            )
        if _finite("mean_energy_score", self.mean_energy_score) < 0.0:
            raise StateSpaceError(
                "mean energy score must be non-negative",
                context={"reason": "invalid_joint_path_report"},
            )
        if _finite("mean_variogram_score", self.mean_variogram_score) < 0.0:
            raise StateSpaceError(
                "mean variogram score must be non-negative",
                context={"reason": "invalid_joint_path_report"},
            )
        _sha256("fingerprint", self.fingerprint)


def evaluate_joint_paths(
    report: MultiHorizonReport,
    *,
    config: JointPathConfig | None = None,
) -> JointPathReport:
    """Evaluate residual-transport path scenarios without target-time leakage."""

    validate_multihorizon_report(report)
    config = config or JointPathConfig()
    horizons = report.config.horizons
    if len(horizons) < 2:
        raise StateSpaceError(
            "joint path evaluation requires at least two horizons",
            context={"reason": "insufficient_joint_dimensions"},
        )
    aligned = _aligned_settlements(report)
    if len(aligned) <= config.min_history:
        raise StateSpaceError(
            "not enough aligned residual paths for joint evaluation",
            context={
                "reason": "insufficient_joint_path_history",
                "required": config.min_history + 1,
                "actual": len(aligned),
            },
        )

    configuration_fingerprint = _configuration_fingerprint(
        config=config,
        source_configuration_fingerprint=report.configuration_fingerprint,
    )
    steps: list[JointPathStep] = []
    for origin, settlements in aligned:
        eligible = tuple(
            item
            for item in aligned
            if item[0] < origin and _maturity_index(item[1]) < origin
        )
        if len(eligible) < config.min_history:
            continue
        history = eligible[-config.history_window :]
        forecasts = tuple(step.forecast for step in settlements)
        forecast = _build_forecast(
            origin_cutoff=origin,
            forecasts=forecasts,
            history=history,
            config=config,
            source_configuration_fingerprint=report.configuration_fingerprint,
            source_report_fingerprint=None,
        )
        actuals = tuple(step.actual for step in settlements)
        step = JointPathStep(
            actuals=actuals,
            forecast=forecast,
            energy_score=energy_score(forecast, actuals),
            variogram_score=variogram_score(
                forecast,
                actuals,
                power=config.variogram_power,
            ),
        )
        steps.append(step)

    if not steps:
        raise StateSpaceError(
            "joint path evaluation produced no leakage-safe scored origins",
            context={"reason": "insufficient_joint_path_history"},
        )
    result = tuple(steps)
    fingerprint = _report_fingerprint(
        configuration_fingerprint=configuration_fingerprint,
        source_report_fingerprint=report.fingerprint,
        horizons=horizons,
        steps=result,
    )
    return JointPathReport(
        config=config,
        configuration_fingerprint=configuration_fingerprint,
        source_report_fingerprint=report.fingerprint,
        source_configuration_fingerprint=report.configuration_fingerprint,
        horizons=horizons,
        steps=result,
        mean_energy_score=statistics.fmean(step.energy_score for step in result),
        mean_variogram_score=statistics.fmean(
            step.variogram_score for step in result
        ),
        fingerprint=fingerprint,
    )


def forecast_joint_path(
    ladder: HorizonLadder,
    report: MultiHorizonReport,
    *,
    config: JointPathConfig | None = None,
) -> JointPathForecast:
    """Transport fully matured historical residual paths onto a future ladder."""

    validate_multihorizon_report(report)
    config = config or JointPathConfig()
    _validate_ladder(ladder, report)
    aligned = _aligned_settlements(report)
    eligible = tuple(
        item for item in aligned if _maturity_index(item[1]) < ladder.origin_cutoff
    )
    if len(eligible) < config.min_history:
        raise StateSpaceError(
            "not enough matured residual paths for future joint forecast",
            context={
                "reason": "insufficient_joint_path_history",
                "required": config.min_history,
                "actual": len(eligible),
            },
        )
    history = eligible[-config.history_window :]
    return _build_forecast(
        origin_cutoff=ladder.origin_cutoff,
        forecasts=ladder.forecasts,
        history=history,
        config=config,
        source_configuration_fingerprint=report.configuration_fingerprint,
        source_report_fingerprint=report.fingerprint,
    )


def validate_joint_path_report(report: JointPathReport) -> JointPathReport:
    """Recompute proper scores and fingerprints for a joint evidence report."""

    if not isinstance(report, JointPathReport):
        raise StateSpaceError(
            "report must be a JointPathReport",
            context={"reason": "invalid_joint_path_report"},
        )
    expected_configuration = _configuration_fingerprint(
        config=report.config,
        source_configuration_fingerprint=report.source_configuration_fingerprint,
    )
    if report.configuration_fingerprint != expected_configuration:
        raise StateSpaceError(
            "joint path configuration fingerprint mismatch",
            context={"reason": "joint_path_report_identity_mismatch"},
        )
    previous_origin: int | None = None
    for step in report.steps:
        if previous_origin is not None and step.origin_cutoff <= previous_origin:
            raise StateSpaceError(
                "joint path report origins must be strictly increasing",
                context={"reason": "joint_path_report_order_mismatch"},
            )
        previous_origin = step.origin_cutoff
        _validate_forecast_identity(step.forecast)
        expected_energy = energy_score(step.forecast, step.actuals)
        expected_variogram = variogram_score(
            step.forecast,
            step.actuals,
            power=report.config.variogram_power,
        )
        _close_or_raise(
            "energy_score",
            step.energy_score,
            expected_energy,
            reason="joint_path_score_mismatch",
        )
        _close_or_raise(
            "variogram_score",
            step.variogram_score,
            expected_variogram,
            reason="joint_path_score_mismatch",
        )
    expected_energy_mean = statistics.fmean(
        step.energy_score for step in report.steps
    )
    expected_variogram_mean = statistics.fmean(
        step.variogram_score for step in report.steps
    )
    _close_or_raise(
        "mean_energy_score",
        report.mean_energy_score,
        expected_energy_mean,
        reason="joint_path_summary_mismatch",
    )
    _close_or_raise(
        "mean_variogram_score",
        report.mean_variogram_score,
        expected_variogram_mean,
        reason="joint_path_summary_mismatch",
    )
    expected_report = _report_fingerprint(
        configuration_fingerprint=report.configuration_fingerprint,
        source_report_fingerprint=report.source_report_fingerprint,
        horizons=report.horizons,
        steps=report.steps,
    )
    if report.fingerprint != expected_report:
        raise StateSpaceError(
            "joint path report fingerprint mismatch",
            context={"reason": "joint_path_report_identity_mismatch"},
        )
    return report


def energy_score(
    forecast: JointPathForecast,
    actuals: Sequence[float],
) -> float:
    """Weighted multivariate energy score for a discrete scenario forecast."""

    actual = _coerce_vector(actuals, dimensions=len(forecast.horizons), field="actual")
    first = sum(
        scenario.weight * _euclidean_distance(scenario.values, actual)
        for scenario in forecast.scenarios
    )
    pair = 0.0
    for left in forecast.scenarios:
        for right in forecast.scenarios:
            pair += (
                left.weight
                * right.weight
                * _euclidean_distance(left.values, right.values)
            )
    return max(0.0, first - 0.5 * pair)


def variogram_score(
    forecast: JointPathForecast,
    actuals: Sequence[float],
    *,
    power: float = 0.5,
) -> float:
    """Equal-pair-weight variogram score for cross-horizon path structure."""

    power = _positive("power", power)
    if power > 2.0:
        raise StateSpaceError(
            "variogram power must be <= 2",
            context={"reason": "invalid_variogram_power"},
        )
    actual = _coerce_vector(actuals, dimensions=len(forecast.horizons), field="actual")
    total = 0.0
    pairs = 0
    for left in range(len(actual)):
        for right in range(left + 1, len(actual)):
            observed = abs(actual[left] - actual[right]) ** power
            expected = sum(
                scenario.weight
                * abs(scenario.values[left] - scenario.values[right]) ** power
                for scenario in forecast.scenarios
            )
            total += (observed - expected) ** 2
            pairs += 1
    return 0.0 if pairs == 0 else total / pairs


def _build_forecast(
    *,
    origin_cutoff: int,
    forecasts: Sequence[HorizonForecast],
    history: Sequence[tuple[int, tuple[HorizonSettlement, ...]]],
    config: JointPathConfig,
    source_configuration_fingerprint: str,
    source_report_fingerprint: str | None,
) -> JointPathForecast:
    if not forecasts:
        raise StateSpaceError(
            "joint path forecast requires marginal forecasts",
            context={"reason": "empty_joint_marginals"},
        )
    horizons = tuple(item.horizon for item in forecasts)
    _validate_horizons(horizons)
    if len(horizons) < 2:
        raise StateSpaceError(
            "joint path forecast requires at least two horizons",
            context={"reason": "insufficient_joint_dimensions"},
        )
    if any(item.origin_cutoff != origin_cutoff for item in forecasts):
        raise StateSpaceError(
            "joint marginal forecasts must share one origin cutoff",
            context={"reason": "joint_path_origin_mismatch"},
        )
    target_indices = tuple(item.target_index for item in forecasts)
    means = tuple(item.predictive.mean for item in forecasts)
    variances = tuple(item.predictive.variance for item in forecasts)
    scales = tuple(max(config.min_scale, math.sqrt(value)) for value in variances)

    residual_paths = tuple(
        _residual_path(
            origin=source_origin,
            settlements=settlements,
            config=config,
        )
        for source_origin, settlements in history
    )
    if len(residual_paths) < config.min_history:
        raise StateSpaceError(
            "joint path history is below configured minimum",
            context={"reason": "insufficient_joint_path_history"},
        )
    if any(path.maturity_index >= origin_cutoff for path in residual_paths):
        raise StateSpaceError(
            "joint path history contains a residual vector not mature at issue time",
            context={"reason": "joint_path_temporal_leakage"},
        )

    weights = _recency_weights(len(residual_paths), config.recency_decay)
    location = tuple(
        sum(
            weight * path.standardized_errors[index]
            for weight, path in zip(weights, residual_paths)
        )
        for index in range(len(horizons))
    )
    centered = tuple(
        tuple(
            value - (location[index] if config.center_residuals else 0.0)
            for index, value in enumerate(path.standardized_errors)
        )
        for path in residual_paths
    )
    dispersion = tuple(
        max(
            config.min_scale,
            math.sqrt(
                sum(
                    weight * vector[index] * vector[index]
                    for weight, vector in zip(weights, centered)
                )
            ),
        )
        for index in range(len(horizons))
    )
    transformed = tuple(
        tuple(
            value / dispersion[index]
            if config.normalize_residual_dispersion
            else value
            for index, value in enumerate(vector)
        )
        for vector in centered
    )
    scenarios = tuple(
        JointPathScenario(
            source_origin_cutoff=path.origin_cutoff,
            weight=weight,
            standardized_residuals=vector,
            values=tuple(
                mean + scale * residual
                for mean, scale, residual in zip(means, scales, vector)
            ),
        )
        for path, vector, weight in zip(residual_paths, transformed, weights)
    )
    covariance = _weighted_covariance(scenarios)
    correlation = _covariance_to_correlation(covariance)
    effective_history_size = 1.0 / sum(weight * weight for weight in weights)
    fingerprint = _forecast_fingerprint(
        origin_cutoff=origin_cutoff,
        horizons=horizons,
        target_indices=target_indices,
        marginal_means=means,
        marginal_variances=variances,
        residual_location=location,
        residual_dispersion=dispersion,
        scenarios=scenarios,
        covariance=covariance,
        correlation=correlation,
        source_configuration_fingerprint=source_configuration_fingerprint,
        source_report_fingerprint=source_report_fingerprint,
    )
    return JointPathForecast(
        origin_cutoff=origin_cutoff,
        horizons=horizons,
        target_indices=target_indices,
        marginal_means=means,
        marginal_variances=variances,
        residual_location=location,
        residual_dispersion=dispersion,
        scenarios=scenarios,
        covariance=covariance,
        correlation=correlation,
        effective_history_size=effective_history_size,
        source_configuration_fingerprint=source_configuration_fingerprint,
        source_report_fingerprint=source_report_fingerprint,
        fingerprint=fingerprint,
    )


def _residual_path(
    *,
    origin: int,
    settlements: Sequence[HorizonSettlement],
    config: JointPathConfig,
) -> ResidualPath:
    if not settlements:
        raise StateSpaceError(
            "residual path requires settlements",
            context={"reason": "empty_residual_path"},
        )
    if any(step.origin_cutoff != origin for step in settlements):
        raise StateSpaceError(
            "residual path settlements must share one origin",
            context={"reason": "residual_path_origin_mismatch"},
        )
    target_indices = tuple(step.target_index for step in settlements)
    residuals = []
    for step in settlements:
        scale = max(config.min_scale, math.sqrt(step.forecast.predictive.variance))
        standardized = step.signed_error / scale
        standardized = min(
            config.standardized_clip,
            max(-config.standardized_clip, standardized),
        )
        residuals.append(standardized)
    return ResidualPath(
        origin_cutoff=origin,
        target_indices=target_indices,
        standardized_errors=tuple(residuals),
    )


def _aligned_settlements(
    report: MultiHorizonReport,
) -> tuple[tuple[int, tuple[HorizonSettlement, ...]], ...]:
    maps = {
        summary.horizon: {
            step.origin_cutoff: step for step in summary.settlements
        }
        for summary in report.summaries
    }
    common = set.intersection(*(set(values) for values in maps.values()))
    result = []
    for origin in sorted(common):
        settlements = tuple(maps[horizon][origin] for horizon in report.config.horizons)
        result.append((origin, settlements))
    return tuple(result)


def _maturity_index(settlements: Sequence[HorizonSettlement]) -> int:
    return max(step.target_index for step in settlements)


def _validate_ladder(ladder: HorizonLadder, report: MultiHorizonReport) -> None:
    if not isinstance(ladder, HorizonLadder):
        raise StateSpaceError(
            "ladder must be a HorizonLadder",
            context={"reason": "invalid_horizon_ladder"},
        )
    if ladder.source_report_fingerprint != report.fingerprint:
        raise StateSpaceError(
            "horizon ladder belongs to a different source report",
            context={"reason": "joint_path_source_mismatch"},
        )
    horizons = tuple(item.horizon for item in ladder.forecasts)
    if horizons != report.config.horizons:
        raise StateSpaceError(
            "horizon ladder geometry differs from source report",
            context={"reason": "joint_path_horizon_mismatch"},
        )
    expected_fingerprint = _ladder_fingerprint(
        source_report_fingerprint=ladder.source_report_fingerprint,
        origin_cutoff=ladder.origin_cutoff,
        forecasts=ladder.forecasts,
    )
    if ladder.fingerprint != expected_fingerprint:
        raise StateSpaceError(
            "horizon ladder fingerprint mismatch",
            context={"reason": "joint_path_ladder_identity_mismatch"},
        )
    latest_target = max(
        step.target_index
        for summary in report.summaries
        for step in summary.settlements
    )
    if ladder.origin_cutoff <= latest_target:
        raise StateSpaceError(
            "future ladder cutoff must be after all source-report targets matured",
            context={"reason": "joint_path_ladder_temporal_leakage"},
        )
    for item in ladder.forecasts:
        expected_weights = dict(report.summary_for(item.horizon).final_weights)
        actual_weights = dict(item.issue_weights)
        if set(actual_weights) != set(expected_weights):
            raise StateSpaceError(
                "ladder expert set disagrees with final horizon state",
                context={"reason": "joint_path_ladder_weight_mismatch"},
            )
        for expert, expected in expected_weights.items():
            if not math.isclose(
                actual_weights[expert],
                expected,
                rel_tol=1e-10,
                abs_tol=1e-10,
            ):
                raise StateSpaceError(
                    "ladder weights disagree with final matured horizon state",
                    context={
                        "reason": "joint_path_ladder_weight_mismatch",
                        "horizon": item.horizon,
                        "expert": expert.value,
                    },
                )


def _validate_forecast_identity(forecast: JointPathForecast) -> None:
    expected_covariance = _weighted_covariance(forecast.scenarios)
    expected_correlation = _covariance_to_correlation(expected_covariance)
    if forecast.covariance != expected_covariance or forecast.correlation != expected_correlation:
        raise StateSpaceError(
            "joint path covariance diagnostics disagree with scenarios",
            context={"reason": "joint_path_covariance_mismatch"},
        )
    expected_effective = 1.0 / sum(
        item.weight * item.weight for item in forecast.scenarios
    )
    _close_or_raise(
        "effective_history_size",
        forecast.effective_history_size,
        expected_effective,
        reason="joint_path_history_mismatch",
    )
    expected = _forecast_fingerprint(
        origin_cutoff=forecast.origin_cutoff,
        horizons=forecast.horizons,
        target_indices=forecast.target_indices,
        marginal_means=forecast.marginal_means,
        marginal_variances=forecast.marginal_variances,
        residual_location=forecast.residual_location,
        residual_dispersion=forecast.residual_dispersion,
        scenarios=forecast.scenarios,
        covariance=forecast.covariance,
        correlation=forecast.correlation,
        source_configuration_fingerprint=forecast.source_configuration_fingerprint,
        source_report_fingerprint=forecast.source_report_fingerprint,
    )
    if forecast.fingerprint != expected:
        raise StateSpaceError(
            "joint path forecast fingerprint mismatch",
            context={"reason": "joint_path_forecast_identity_mismatch"},
        )


def _weighted_covariance(
    scenarios: Sequence[JointPathScenario],
) -> tuple[tuple[float, ...], ...]:
    dimensions = len(scenarios[0].values)
    means = tuple(
        sum(item.weight * item.values[index] for item in scenarios)
        for index in range(dimensions)
    )
    rows = []
    for left in range(dimensions):
        row = []
        for right in range(dimensions):
            value = sum(
                item.weight
                * (item.values[left] - means[left])
                * (item.values[right] - means[right])
                for item in scenarios
            )
            row.append(value)
        rows.append(tuple(row))
    return tuple(rows)


def _covariance_to_correlation(
    covariance: Sequence[Sequence[float]],
) -> tuple[tuple[float, ...], ...]:
    dimensions = len(covariance)
    rows = []
    for left in range(dimensions):
        row = []
        for right in range(dimensions):
            if left == right:
                row.append(1.0 if covariance[left][left] > _EPSILON else 0.0)
                continue
            denominator = math.sqrt(
                max(0.0, covariance[left][left])
                * max(0.0, covariance[right][right])
            )
            if denominator <= _EPSILON:
                row.append(0.0)
            else:
                value = covariance[left][right] / denominator
                row.append(min(1.0, max(-1.0, value)))
        rows.append(tuple(row))
    return tuple(rows)


def _recency_weights(count: int, decay: float) -> tuple[float, ...]:
    if count <= 0:
        raise StateSpaceError(
            "recency weighting requires history",
            context={"reason": "empty_joint_path_history"},
        )
    raw = tuple(decay ** (count - index - 1) for index in range(count))
    total = sum(raw)
    return tuple(value / total for value in raw)


def _configuration_fingerprint(
    *,
    config: JointPathConfig,
    source_configuration_fingerprint: str,
) -> str:
    return _digest(
        {
            "center_residuals": config.center_residuals,
            "history_window": config.history_window,
            "min_history": config.min_history,
            "min_scale": config.min_scale,
            "normalize_residual_dispersion": config.normalize_residual_dispersion,
            "recency_decay": config.recency_decay,
            "schema": "jeeves.joint_path.config.v1",
            "source_configuration_fingerprint": source_configuration_fingerprint,
            "standardized_clip": config.standardized_clip,
            "variogram_power": config.variogram_power,
        }
    )


def _forecast_fingerprint(
    *,
    origin_cutoff: int,
    horizons: Sequence[int],
    target_indices: Sequence[int],
    marginal_means: Sequence[float],
    marginal_variances: Sequence[float],
    residual_location: Sequence[float],
    residual_dispersion: Sequence[float],
    scenarios: Sequence[JointPathScenario],
    covariance: Sequence[Sequence[float]],
    correlation: Sequence[Sequence[float]],
    source_configuration_fingerprint: str,
    source_report_fingerprint: str | None,
) -> str:
    return _digest(
        {
            "correlation": [list(row) for row in correlation],
            "covariance": [list(row) for row in covariance],
            "horizons": list(horizons),
            "marginal_means": list(marginal_means),
            "marginal_variances": list(marginal_variances),
            "origin_cutoff": origin_cutoff,
            "residual_dispersion": list(residual_dispersion),
            "residual_location": list(residual_location),
            "scenarios": [
                {
                    "source_origin_cutoff": item.source_origin_cutoff,
                    "standardized_residuals": list(item.standardized_residuals),
                    "values": list(item.values),
                    "weight": item.weight,
                }
                for item in scenarios
            ],
            "schema": "jeeves.joint_path.forecast.v1",
            "source_configuration_fingerprint": source_configuration_fingerprint,
            "source_report_fingerprint": source_report_fingerprint,
            "target_indices": list(target_indices),
        }
    )


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    source_report_fingerprint: str,
    horizons: Sequence[int],
    steps: Sequence[JointPathStep],
) -> str:
    return _digest(
        {
            "configuration_fingerprint": configuration_fingerprint,
            "horizons": list(horizons),
            "schema": "jeeves.joint_path.report.v1",
            "source_report_fingerprint": source_report_fingerprint,
            "steps": [
                {
                    "actuals": list(step.actuals),
                    "energy_score": step.energy_score,
                    "forecast_fingerprint": step.forecast.fingerprint,
                    "origin_cutoff": step.origin_cutoff,
                    "variogram_score": step.variogram_score,
                }
                for step in steps
            ],
        }
    )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _euclidean_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(left, right)))


def _coerce_vector(
    values: Sequence[float],
    *,
    dimensions: int,
    field: str,
) -> tuple[float, ...]:
    result = tuple(_finite(field, value) for value in values)
    if len(result) != dimensions:
        raise StateSpaceError(
            f"{field} vector has the wrong dimension",
            context={"reason": "joint_path_dimension_mismatch", "field": field},
        )
    return result


def _validate_horizons(horizons: Sequence[int]) -> None:
    if not horizons:
        raise StateSpaceError(
            "joint path horizons cannot be empty",
            context={"reason": "empty_joint_path_horizons"},
        )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in horizons
    ) or tuple(sorted(set(horizons))) != tuple(horizons):
        raise StateSpaceError(
            "joint path horizons must be unique increasing positive integers",
            context={"reason": "invalid_joint_path_horizons"},
        )


def _validate_matrix(
    field: str,
    matrix: Sequence[Sequence[float]],
    dimensions: int,
) -> None:
    if len(matrix) != dimensions or any(len(row) != dimensions for row in matrix):
        raise StateSpaceError(
            f"{field} matrix has the wrong shape",
            context={"reason": "joint_path_matrix_mismatch", "field": field},
        )
    for row in matrix:
        for value in row:
            _finite(field, value)


def _close_or_raise(
    field: str,
    actual: float,
    expected: float,
    *,
    reason: str,
) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
        raise StateSpaceError(
            f"{field} disagrees with recomputed joint path evidence",
            context={"reason": reason, "field": field},
        )


def _sha256(field: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{field} must be a lowercase SHA-256 digest",
            context={"reason": "invalid_joint_path_digest", "field": field},
        )
    return value


def _finite(field: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{field} must be numeric",
            context={"reason": "invalid_joint_path_number", "field": field},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{field} must be finite",
            context={"reason": "invalid_joint_path_number", "field": field},
        )
    return number


def _positive(field: str, value: object) -> float:
    number = _finite(field, value)
    if number <= 0.0:
        raise StateSpaceError(
            f"{field} must be positive",
            context={"reason": "invalid_joint_path_number", "field": field},
        )
    return number


def _positive_integer(field: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StateSpaceError(
            f"{field} must be a positive integer",
            context={"reason": "invalid_joint_path_number", "field": field},
        )
    return value


def _open_closed_interval(
    field: str,
    value: object,
    lower: float,
    upper: float,
) -> float:
    number = _finite(field, value)
    if not lower < number <= upper:
        raise StateSpaceError(
            f"{field} must lie in ({lower}, {upper}]",
            context={"reason": "invalid_joint_path_number", "field": field},
        )
    return number


__all__ = [
    "JointPathConfig",
    "JointPathForecast",
    "JointPathReport",
    "JointPathScenario",
    "JointPathStep",
    "ResidualPath",
    "energy_score",
    "evaluate_joint_paths",
    "forecast_joint_path",
    "validate_joint_path_report",
    "variogram_score",
]
