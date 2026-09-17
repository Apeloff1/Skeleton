"""Delayed, horizon-specific probabilistic arbitration for Jeeves.

One-step prequential evidence is not automatically valid evidence for a longer
forecast horizon.  This module therefore gives every configured horizon its own
expert-weight state and its own settlement clock.

At origin ``t`` a horizon-``h`` forecast is issued from observations strictly
before ``t`` and targets index ``t + h - 1``.  Its expert weights are frozen at
issue time.  The realized target may update the horizon-``h`` posterior only
after that target matures; the update can influence forecasts issued at later
origins, never forecasts already in flight.

The resulting report keeps per-horizon proper scores and errors, aligned
cross-horizon residual covariance/correlation, deterministic identity
fingerprints, and an optional horizon-by-horizon conformal evidence bundle.
Historical evidence remains descriptive evidence and grants no live execution
or autonomous model-mutation authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .probabilistic_arbitration import (
    ArbitratedForecast,
    CrossFamilyConfig,
    ExpertKind,
    _posterior_weights,
)
from .probabilistic_conformal import (
    ConformalConfig,
    ConformalInterval,
    ConformalReport,
    ForecastObservation,
    conformalize_next_forecast,
    evaluate_prequential_conformal,
)
from .probabilistic_state_space import StateSpaceError


class HorizonArbitrator(Protocol):
    """Structural contract consumed by multi-horizon arbitration."""

    experts: tuple[ExpertKind, ...]
    config: CrossFamilyConfig
    configuration_fingerprint: str

    def forecast(
        self,
        series: Sequence[float],
        *,
        horizon: int = 1,
        weights: Mapping[ExpertKind, float] | None = None,
    ) -> ArbitratedForecast: ...


@dataclass(frozen=True, slots=True)
class MultiHorizonConfig:
    """Controls issue cadence and independent horizon evidence clocks."""

    horizons: tuple[int, ...] = (1, 2, 4, 8)
    min_train_size: int = 32
    step: int = 1

    def __post_init__(self) -> None:
        if not self.horizons:
            raise StateSpaceError(
                "at least one forecast horizon is required",
                context={"reason": "empty_multihorizon_config"},
            )
        previous = 0
        for horizon in self.horizons:
            if (
                isinstance(horizon, bool)
                or not isinstance(horizon, int)
                or horizon <= 0
            ):
                raise StateSpaceError(
                    "forecast horizons must be positive integers",
                    context={
                        "reason": "invalid_multihorizon_config",
                        "field": "horizons",
                    },
                )
            if horizon <= previous:
                raise StateSpaceError(
                    "forecast horizons must be unique and strictly increasing",
                    context={
                        "reason": "invalid_multihorizon_config",
                        "field": "horizons",
                    },
                )
            previous = horizon
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
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step <= 0:
            raise StateSpaceError(
                "step must be a positive integer",
                context={
                    "reason": "invalid_multihorizon_config",
                    "field": "step",
                },
            )


@dataclass(frozen=True, slots=True)
class HorizonStep:
    """One matured forecast whose issue-time state can no longer change."""

    origin_index: int
    target_index: int
    horizon: int
    actual: float
    predictive: ArbitratedForecast
    prior_weights: tuple[tuple[ExpertKind, float], ...]
    posterior_weights: tuple[tuple[ExpertKind, float], ...]
    component_log_scores: tuple[tuple[ExpertKind, float], ...]
    mixture_log_score: float
    error: float
    absolute_error: float
    squared_error: float

    def __post_init__(self) -> None:
        for name, value in (
            ("origin_index", self.origin_index),
            ("target_index", self.target_index),
            ("horizon", self.horizon),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise StateSpaceError(
                    f"{name} must be a positive integer",
                    context={"reason": "invalid_multihorizon_step", "field": name},
                )
        if self.target_index != self.origin_index + self.horizon - 1:
            raise StateSpaceError(
                "target index is inconsistent with origin and horizon",
                context={"reason": "invalid_multihorizon_step"},
            )
        for name in (
            "actual",
            "mixture_log_score",
            "error",
            "absolute_error",
            "squared_error",
        ):
            _finite(name, getattr(self, name))
        if self.absolute_error < 0.0 or self.squared_error < 0.0:
            raise StateSpaceError(
                "forecast errors must be non-negative where required",
                context={"reason": "invalid_multihorizon_step"},
            )
        if abs(self.absolute_error - abs(self.error)) > 1e-9:
            raise StateSpaceError(
                "absolute error disagrees with signed error",
                context={"reason": "invalid_multihorizon_step"},
            )
        if abs(self.squared_error - self.error * self.error) > 1e-8:
            raise StateSpaceError(
                "squared error disagrees with signed error",
                context={"reason": "invalid_multihorizon_step"},
            )
        if self.predictive.horizon != self.horizon:
            raise StateSpaceError(
                "predictive horizon disagrees with step horizon",
                context={"reason": "invalid_multihorizon_step"},
            )
        _validate_weight_pairs(self.prior_weights)
        _validate_weight_pairs(self.posterior_weights)
        if tuple(expert for expert, _ in self.prior_weights) != tuple(
            expert for expert, _ in self.posterior_weights
        ):
            raise StateSpaceError(
                "prior and posterior expert sets must match",
                context={"reason": "invalid_multihorizon_step"},
            )


@dataclass(frozen=True, slots=True)
class HorizonReport:
    """Prequential evidence and final posterior state for one horizon."""

    horizon: int
    steps: tuple[HorizonStep, ...]
    final_weights: tuple[tuple[ExpertKind, float], ...]
    mean_log_score: float
    mae: float
    rmse: float
    bias: float
    fingerprint: str

    @property
    def selected_expert(self) -> ExpertKind:
        return max(
            self.final_weights,
            key=lambda item: (item[1], item[0].value),
        )[0]

    def weight_for(self, expert: ExpertKind) -> float:
        for current, weight in self.final_weights:
            if current is expert:
                return weight
        raise StateSpaceError(
            "expert is absent from horizon report",
            context={
                "reason": "missing_multihorizon_expert",
                "expert": expert.value,
                "horizon": self.horizon,
            },
        )


@dataclass(frozen=True, slots=True)
class HorizonDependence:
    """Aligned error dependence across forecast horizons."""

    horizons: tuple[int, ...]
    common_origins: tuple[int, ...]
    covariance: tuple[tuple[float, ...], ...]
    correlation: tuple[tuple[float, ...], ...]

    @property
    def sample_size(self) -> int:
        return len(self.common_origins)


@dataclass(frozen=True, slots=True)
class MultiHorizonReport:
    """Auditable delayed-feedback evidence across all configured horizons."""

    config: MultiHorizonConfig
    arbitrator_configuration_fingerprint: str
    configuration_fingerprint: str
    horizon_reports: tuple[HorizonReport, ...]
    dependence: HorizonDependence
    fingerprint: str

    @property
    def horizons(self) -> tuple[int, ...]:
        return tuple(report.horizon for report in self.horizon_reports)

    def report_for(self, horizon: int) -> HorizonReport:
        for report in self.horizon_reports:
            if report.horizon == horizon:
                return report
        raise StateSpaceError(
            "horizon is absent from multi-horizon report",
            context={"reason": "missing_multihorizon_report", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class ForecastLadder:
    """One issue-time set of forecasts using matured evidence only."""

    origin_index: int
    source_report_fingerprint: str
    forecasts: tuple[tuple[int, ArbitratedForecast], ...]

    def forecast_for(self, horizon: int) -> ArbitratedForecast:
        for current, forecast in self.forecasts:
            if current == horizon:
                return forecast
        raise StateSpaceError(
            "horizon is absent from forecast ladder",
            context={"reason": "missing_forecast_ladder_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class HorizonConformalEvidence:
    """Calibration evidence isolated to one forecast horizon."""

    horizon: int
    source_horizon_fingerprint: str
    report: ConformalReport


@dataclass(frozen=True, slots=True)
class MultiHorizonConformalReport:
    """Per-horizon conformal states bound to one multi-horizon source report."""

    source_report_fingerprint: str
    horizons: tuple[HorizonConformalEvidence, ...]
    fingerprint: str

    def evidence_for(self, horizon: int) -> HorizonConformalEvidence:
        for evidence in self.horizons:
            if evidence.horizon == horizon:
                return evidence
        raise StateSpaceError(
            "horizon is absent from conformal evidence",
            context={"reason": "missing_multihorizon_conformal", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class ConformalForecastLadder:
    """Forecast ladder paired with calibrated intervals at every horizon."""

    origin_index: int
    source_report_fingerprint: str
    intervals: tuple[tuple[int, ConformalInterval], ...]

    def interval_for(self, horizon: int) -> ConformalInterval:
        for current, interval in self.intervals:
            if current == horizon:
                return interval
        raise StateSpaceError(
            "horizon is absent from conformal forecast ladder",
            context={"reason": "missing_conformal_ladder_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class _PendingForecast:
    origin_index: int
    target_index: int
    horizon: int
    predictive: ArbitratedForecast
    prior_weights: tuple[tuple[ExpertKind, float], ...]


class MultiHorizonArbitrator:
    """Maintain an independent delayed-feedback expert posterior per horizon."""

    def __init__(
        self,
        arbitrator: HorizonArbitrator,
        *,
        config: MultiHorizonConfig | None = None,
    ) -> None:
        self.arbitrator = arbitrator
        self.config = config or MultiHorizonConfig()
        _validate_arbitrator(arbitrator)
        self._configuration_fingerprint = _configuration_fingerprint(
            config=self.config,
            arbitrator_fingerprint=arbitrator.configuration_fingerprint,
        )

    @property
    def configuration_fingerprint(self) -> str:
        return self._configuration_fingerprint

    def evaluate(self, series: Sequence[float]) -> MultiHorizonReport:
        """Issue and settle forecasts in strict event-time order."""

        values = _coerce_values(series)
        min_train_size = max(
            self.config.min_train_size,
            self.arbitrator.config.min_train_size,
        )
        if len(values) <= min_train_size:
            raise StateSpaceError(
                "series is too short for multi-horizon arbitration",
                context={"reason": "insufficient_multihorizon_history"},
            )

        weights: dict[int, dict[ExpertKind, float] | None] = {
            horizon: None for horizon in self.config.horizons
        }
        pending: dict[int, list[_PendingForecast]] = {}
        steps: dict[int, list[HorizonStep]] = {
            horizon: [] for horizon in self.config.horizons
        }

        for origin_index in range(min_train_size, len(values)):
            should_issue = (
                (origin_index - min_train_size) % self.config.step == 0
            )
            if should_issue:
                training = values[:origin_index]
                for horizon in self.config.horizons:
                    target_index = origin_index + horizon - 1
                    if target_index >= len(values):
                        continue
                    predictive = self.arbitrator.forecast(
                        training,
                        horizon=horizon,
                        weights=weights[horizon],
                    )
                    prior = _weights_from_forecast(predictive)
                    if weights[horizon] is not None:
                        _assert_same_weights(weights[horizon], prior)
                    pending.setdefault(target_index, []).append(
                        _PendingForecast(
                            origin_index=origin_index,
                            target_index=target_index,
                            horizon=horizon,
                            predictive=predictive,
                            prior_weights=prior,
                        )
                    )

            # Settlement intentionally occurs after forecasts for this origin
            # are issued.  The target at origin_index was unavailable at issue
            # time and therefore cannot influence any forecast issued here.
            actual = values[origin_index]
            for item in pending.pop(origin_index, ()):  # type: ignore[arg-type]
                component_scores = {
                    component.expert: component.predictive.log_density(actual)
                    for component in item.predictive.components
                }
                posterior = _posterior_weights(
                    prior=dict(item.prior_weights),
                    log_scores=component_scores,
                    config=self.arbitrator.config,
                )
                weights[item.horizon] = posterior
                error = item.predictive.mean - actual
                steps[item.horizon].append(
                    HorizonStep(
                        origin_index=item.origin_index,
                        target_index=item.target_index,
                        horizon=item.horizon,
                        actual=actual,
                        predictive=item.predictive,
                        prior_weights=item.prior_weights,
                        posterior_weights=_sorted_weights(posterior),
                        component_log_scores=_sorted_scores(component_scores),
                        mixture_log_score=item.predictive.log_density(actual),
                        error=error,
                        absolute_error=abs(error),
                        squared_error=error * error,
                    )
                )

        if pending:
            raise StateSpaceError(
                "matured multi-horizon forecasts were left unsettled",
                context={"reason": "multihorizon_settlement_failure"},
            )

        horizon_reports: list[HorizonReport] = []
        for horizon in self.config.horizons:
            horizon_steps = tuple(steps[horizon])
            if not horizon_steps:
                raise StateSpaceError(
                    "a configured horizon produced no scored forecasts",
                    context={
                        "reason": "insufficient_multihorizon_history",
                        "horizon": horizon,
                    },
                )
            final_weights = horizon_steps[-1].posterior_weights
            horizon_reports.append(
                _build_horizon_report(
                    horizon=horizon,
                    steps=horizon_steps,
                    final_weights=final_weights,
                )
            )

        dependence = _error_dependence(tuple(horizon_reports))
        report_fingerprint = _report_fingerprint(
            configuration_fingerprint=self.configuration_fingerprint,
            horizon_reports=horizon_reports,
            dependence=dependence,
        )
        return MultiHorizonReport(
            config=self.config,
            arbitrator_configuration_fingerprint=(
                self.arbitrator.configuration_fingerprint
            ),
            configuration_fingerprint=self.configuration_fingerprint,
            horizon_reports=tuple(horizon_reports),
            dependence=dependence,
            fingerprint=report_fingerprint,
        )

    def forecast_from_report(
        self,
        series: Sequence[float],
        report: MultiHorizonReport,
    ) -> ForecastLadder:
        """Forecast every horizon from its own last matured posterior state."""

        _validate_report_identity(report, expected=self.configuration_fingerprint)
        values = _coerce_values(series)
        forecasts = tuple(
            (
                horizon_report.horizon,
                self.arbitrator.forecast(
                    values,
                    horizon=horizon_report.horizon,
                    weights=dict(horizon_report.final_weights),
                ),
            )
            for horizon_report in report.horizon_reports
        )
        return ForecastLadder(
            origin_index=len(values),
            source_report_fingerprint=report.fingerprint,
            forecasts=forecasts,
        )


def evaluate_multihorizon_conformal(
    report: MultiHorizonReport,
    *,
    config: ConformalConfig | None = None,
) -> MultiHorizonConformalReport:
    """Calibrate each horizon only from errors completed at that horizon."""

    _validate_report_identity(report, expected=report.configuration_fingerprint)
    config = config or ConformalConfig()
    horizon_evidence: list[HorizonConformalEvidence] = []
    for horizon_report in report.horizon_reports:
        observations = tuple(
            ForecastObservation(
                target_index=step.target_index,
                actual=step.actual,
                predictive=step.predictive,
            )
            for step in horizon_report.steps
        )
        try:
            conformal = evaluate_prequential_conformal(observations, config=config)
        except StateSpaceError as exc:
            raise StateSpaceError(
                "insufficient completed evidence for one conformal horizon",
                context={
                    "reason": "insufficient_multihorizon_conformal_history",
                    "horizon": horizon_report.horizon,
                },
            ) from exc
        horizon_evidence.append(
            HorizonConformalEvidence(
                horizon=horizon_report.horizon,
                source_horizon_fingerprint=horizon_report.fingerprint,
                report=conformal,
            )
        )

    fingerprint = _conformal_report_fingerprint(
        source_report_fingerprint=report.fingerprint,
        evidence=horizon_evidence,
    )
    return MultiHorizonConformalReport(
        source_report_fingerprint=report.fingerprint,
        horizons=tuple(horizon_evidence),
        fingerprint=fingerprint,
    )


def conformalize_forecast_ladder(
    ladder: ForecastLadder,
    evidence: MultiHorizonConformalReport,
) -> ConformalForecastLadder:
    """Attach horizon-specific conformal intervals to a forecast ladder."""

    if ladder.source_report_fingerprint != evidence.source_report_fingerprint:
        raise StateSpaceError(
            "forecast ladder and conformal evidence come from different reports",
            context={"reason": "multihorizon_conformal_source_mismatch"},
        )
    _validate_conformal_report_identity(evidence)
    forecast_horizons = tuple(horizon for horizon, _ in ladder.forecasts)
    evidence_horizons = tuple(item.horizon for item in evidence.horizons)
    if forecast_horizons != evidence_horizons:
        raise StateSpaceError(
            "forecast ladder and conformal evidence horizons differ",
            context={"reason": "multihorizon_conformal_horizon_mismatch"},
        )
    intervals = tuple(
        (
            horizon,
            conformalize_next_forecast(
                forecast,
                evidence.evidence_for(horizon).report,
                target_index=ladder.origin_index + horizon - 1,
            ),
        )
        for horizon, forecast in ladder.forecasts
    )
    return ConformalForecastLadder(
        origin_index=ladder.origin_index,
        source_report_fingerprint=ladder.source_report_fingerprint,
        intervals=intervals,
    )


def _build_horizon_report(
    *,
    horizon: int,
    steps: tuple[HorizonStep, ...],
    final_weights: tuple[tuple[ExpertKind, float], ...],
) -> HorizonReport:
    fingerprint = _horizon_fingerprint(
        horizon=horizon,
        steps=steps,
        final_weights=final_weights,
    )
    return HorizonReport(
        horizon=horizon,
        steps=steps,
        final_weights=final_weights,
        mean_log_score=statistics.fmean(step.mixture_log_score for step in steps),
        mae=statistics.fmean(step.absolute_error for step in steps),
        rmse=math.sqrt(statistics.fmean(step.squared_error for step in steps)),
        bias=statistics.fmean(step.error for step in steps),
        fingerprint=fingerprint,
    )


def _error_dependence(
    reports: tuple[HorizonReport, ...],
) -> HorizonDependence:
    horizons = tuple(report.horizon for report in reports)
    by_horizon = {
        report.horizon: {step.origin_index: step.error for step in report.steps}
        for report in reports
    }
    common = set(by_horizon[horizons[0]])
    for horizon in horizons[1:]:
        common.intersection_update(by_horizon[horizon])
    common_origins = tuple(sorted(common))

    columns = tuple(
        tuple(by_horizon[horizon][origin] for origin in common_origins)
        for horizon in horizons
    )
    covariance = _covariance_matrix(columns)
    correlation = _correlation_matrix(covariance)
    return HorizonDependence(
        horizons=horizons,
        common_origins=common_origins,
        covariance=covariance,
        correlation=correlation,
    )


def _covariance_matrix(
    columns: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    size = len(columns)
    if not columns or len(columns[0]) < 2:
        return tuple(tuple(0.0 for _ in range(size)) for _ in range(size))
    means = tuple(statistics.fmean(column) for column in columns)
    denominator = len(columns[0]) - 1
    rows: list[tuple[float, ...]] = []
    for left, left_mean in zip(columns, means):
        row = []
        for right, right_mean in zip(columns, means):
            value = sum(
                (x - left_mean) * (y - right_mean)
                for x, y in zip(left, right)
            ) / denominator
            row.append(value)
        rows.append(tuple(row))
    return tuple(rows)


def _correlation_matrix(
    covariance: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    size = len(covariance)
    if size == 0:
        return ()
    variances = tuple(max(0.0, covariance[index][index]) for index in range(size))
    rows: list[tuple[float, ...]] = []
    for i in range(size):
        row = []
        for j in range(size):
            if i == j:
                row.append(1.0 if variances[i] > 0.0 else 0.0)
                continue
            denominator = math.sqrt(variances[i] * variances[j])
            if denominator <= 0.0:
                row.append(0.0)
            else:
                value = covariance[i][j] / denominator
                row.append(min(1.0, max(-1.0, value)))
        rows.append(tuple(row))
    return tuple(rows)


def _weights_from_forecast(
    forecast: ArbitratedForecast,
) -> tuple[tuple[ExpertKind, float], ...]:
    pairs = tuple(
        sorted(
            ((component.expert, component.weight) for component in forecast.components),
            key=lambda item: item[0].value,
        )
    )
    _validate_weight_pairs(pairs)
    return pairs


def _assert_same_weights(
    expected: Mapping[ExpertKind, float],
    actual: tuple[tuple[ExpertKind, float], ...],
) -> None:
    if set(expected) != {expert for expert, _ in actual}:
        raise StateSpaceError(
            "arbitrator changed the configured expert set",
            context={"reason": "multihorizon_expert_set_mismatch"},
        )
    for expert, value in actual:
        if abs(expected[expert] - value) > 1e-10:
            raise StateSpaceError(
                "arbitrator did not preserve supplied issue-time weights",
                context={
                    "reason": "multihorizon_weight_custody_failure",
                    "expert": expert.value,
                },
            )


def _validate_weight_pairs(
    weights: tuple[tuple[ExpertKind, float], ...],
) -> None:
    if not weights or len({expert for expert, _ in weights}) != len(weights):
        raise StateSpaceError(
            "expert weights must be non-empty and unique",
            context={"reason": "invalid_multihorizon_weights"},
        )
    total = 0.0
    for expert, weight in weights:
        if not isinstance(expert, ExpertKind):
            raise StateSpaceError(
                "expert weight key must be ExpertKind",
                context={"reason": "invalid_multihorizon_weights"},
            )
        value = _finite("expert_weight", weight)
        if not 0.0 <= value <= 1.0:
            raise StateSpaceError(
                "expert weights must lie in [0, 1]",
                context={"reason": "invalid_multihorizon_weights"},
            )
        total += value
    if abs(total - 1.0) > 1e-9:
        raise StateSpaceError(
            "expert weights must sum to one",
            context={"reason": "invalid_multihorizon_weights"},
        )


def _validate_arbitrator(arbitrator: HorizonArbitrator) -> None:
    if not getattr(arbitrator, "experts", None):
        raise StateSpaceError(
            "multi-horizon arbitrator requires a non-empty expert set",
            context={"reason": "invalid_multihorizon_arbitrator"},
        )
    if not isinstance(getattr(arbitrator, "config", None), CrossFamilyConfig):
        raise StateSpaceError(
            "multi-horizon arbitrator requires CrossFamilyConfig",
            context={"reason": "invalid_multihorizon_arbitrator"},
        )
    fingerprint = getattr(arbitrator, "configuration_fingerprint", None)
    if not isinstance(fingerprint, str) or not fingerprint:
        raise StateSpaceError(
            "multi-horizon arbitrator requires a configuration fingerprint",
            context={"reason": "invalid_multihorizon_arbitrator"},
        )


def _validate_report_identity(
    report: MultiHorizonReport,
    *,
    expected: str,
) -> None:
    if not isinstance(report, MultiHorizonReport):
        raise StateSpaceError(
            "report must be a MultiHorizonReport",
            context={"reason": "invalid_multihorizon_report"},
        )
    if report.configuration_fingerprint != expected:
        raise StateSpaceError(
            "multi-horizon report configuration does not match evaluator",
            context={"reason": "multihorizon_report_mismatch"},
        )
    recalculated_configuration = _configuration_fingerprint(
        config=report.config,
        arbitrator_fingerprint=report.arbitrator_configuration_fingerprint,
    )
    if recalculated_configuration != report.configuration_fingerprint:
        raise StateSpaceError(
            "multi-horizon configuration fingerprint mismatch",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )
    if report.horizons != report.config.horizons:
        raise StateSpaceError(
            "multi-horizon report horizon set is inconsistent",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )
    expected_fingerprint = _report_fingerprint(
        configuration_fingerprint=report.configuration_fingerprint,
        horizon_reports=report.horizon_reports,
        dependence=report.dependence,
    )
    if report.fingerprint != expected_fingerprint:
        raise StateSpaceError(
            "multi-horizon report state fingerprint mismatch",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )


def _validate_conformal_report_identity(
    report: MultiHorizonConformalReport,
) -> None:
    if not isinstance(report, MultiHorizonConformalReport) or not report.horizons:
        raise StateSpaceError(
            "invalid multi-horizon conformal report",
            context={"reason": "invalid_multihorizon_conformal_report"},
        )
    horizons = tuple(item.horizon for item in report.horizons)
    if len(set(horizons)) != len(horizons):
        raise StateSpaceError(
            "conformal horizon evidence must be unique",
            context={"reason": "invalid_multihorizon_conformal_report"},
        )
    expected = _conformal_report_fingerprint(
        source_report_fingerprint=report.source_report_fingerprint,
        evidence=report.horizons,
    )
    if expected != report.fingerprint:
        raise StateSpaceError(
            "multi-horizon conformal fingerprint mismatch",
            context={"reason": "multihorizon_conformal_identity_mismatch"},
        )


def _configuration_fingerprint(
    *,
    config: MultiHorizonConfig,
    arbitrator_fingerprint: str,
) -> str:
    return _digest(
        {
            "arbitrator_configuration_fingerprint": arbitrator_fingerprint,
            "horizons": list(config.horizons),
            "min_train_size": config.min_train_size,
            "schema": "jeeves.multihorizon.config.v1",
            "step": config.step,
        }
    )


def _horizon_fingerprint(
    *,
    horizon: int,
    steps: Sequence[HorizonStep],
    final_weights: Sequence[tuple[ExpertKind, float]],
) -> str:
    return _digest(
        {
            "final_weights": [
                [expert.value, weight] for expert, weight in final_weights
            ],
            "horizon": horizon,
            "schema": "jeeves.multihorizon.horizon.v1",
            "steps": [
                {
                    "actual": step.actual,
                    "component_log_scores": [
                        [expert.value, score]
                        for expert, score in step.component_log_scores
                    ],
                    "mixture_log_score": step.mixture_log_score,
                    "origin_index": step.origin_index,
                    "posterior_weights": [
                        [expert.value, weight]
                        for expert, weight in step.posterior_weights
                    ],
                    "predictive_mean": step.predictive.mean,
                    "predictive_variance": step.predictive.variance,
                    "prior_weights": [
                        [expert.value, weight]
                        for expert, weight in step.prior_weights
                    ],
                    "target_index": step.target_index,
                }
                for step in steps
            ],
        }
    )


def _report_fingerprint(
    *,
    configuration_fingerprint: str,
    horizon_reports: Sequence[HorizonReport],
    dependence: HorizonDependence,
) -> str:
    return _digest(
        {
            "configuration_fingerprint": configuration_fingerprint,
            "dependence": {
                "common_origins": list(dependence.common_origins),
                "correlation": [list(row) for row in dependence.correlation],
                "covariance": [list(row) for row in dependence.covariance],
                "horizons": list(dependence.horizons),
            },
            "horizon_fingerprints": [
                report.fingerprint for report in horizon_reports
            ],
            "schema": "jeeves.multihorizon.report.v1",
        }
    )


def _conformal_report_fingerprint(
    *,
    source_report_fingerprint: str,
    evidence: Sequence[HorizonConformalEvidence],
) -> str:
    return _digest(
        {
            "evidence": [
                {
                    "conformal_fingerprint": item.report.fingerprint,
                    "horizon": item.horizon,
                    "source_horizon_fingerprint": item.source_horizon_fingerprint,
                }
                for item in evidence
            ],
            "schema": "jeeves.multihorizon.conformal.v1",
            "source_report_fingerprint": source_report_fingerprint,
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


def _coerce_values(series: Sequence[float]) -> tuple[float, ...]:
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


def _sorted_weights(
    weights: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(weights.items(), key=lambda item: item[0].value))


def _sorted_scores(
    scores: Mapping[ExpertKind, float],
) -> tuple[tuple[ExpertKind, float], ...]:
    return tuple(sorted(scores.items(), key=lambda item: item[0].value))


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


__all__ = [
    "ConformalForecastLadder",
    "ForecastLadder",
    "HorizonArbitrator",
    "HorizonConformalEvidence",
    "HorizonDependence",
    "HorizonReport",
    "HorizonStep",
    "MultiHorizonArbitrator",
    "MultiHorizonConfig",
    "MultiHorizonConformalReport",
    "MultiHorizonReport",
    "conformalize_forecast_ladder",
    "evaluate_multihorizon_conformal",
]
