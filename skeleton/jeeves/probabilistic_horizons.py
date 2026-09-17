"""Leakage-safe multi-horizon probabilistic arbitration for Jeeves.

The one-step cross-family arbitrator already learns from completed targets.
This module extends that custody model across multiple forecast horizons.

Each horizon owns an independent expert-weight process. A horizon-h forecast
issued with observations ``[:cutoff]`` targets index ``cutoff + h - 1``.
Its component distributions and mixture weights are frozen at issue time.
The target may update the horizon-h learning state only once that target has
actually matured. Short-horizon outcomes therefore cannot masquerade as
long-horizon evidence.

The module also reports aligned cross-horizon forecast-error covariance and can
apply the existing prequential conformal layer separately to every horizon.
The covariance is empirical diagnostic evidence, not a claim that the marginal
forecast family defines a joint multivariate distribution.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Sequence

from .probabilistic_arbitration import (
    ArbitratedForecast,
    CrossFamilyArbitrator,
    ExpertKind,
)
from .probabilistic_conformal import (
    ConformalConfig,
    ConformalReport,
    ForecastObservation,
    evaluate_prequential_conformal,
)
from .probabilistic_state_space import SeriesValues, StateSpaceError

_EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class MultiHorizonConfig:
    """Controls delayed-feedback learning across forecast horizons."""

    horizons: tuple[int, ...] = (1, 2, 4, 8)
    min_train_size: int = 48
    learning_rate: float = 0.75
    forgetting_factor: float = 0.99
    prior_strength: float = 0.02
    min_weight: float = 1e-4
    max_log_score_gap: float = 30.0
    covariance_floor: float = 1e-12

    def __post_init__(self) -> None:
        if not isinstance(self.horizons, tuple) or not self.horizons:
            raise StateSpaceError(
                "horizons must be a non-empty tuple",
                context={"reason": "invalid_multihorizon_config", "field": "horizons"},
            )
        if any(
            isinstance(horizon, bool)
            or not isinstance(horizon, int)
            or horizon <= 0
            for horizon in self.horizons
        ):
            raise StateSpaceError(
                "all horizons must be positive integers",
                context={"reason": "invalid_multihorizon_config", "field": "horizons"},
            )
        if tuple(sorted(set(self.horizons))) != self.horizons:
            raise StateSpaceError(
                "horizons must be unique and strictly increasing",
                context={"reason": "invalid_multihorizon_config", "field": "horizons"},
            )
        if (
            isinstance(self.min_train_size, bool)
            or not isinstance(self.min_train_size, int)
            or self.min_train_size < 8
        ):
            raise StateSpaceError(
                "min_train_size must be an integer >= 8",
                context={
                    "reason": "invalid_multihorizon_config",
                    "field": "min_train_size",
                },
            )
        _closed_interval("learning_rate", self.learning_rate, 0.0, 8.0)
        _open_closed_interval(
            "forgetting_factor",
            self.forgetting_factor,
            0.0,
            1.0,
        )
        _closed_interval("prior_strength", self.prior_strength, 0.0, 1.0)
        _closed_interval("min_weight", self.min_weight, 0.0, 0.20)
        gap = _positive("max_log_score_gap", self.max_log_score_gap)
        if gap > 1_000.0:
            raise StateSpaceError(
                "max_log_score_gap must be <= 1000",
                context={
                    "reason": "invalid_multihorizon_config",
                    "field": "max_log_score_gap",
                },
            )
        _positive("covariance_floor", self.covariance_floor)


@dataclass(frozen=True, slots=True)
class HorizonForecast:
    """One forecast frozen at its historical information cutoff."""

    origin_cutoff: int
    target_index: int
    horizon: int
    predictive: ArbitratedForecast
    issue_weights: tuple[tuple[ExpertKind, float], ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.origin_cutoff, bool)
            or not isinstance(self.origin_cutoff, int)
            or self.origin_cutoff < 1
        ):
            raise StateSpaceError(
                "origin_cutoff must be a positive integer",
                context={"reason": "invalid_horizon_forecast"},
            )
        if (
            isinstance(self.target_index, bool)
            or not isinstance(self.target_index, int)
            or self.target_index < self.origin_cutoff
        ):
            raise StateSpaceError(
                "target_index must be at or after the forecast cutoff",
                context={"reason": "invalid_horizon_forecast"},
            )
        if (
            isinstance(self.horizon, bool)
            or not isinstance(self.horizon, int)
            or self.horizon <= 0
        ):
            raise StateSpaceError(
                "horizon must be a positive integer",
                context={"reason": "invalid_horizon_forecast"},
            )
        expected_target = self.origin_cutoff + self.horizon - 1
        if self.target_index != expected_target:
            raise StateSpaceError(
                "target_index disagrees with origin_cutoff and horizon",
                context={"reason": "invalid_horizon_geometry"},
            )
        if self.predictive.horizon != self.horizon:
            raise StateSpaceError(
                "predictive horizon disagrees with horizon forecast",
                context={"reason": "horizon_mismatch"},
            )
        _validate_weight_vector(self.issue_weights)


@dataclass(frozen=True, slots=True)
class HorizonSettlement:
    """A matured target scored after its issue-time forecast is immutable."""

    forecast: HorizonForecast
    actual: float
    update_prior_weights: tuple[tuple[ExpertKind, float], ...]
    posterior_weights: tuple[tuple[ExpertKind, float], ...]
    component_log_scores: tuple[tuple[ExpertKind, float], ...]
    mixture_log_score: float
    absolute_error: float
    squared_error: float
    epistemic_share: float

    def __post_init__(self) -> None:
        _finite("actual", self.actual)
        _validate_weight_vector(self.update_prior_weights)
        _validate_weight_vector(self.posterior_weights)
        expected = {component.expert for component in self.forecast.predictive.components}
        if {expert for expert, _ in self.component_log_scores} != expected:
            raise StateSpaceError(
                "component_log_scores must exactly match forecast experts",
                context={"reason": "incomplete_horizon_scores"},
            )
        for _, value in self.component_log_scores:
            _finite("component_log_score", value)
        _finite("mixture_log_score", self.mixture_log_score)
        absolute = _finite("absolute_error", self.absolute_error)
        squared = _finite("squared_error", self.squared_error)
        share = _finite("epistemic_share", self.epistemic_share)
        if absolute < 0.0 or squared < 0.0 or not 0.0 <= share <= 1.0:
            raise StateSpaceError(
                "invalid horizon settlement diagnostics",
                context={"reason": "invalid_horizon_settlement"},
            )

    @property
    def horizon(self) -> int:
        return self.forecast.horizon

    @property
    def origin_cutoff(self) -> int:
        return self.forecast.origin_cutoff

    @property
    def target_index(self) -> int:
        return self.forecast.target_index

    @property
    def signed_error(self) -> float:
        return self.actual - self.forecast.predictive.mean


@dataclass(frozen=True, slots=True)
class HorizonSummary:
    """All completed evidence and final learning state for one horizon."""

    horizon: int
    settlements: tuple[HorizonSettlement, ...]
    final_weights: tuple[tuple[ExpertKind, float], ...]
    mean_log_score: float
    mae: float
    rmse: float
    average_effective_expert_count: float
    average_epistemic_share: float
    fingerprint: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon, bool)
            or not isinstance(self.horizon, int)
            or self.horizon <= 0
        ):
            raise StateSpaceError(
                "summary horizon must be positive",
                context={"reason": "invalid_horizon_summary"},
            )
        if not self.settlements:
            raise StateSpaceError(
                "horizon summary requires completed settlements",
                context={"reason": "empty_horizon_summary"},
            )
        if any(step.horizon != self.horizon for step in self.settlements):
            raise StateSpaceError(
                "horizon summary contains a settlement from another horizon",
                context={"reason": "horizon_mismatch"},
            )
        _validate_weight_vector(self.final_weights)
        _finite("mean_log_score", self.mean_log_score)
        if _finite("mae", self.mae) < 0.0 or _finite("rmse", self.rmse) < 0.0:
            raise StateSpaceError(
                "summary error metrics must be non-negative",
                context={"reason": "invalid_horizon_summary"},
            )
        count = _finite(
            "average_effective_expert_count",
            self.average_effective_expert_count,
        )
        share = _finite("average_epistemic_share", self.average_epistemic_share)
        if count < 1.0 or not 0.0 <= share <= 1.0:
            raise StateSpaceError(
                "invalid summary diversity diagnostics",
                context={"reason": "invalid_horizon_summary"},
            )


@dataclass(frozen=True, slots=True)
class HorizonDependenceReport:
    """Empirical dependence of aligned forecast errors across horizons."""

    horizons: tuple[int, ...]
    aligned_origins: tuple[int, ...]
    mean_errors: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    correlation: tuple[tuple[float, ...], ...]
    fingerprint: str

    @property
    def sample_size(self) -> int:
        return len(self.aligned_origins)


@dataclass(frozen=True, slots=True)
class MultiHorizonReport:
    """Auditable delayed-feedback evidence across all configured horizons."""

    config: MultiHorizonConfig
    experts: tuple[ExpertKind, ...]
    arbitration_configuration_fingerprint: str
    configuration_fingerprint: str
    summaries: tuple[HorizonSummary, ...]
    dependence: HorizonDependenceReport | None
    fingerprint: str

    def summary_for(self, horizon: int) -> HorizonSummary:
        for summary in self.summaries:
            if summary.horizon == horizon:
                return summary
        raise StateSpaceError(
            "horizon is absent from multi-horizon report",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class HorizonLadder:
    """Current marginal forecasts using each horizon's matured evidence."""

    origin_cutoff: int
    forecasts: tuple[HorizonForecast, ...]
    source_report_fingerprint: str
    fingerprint: str

    def forecast_for(self, horizon: int) -> HorizonForecast:
        for forecast in self.forecasts:
            if forecast.horizon == horizon:
                return forecast
        raise StateSpaceError(
            "horizon is absent from forecast ladder",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class HorizonConformalReport:
    """Conformal evidence for exactly one forecast horizon."""

    horizon: int
    report: ConformalReport


@dataclass(frozen=True, slots=True)
class MultiHorizonConformalReport:
    """Per-horizon conformal evidence without cross-horizon score leakage."""

    source_report_fingerprint: str
    reports: tuple[HorizonConformalReport, ...]
    fingerprint: str

    def report_for(self, horizon: int) -> ConformalReport:
        for item in self.reports:
            if item.horizon == horizon:
                return item.report
        raise StateSpaceError(
            "horizon is absent from conformal report",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


class MultiHorizonArbitrator:
    """Delayed-feedback arbitration with independent state per horizon."""

    def __init__(
        self,
        arbitrator: CrossFamilyArbitrator,
        *,
        config: MultiHorizonConfig | None = None,
        prior_weights: Mapping[int, Mapping[ExpertKind, float]] | None = None,
    ) -> None:
        if not isinstance(arbitrator, CrossFamilyArbitrator):
            raise StateSpaceError(
                "arbitrator must be a CrossFamilyArbitrator",
                context={"reason": "invalid_multihorizon_arbitrator"},
            )
        self.arbitrator = arbitrator
        self.config = config or MultiHorizonConfig()
        self.experts = tuple(arbitrator.experts)
        if self.config.min_weight * len(self.experts) >= 1.0:
            raise StateSpaceError(
                "min_weight is too large for the configured expert count",
                context={
                    "reason": "invalid_multihorizon_config",
                    "field": "min_weight",
                },
            )
        self._initial_weights = _normalize_horizon_priors(
            horizons=self.config.horizons,
            experts=self.experts,
            supplied=prior_weights,
        )
        self._configuration_fingerprint = _configuration_fingerprint(
            config=self.config,
            experts=self.experts,
            arbitration_configuration_fingerprint=(
                self.arbitrator.configuration_fingerprint
            ),
            initial_weights=self._initial_weights,
        )

    @property
    def configuration_fingerprint(self) -> str:
        return self._configuration_fingerprint

    def evaluate(
        self,
        series: SeriesValues | Sequence[float],
    ) -> MultiHorizonReport:
        """Evaluate all horizons while settling feedback only when it matures."""

        values = _coerce_values(series)
        maximum_horizon = max(self.config.horizons)
        if len(values) < self.config.min_train_size + maximum_horizon:
            raise StateSpaceError(
                "series is too short for configured multi-horizon evaluation",
                context={
                    "reason": "insufficient_multihorizon_history",
                    "required": self.config.min_train_size + maximum_horizon,
                    "actual": len(values),
                },
            )

        weights_by_horizon = {
            horizon: dict(weights)
            for horizon, weights in self._initial_weights.items()
        }
        settlements_by_horizon: dict[int, list[HorizonSettlement]] = {
            horizon: [] for horizon in self.config.horizons
        }
        pending: dict[int, list[HorizonForecast]] = {}

        for cutoff in range(self.config.min_train_size, len(values) + 1):
            matured_index = cutoff - 1
            matured = pending.pop(matured_index, ())
            for forecast in sorted(matured, key=lambda item: item.horizon):
                horizon = forecast.horizon
                actual = values[forecast.target_index]
                component_scores = {
                    component.expert: component.predictive.log_density(actual)
                    for component in forecast.predictive.components
                }
                update_prior = dict(weights_by_horizon[horizon])
                posterior = _posterior_weights(
                    prior=update_prior,
                    log_scores=component_scores,
                    config=self.config,
                )
                error = forecast.predictive.mean - actual
                epistemic_share = (
                    forecast.predictive.epistemic_variance
                    / max(_EPSILON, forecast.predictive.variance)
                )
                settlement = HorizonSettlement(
                    forecast=forecast,
                    actual=actual,
                    update_prior_weights=_sorted_weights(update_prior),
                    posterior_weights=_sorted_weights(posterior),
                    component_log_scores=_sorted_scores(component_scores),
                    mixture_log_score=forecast.predictive.log_density(actual),
                    absolute_error=abs(error),
                    squared_error=error * error,
                    epistemic_share=min(1.0, max(0.0, epistemic_share)),
                )
                settlements_by_horizon[horizon].append(settlement)
                weights_by_horizon[horizon] = posterior

            if cutoff == len(values):
                continue

            training = values[:cutoff]
            for horizon in self.config.horizons:
                target_index = cutoff + horizon - 1
                if target_index >= len(values):
                    continue
                issue_weights = dict(weights_by_horizon[horizon])
                predictive = self.arbitrator.forecast(
                    training,
                    horizon=horizon,
                    weights=issue_weights,
                )
                forecast = HorizonForecast(
                    origin_cutoff=cutoff,
                    target_index=target_index,
                    horizon=horizon,
                    predictive=predictive,
                    issue_weights=_sorted_weights(issue_weights),
                )
                pending.setdefault(target_index, []).append(forecast)

        if pending:
            raise StateSpaceError(
                "completed historical evaluation left unresolved forecasts",
                context={"reason": "multihorizon_custody_error"},
            )

        summaries = tuple(
            _build_summary(
                horizon=horizon,
                settlements=settlements_by_horizon[horizon],
                final_weights=weights_by_horizon[horizon],
            )
            for horizon in self.config.horizons
        )
        dependence = _build_dependence_report(
            summaries,
            covariance_floor=self.config.covariance_floor,
        )
        fingerprint = _report_fingerprint(
            configuration_fingerprint=self.configuration_fingerprint,
            summaries=summaries,
            dependence=dependence,
        )
        return MultiHorizonReport(
            config=self.config,
            experts=self.experts,
            arbitration_configuration_fingerprint=(
                self.arbitrator.configuration_fingerprint
            ),
            configuration_fingerprint=self.configuration_fingerprint,
            summaries=summaries,
            dependence=dependence,
            fingerprint=fingerprint,
        )

    def forecast_ladder(
        self,
        series: SeriesValues | Sequence[float],
        report: MultiHorizonReport,
    ) -> HorizonLadder:
        """Forecast every configured horizon using only matured report state."""

        values = _coerce_values(series)
        if len(values) < self.config.min_train_size:
            raise StateSpaceError(
                "series is shorter than the multi-horizon training minimum",
                context={"reason": "insufficient_multihorizon_history"},
            )
        self._validate_report_identity(report)
        cutoff = len(values)
        forecasts = tuple(
            HorizonForecast(
                origin_cutoff=cutoff,
                target_index=cutoff + horizon - 1,
                horizon=horizon,
                predictive=self.arbitrator.forecast(
                    values,
                    horizon=horizon,
                    weights=dict(report.summary_for(horizon).final_weights),
                ),
                issue_weights=report.summary_for(horizon).final_weights,
            )
            for horizon in self.config.horizons
        )
        fingerprint = _ladder_fingerprint(
            source_report_fingerprint=report.fingerprint,
            origin_cutoff=cutoff,
            forecasts=forecasts,
        )
        return HorizonLadder(
            origin_cutoff=cutoff,
            forecasts=forecasts,
            source_report_fingerprint=report.fingerprint,
            fingerprint=fingerprint,
        )

    def _validate_report_identity(self, report: MultiHorizonReport) -> None:
        if not isinstance(report, MultiHorizonReport):
            raise StateSpaceError(
                "report must be a MultiHorizonReport",
                context={"reason": "invalid_multihorizon_report"},
            )
        if (
            report.config != self.config
            or report.experts != self.experts
            or report.arbitration_configuration_fingerprint
            != self.arbitrator.configuration_fingerprint
            or report.configuration_fingerprint != self.configuration_fingerprint
        ):
            raise StateSpaceError(
                "multi-horizon report does not match arbitrator configuration",
                context={"reason": "multihorizon_report_mismatch"},
            )
        if tuple(summary.horizon for summary in report.summaries) != self.config.horizons:
            raise StateSpaceError(
                "multi-horizon report summary set is inconsistent",
                context={"reason": "multihorizon_report_identity_mismatch"},
            )
        for summary in report.summaries:
            expected_summary = _summary_fingerprint(
                horizon=summary.horizon,
                settlements=summary.settlements,
                final_weights=summary.final_weights,
            )
            if summary.fingerprint != expected_summary:
                raise StateSpaceError(
                    "multi-horizon summary fingerprint mismatch",
                    context={
                        "reason": "multihorizon_report_identity_mismatch",
                        "horizon": summary.horizon,
                    },
                )
        if report.dependence is not None:
            expected_dependence = _dependence_fingerprint(
                horizons=report.dependence.horizons,
                aligned_origins=report.dependence.aligned_origins,
                mean_errors=report.dependence.mean_errors,
                covariance=report.dependence.covariance,
                correlation=report.dependence.correlation,
            )
            if report.dependence.fingerprint != expected_dependence:
                raise StateSpaceError(
                    "multi-horizon dependence fingerprint mismatch",
                    context={"reason": "multihorizon_report_identity_mismatch"},
                )
        expected_report = _report_fingerprint(
            configuration_fingerprint=report.configuration_fingerprint,
            summaries=report.summaries,
            dependence=report.dependence,
        )
        if report.fingerprint != expected_report:
            raise StateSpaceError(
                "multi-horizon report fingerprint mismatch",
                context={"reason": "multihorizon_report_identity_mismatch"},
            )


def evaluate_multihorizon_conformal(
    report: MultiHorizonReport,
    *,
    config: ConformalConfig | None = None,
) -> MultiHorizonConformalReport:
    """Apply prequential conformal calibration independently per horizon."""

    if not isinstance(report, MultiHorizonReport):
        raise StateSpaceError(
            "report must be a MultiHorizonReport",
            context={"reason": "invalid_multihorizon_report"},
        )
    config = config or ConformalConfig()
    reports: list[HorizonConformalReport] = []
    for summary in report.summaries:
        if len(summary.settlements) <= config.min_calibration:
            raise StateSpaceError(
                "not enough completed settlements for horizon conformal calibration",
                context={
                    "reason": "insufficient_multihorizon_conformal_history",
                    "horizon": summary.horizon,
                    "required": config.min_calibration + 1,
                    "actual": len(summary.settlements),
                },
            )
        observations = tuple(
            ForecastObservation(
                target_index=step.target_index,
                actual=step.actual,
                predictive=step.forecast.predictive,
            )
            for step in summary.settlements
        )
        conformal = evaluate_prequential_conformal(observations, config=config)
        reports.append(
            HorizonConformalReport(
                horizon=summary.horizon,
                report=conformal,
            )
        )
    result = tuple(reports)
    fingerprint = _multihorizon_conformal_fingerprint(
        source_report_fingerprint=report.fingerprint,
        reports=result,
    )
    return MultiHorizonConformalReport(
        source_report_fingerprint=report.fingerprint,
        reports=result,
        fingerprint=fingerprint,
    )


def _build_summary(
    *,
    horizon: int,
    settlements: Sequence[HorizonSettlement],
    final_weights: Mapping[ExpertKind, float],
) -> HorizonSummary:
    if not settlements:
        raise StateSpaceError(
            "multi-horizon evaluation produced no settlements for a horizon",
            context={"reason": "empty_horizon_summary", "horizon": horizon},
        )
    final = _sorted_weights(final_weights)
    fingerprint = _summary_fingerprint(
        horizon=horizon,
        settlements=settlements,
        final_weights=final,
    )
    return HorizonSummary(
        horizon=horizon,
        settlements=tuple(settlements),
        final_weights=final,
        mean_log_score=statistics.fmean(
            step.mixture_log_score for step in settlements
        ),
        mae=statistics.fmean(step.absolute_error for step in settlements),
        rmse=math.sqrt(
            statistics.fmean(step.squared_error for step in settlements)
        ),
        average_effective_expert_count=statistics.fmean(
            step.forecast.predictive.effective_expert_count
            for step in settlements
        ),
        average_epistemic_share=statistics.fmean(
            step.epistemic_share for step in settlements
        ),
        fingerprint=fingerprint,
    )


def _build_dependence_report(
    summaries: Sequence[HorizonSummary],
    *,
    covariance_floor: float,
) -> HorizonDependenceReport | None:
    by_horizon = {
        summary.horizon: {
            step.origin_cutoff: step.signed_error
            for step in summary.settlements
        }
        for summary in summaries
    }
    common_origins = set.intersection(
        *(set(origin_errors) for origin_errors in by_horizon.values())
    )
    if len(common_origins) < 2:
        return None
    aligned_origins = tuple(sorted(common_origins))
    horizons = tuple(summary.horizon for summary in summaries)
    matrix = tuple(
        tuple(by_horizon[horizon][origin] for horizon in horizons)
        for origin in aligned_origins
    )
    mean_errors = tuple(
        statistics.fmean(row[column] for row in matrix)
        for column in range(len(horizons))
    )
    covariance_rows: list[tuple[float, ...]] = []
    denominator = len(matrix) - 1
    for left in range(len(horizons)):
        row: list[float] = []
        for right in range(len(horizons)):
            value = sum(
                (sample[left] - mean_errors[left])
                * (sample[right] - mean_errors[right])
                for sample in matrix
            ) / denominator
            if left == right:
                value = max(covariance_floor, value)
            row.append(value)
        covariance_rows.append(tuple(row))
    covariance = tuple(covariance_rows)

    correlation_rows: list[tuple[float, ...]] = []
    for left in range(len(horizons)):
        row = []
        for right in range(len(horizons)):
            if left == right:
                row.append(1.0)
                continue
            scale = math.sqrt(
                max(covariance_floor, covariance[left][left])
                * max(covariance_floor, covariance[right][right])
            )
            value = covariance[left][right] / scale
            row.append(min(1.0, max(-1.0, value)))
        correlation_rows.append(tuple(row))
    correlation = tuple(correlation_rows)
    fingerprint = _dependence_fingerprint(
        horizons=horizons,
        aligned_origins=aligned_origins,
        mean_errors=mean_errors,
        covariance=covariance,
        correlation=correlation,
    )
    return HorizonDependenceReport(
        horizons=horizons,
        aligned_origins=aligned_origins,
        mean_errors=mean_errors,
        covariance=covariance,
        correlation=correlation,
        fingerprint=fingerprint,
    )


def _posterior_weights(
    *,
    prior: Mapping[ExpertKind, float],
    log_scores: Mapping[ExpertKind, float],
    config: MultiHorizonConfig,
) -> dict[ExpertKind, float]:
    if set(prior) != set(log_scores):
        raise StateSpaceError(
            "horizon update requires one completed score per expert",
            context={"reason": "incomplete_horizon_update"},
        )
    best_score = max(_finite("component_log_score", score) for score in log_scores.values())
    floor = best_score - config.max_log_score_gap
    uniform = 1.0 / len(prior)
    logits: dict[ExpertKind, float] = {}
    for expert, weight in prior.items():
        score = max(floor, _finite("component_log_score", log_scores[expert]))
        blended = (
            (1.0 - config.prior_strength) * weight
            + config.prior_strength * uniform
        )
        remembered = config.forgetting_factor * math.log(max(_EPSILON, blended))
        logits[expert] = remembered + config.learning_rate * score
    normalizer = _logsumexp(tuple(logits.values()))
    raw = {
        expert: math.exp(value - normalizer)
        for expert, value in logits.items()
    }
    return _apply_weight_floor(raw, config.min_weight)


def _normalize_horizon_priors(
    *,
    horizons: Sequence[int],
    experts: Sequence[ExpertKind],
    supplied: Mapping[int, Mapping[ExpertKind, float]] | None,
) -> dict[int, tuple[tuple[ExpertKind, float], ...]]:
    if supplied is not None and set(supplied) != set(horizons):
        raise StateSpaceError(
            "prior_weights must provide exactly one mapping per horizon",
            context={"reason": "invalid_multihorizon_prior"},
        )
    result: dict[int, tuple[tuple[ExpertKind, float], ...]] = {}
    for horizon in horizons:
        current = None if supplied is None else supplied[horizon]
        if current is None:
            uniform = 1.0 / len(experts)
            result[horizon] = tuple((expert, uniform) for expert in experts)
            continue
        if set(current) != set(experts):
            raise StateSpaceError(
                "each horizon prior must exactly match configured experts",
                context={
                    "reason": "invalid_multihorizon_prior",
                    "horizon": horizon,
                },
            )
        clean = {
            expert: _non_negative("prior_weight", current[expert])
            for expert in experts
        }
        total = sum(clean.values())
        if total <= _EPSILON:
            raise StateSpaceError(
                "each horizon prior must contain positive mass",
                context={
                    "reason": "invalid_multihorizon_prior",
                    "horizon": horizon,
                },
            )
        result[horizon] = tuple(
            (expert, clean[expert] / total)
            for expert in experts
        )
    return result


def _configuration_fingerprint(
    *,
    config: MultiHorizonConfig,
    experts: Sequence[ExpertKind],
    arbitration_configuration_fingerprint: str,
    initial_weights: Mapping[int, Sequence[tuple[ExpertKind, float]]],
) -> str:
    payload = {
        "arbitration_configuration_fingerprint": (
            arbitration_configuration_fingerprint
        ),
        "config": {
            "covariance_floor": config.covariance_floor,
            "forgetting_factor": config.forgetting_factor,
            "horizons": list(config.horizons),
            "learning_rate": config.learning_rate,
            "max_log_score_gap": config.max_log_score_gap,
            "min_train_size": config.min_train_size,
            "min_weight": config.min_weight,
            "prior_strength": config.prior_strength,
        },
        "experts": [expert.value for expert in experts],
        "initial_weights": {
            str(horizon): [
                [expert.value, weight]
                for expert, weight in initial_weights[horizon]
            ]
            for horizon in config.horizons
        },
        "schema": "jeeves.multihorizon.config.v1",
    }
    return _digest(payload)


def _summary_fingerprint(
    *,
    horizon: int,
    settlements: Sequence[HorizonSettlement],
    final_weights: Sequence[tuple[ExpertKind, float]],
) -> str:
    payload = {
        "final_weights": [
            [expert.value, weight] for expert, weight in final_weights
        ],
        "horizon": horizon,
        "schema": "jeeves.multihorizon.summary.v1",
        "settlements": [
            {
                "actual": step.actual,
                "component_log_scores": [
                    [expert.value, score]
                    for expert, score in step.component_log_scores
                ],
                "epistemic_share": step.epistemic_share,
                "issue_weights": [
                    [expert.value, weight]
                    for expert, weight in step.forecast.issue_weights
                ],
                "mixture_log_score": step.mixture_log_score,
                "origin_cutoff": step.origin_cutoff,
                "posterior_weights": [
                    [expert.value, weight]
                    for expert, weight in step.posterior_weights
                ],
                "predictive_mean": step.forecast.predictive.mean,
                "predictive_variance": step.forecast.predictive.variance,
                "target_index": step.target_index,
                "update_prior_weights": [
                    [expert.value, weight]
                    for expert, weight in step.update_prior_weights
                ],
            }
            for step in settlements
        ],
    }
    return _digest(payload)


def _dependence_fingerprint(
    *,
    horizons: Sequence[int],
    aligned_origins: Sequence[int],
    mean_errors: Sequence[float],
    covariance: Sequence[Sequence[float]],
    correlation: Sequence[Sequence[float]],
) -> str:
    return _digest(
        {
            "aligned_origins": list(aligned_origins),
            "correlation": [list(row) for row in correlation],
            "covariance": [list(row) for row in covariance],
            "horizons": list(horizons),
            "mean_errors": list(mean_errors),
            "schema": "jeeves.multihorizon.dependence.v1",
        }
    )


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    summaries: Sequence[HorizonSummary],
    dependence: HorizonDependenceReport | None,
) -> str:
    return _digest(
        {
            "configuration_fingerprint": configuration_fingerprint,
            "dependence_fingerprint": (
                None if dependence is None else dependence.fingerprint
            ),
            "schema": "jeeves.multihorizon.report.v1",
            "summary_fingerprints": [
                summary.fingerprint for summary in summaries
            ],
        }
    )


def _ladder_fingerprint(
    *,
    source_report_fingerprint: str,
    origin_cutoff: int,
    forecasts: Sequence[HorizonForecast],
) -> str:
    return _digest(
        {
            "forecasts": [
                {
                    "horizon": forecast.horizon,
                    "issue_weights": [
                        [expert.value, weight]
                        for expert, weight in forecast.issue_weights
                    ],
                    "mean": forecast.predictive.mean,
                    "target_index": forecast.target_index,
                    "variance": forecast.predictive.variance,
                }
                for forecast in forecasts
            ],
            "origin_cutoff": origin_cutoff,
            "schema": "jeeves.multihorizon.ladder.v1",
            "source_report_fingerprint": source_report_fingerprint,
        }
    )


def _multihorizon_conformal_fingerprint(
    *,
    source_report_fingerprint: str,
    reports: Sequence[HorizonConformalReport],
) -> str:
    return _digest(
        {
            "reports": [
                {
                    "horizon": item.horizon,
                    "report_fingerprint": item.report.fingerprint,
                }
                for item in reports
            ],
            "schema": "jeeves.multihorizon.conformal.v1",
            "source_report_fingerprint": source_report_fingerprint,
        }
    )


def _validate_weight_vector(
    weights: Sequence[tuple[ExpertKind, float]],
) -> None:
    if not weights:
        raise StateSpaceError(
            "weight vector cannot be empty",
            context={"reason": "invalid_horizon_weights"},
        )
    experts = [expert for expert, _ in weights]
    if len(set(experts)) != len(experts):
        raise StateSpaceError(
            "weight vector contains duplicate experts",
            context={"reason": "invalid_horizon_weights"},
        )
    total = 0.0
    for expert, weight in weights:
        if not isinstance(expert, ExpertKind):
            raise StateSpaceError(
                "weight vector contains an invalid expert",
                context={"reason": "invalid_horizon_weights"},
            )
        clean = _finite("weight", weight)
        if not 0.0 <= clean <= 1.0:
            raise StateSpaceError(
                "weights must lie in [0, 1]",
                context={"reason": "invalid_horizon_weights"},
            )
        total += clean
    if abs(total - 1.0) > 1e-9:
        raise StateSpaceError(
            "weights must sum to one",
            context={"reason": "invalid_horizon_weights"},
        )


def _apply_weight_floor(
    weights: Mapping[ExpertKind, float],
    floor: float,
) -> dict[ExpertKind, float]:
    total = sum(weights.values())
    if not math.isfinite(total) or total <= _EPSILON:
        raise StateSpaceError(
            "horizon weights lost all probability mass",
            context={"reason": "numerical_instability"},
        )
    normalized = {
        expert: weight / total for expert, weight in weights.items()
    }
    if floor <= 0.0:
        return normalized
    if floor * len(weights) >= 1.0:
        raise StateSpaceError(
            "min_weight is too large for the configured expert count",
            context={
                "reason": "invalid_multihorizon_config",
                "field": "min_weight",
            },
        )
    free_mass = 1.0 - floor * len(weights)
    return {
        expert: floor + free_mass * normalized[expert]
        for expert in normalized
    }


def _sorted_weights(
    weights: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(weights.items(), key=lambda item: item[0].value))


def _sorted_scores(
    scores: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(scores.items(), key=lambda item: item[0].value))


def _coerce_values(
    series: SeriesValues | Sequence[float],
) -> tuple[float, ...]:
    raw: object = getattr(series, "values", series)
    if isinstance(raw, (str, bytes)):
        raise StateSpaceError(
            "multi-horizon series must be numeric",
            context={"reason": "invalid_series"},
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise StateSpaceError(
            "multi-horizon series must be iterable",
            context={"reason": "invalid_series"},
        ) from exc
    if not values:
        raise StateSpaceError(
            "multi-horizon series cannot be empty",
            context={"reason": "empty_series"},
        )
    return tuple(_finite("value", value) for value in values)


def _logsumexp(values: Sequence[float]) -> float:
    if not values:
        raise StateSpaceError(
            "logsumexp requires at least one value",
            context={"reason": "empty_numeric_sequence"},
        )
    maximum = max(values)
    if not math.isfinite(maximum):
        raise StateSpaceError(
            "horizon log weights became non-finite",
            context={"reason": "numerical_instability"},
        )
    return maximum + math.log(
        sum(math.exp(value - maximum) for value in values)
    )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_number", "field": name},
        )
    result = float(value)
    if not math.isfinite(result):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_number", "field": name},
        )
    return result


def _non_negative(name: str, value: object) -> float:
    result = _finite(name, value)
    if result < 0.0:
        raise StateSpaceError(
            f"{name} must be non-negative",
            context={"reason": "invalid_number", "field": name},
        )
    return result


def _positive(name: str, value: object) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise StateSpaceError(
            f"{name} must be positive",
            context={"reason": "invalid_number", "field": name},
        )
    return result


def _closed_interval(
    name: str,
    value: object,
    minimum: float,
    maximum: float,
) -> float:
    result = _finite(name, value)
    if not minimum <= result <= maximum:
        raise StateSpaceError(
            f"{name} must be between {minimum} and {maximum}",
            context={"reason": "invalid_multihorizon_config", "field": name},
        )
    return result


def _open_closed_interval(
    name: str,
    value: object,
    minimum: float,
    maximum: float,
) -> float:
    result = _finite(name, value)
    if not minimum < result <= maximum:
        raise StateSpaceError(
            f"{name} must be > {minimum} and <= {maximum}",
            context={"reason": "invalid_multihorizon_config", "field": name},
        )
    return result


__all__ = [
    "HorizonConformalReport",
    "HorizonDependenceReport",
    "HorizonForecast",
    "HorizonLadder",
    "HorizonSettlement",
    "HorizonSummary",
    "MultiHorizonArbitrator",
    "MultiHorizonConfig",
    "MultiHorizonConformalReport",
    "MultiHorizonReport",
    "evaluate_multihorizon_conformal",
]
