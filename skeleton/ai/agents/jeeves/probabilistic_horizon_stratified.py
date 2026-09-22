"""Regime-conditioned uncertainty evidence for Jeeves multi-horizon forecasts.

This bridge composes delayed multi-horizon arbitration with the hierarchical
conformal and conformal-governance layers.  The composition preserves two
separate custody rules:

* forecast-family weights for horizon ``h`` may learn only after a horizon-h
  target matures; and
* conformal scores for a target may enter a horizon/regime calibration bucket
  only after that target's interval has been issued and scored.

Regime labels are supplied by the caller and are indexed by ``origin_cutoff`` --
the information boundary at which the forecast was issued.  The bridge never
derives a regime from the realized target.  A future forecast ladder likewise
requires an explicit pre-target regime value for every configured horizon.

Governance aggregation in this module is evidence-only.  It does not activate a
model, mutate posterior weights, fetch data, route forecasts, or authorize any
external action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from .probabilistic_conformal_stratified import (
    StratifiedConformalConfig,
    StratifiedConformalReport,
    StratifiedForecastInterval,
    StratifiedForecastObservation,
    conformalize_next_stratified_forecast,
    evaluate_stratified_conformal,
    validate_stratified_conformal_report,
)
from .probabilistic_governance import (
    ConformalGovernanceDecision,
    ConformalGovernanceGate,
    evaluate_conformal_governance,
)
from .probabilistic_horizons import (
    HorizonLadder,
    MultiHorizonArbitrator,
    MultiHorizonReport,
)
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class HorizonStratifiedCalibration:
    """Regime-conditioned conformal evidence for one forecast horizon."""

    horizon: int
    source_summary_fingerprint: str
    report: StratifiedConformalReport
    fingerprint: str

    def __post_init__(self) -> None:
        _positive_integer("horizon", self.horizon)
        _sha256("source_summary_fingerprint", self.source_summary_fingerprint)
        _sha256("fingerprint", self.fingerprint)
        if not isinstance(self.report, StratifiedConformalReport):
            raise StateSpaceError(
                "report must be a StratifiedConformalReport",
                context={"reason": "invalid_horizon_stratified_calibration"},
            )
        if any(
            bucket.key.horizon != self.horizon
            for bucket in self.report.buckets
        ):
            raise StateSpaceError(
                "stratified calibration contains a foreign horizon bucket",
                context={"reason": "horizon_stratified_mismatch"},
            )
        if any(
            step.interval.horizon != self.horizon
            for step in self.report.steps
        ):
            raise StateSpaceError(
                "stratified calibration contains a foreign horizon step",
                context={"reason": "horizon_stratified_mismatch"},
            )


@dataclass(frozen=True, slots=True)
class MultiHorizonStratifiedCalibration:
    """Integrity-bound stratified calibration evidence across horizons."""

    source_report_fingerprint: str
    regime_assignments: tuple[tuple[int, str | None], ...]
    regime_assignment_fingerprint: str
    reports: tuple[HorizonStratifiedCalibration, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        _sha256("source_report_fingerprint", self.source_report_fingerprint)
        _sha256(
            "regime_assignment_fingerprint",
            self.regime_assignment_fingerprint,
        )
        _sha256("fingerprint", self.fingerprint)
        if not self.reports:
            raise StateSpaceError(
                "multi-horizon stratified calibration requires reports",
                context={"reason": "empty_horizon_stratified_calibration"},
            )
        horizons = tuple(item.horizon for item in self.reports)
        if horizons != tuple(sorted(set(horizons))):
            raise StateSpaceError(
                "stratified calibration horizons must be unique and increasing",
                context={"reason": "invalid_horizon_stratified_calibration"},
            )
        _validate_assignment_tuple(self.regime_assignments)

    @property
    def horizons(self) -> tuple[int, ...]:
        return tuple(item.horizon for item in self.reports)

    def report_for(self, horizon: int) -> StratifiedConformalReport:
        for item in self.reports:
            if item.horizon == horizon:
                return item.report
        raise StateSpaceError(
            "horizon is absent from stratified calibration",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class HorizonStratifiedInterval:
    """A future interval authorized by one horizon's calibration evidence."""

    horizon: int
    forecast: StratifiedForecastInterval

    def __post_init__(self) -> None:
        _positive_integer("horizon", self.horizon)
        if not isinstance(self.forecast, StratifiedForecastInterval):
            raise StateSpaceError(
                "forecast must be a StratifiedForecastInterval",
                context={"reason": "invalid_horizon_stratified_interval"},
            )
        if self.forecast.interval.horizon != self.horizon:
            raise StateSpaceError(
                "interval horizon disagrees with wrapper horizon",
                context={"reason": "horizon_stratified_mismatch"},
            )


@dataclass(frozen=True, slots=True)
class MultiHorizonStratifiedIntervalLadder:
    """Regime-conditioned intervals for a complete multi-horizon ladder."""

    source_forecast_ladder_fingerprint: str
    source_calibration_fingerprint: str
    regime_assignments: tuple[tuple[int, str | None], ...]
    intervals: tuple[HorizonStratifiedInterval, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        _sha256(
            "source_forecast_ladder_fingerprint",
            self.source_forecast_ladder_fingerprint,
        )
        _sha256(
            "source_calibration_fingerprint",
            self.source_calibration_fingerprint,
        )
        _sha256("fingerprint", self.fingerprint)
        if not self.intervals:
            raise StateSpaceError(
                "stratified interval ladder cannot be empty",
                context={"reason": "empty_horizon_stratified_interval_ladder"},
            )
        horizons = tuple(item.horizon for item in self.intervals)
        if horizons != tuple(sorted(set(horizons))):
            raise StateSpaceError(
                "interval ladder horizons must be unique and increasing",
                context={"reason": "invalid_horizon_stratified_interval_ladder"},
            )
        _validate_horizon_assignment_tuple(
            self.regime_assignments,
            expected_horizons=horizons,
        )

    def interval_for(self, horizon: int) -> StratifiedForecastInterval:
        for item in self.intervals:
            if item.horizon == horizon:
                return item.forecast
        raise StateSpaceError(
            "horizon is absent from stratified interval ladder",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


@dataclass(frozen=True, slots=True)
class HorizonConformalGovernanceEvidence:
    """Calibration-governance evidence for one forecast horizon."""

    horizon: int
    decision: ConformalGovernanceDecision

    def __post_init__(self) -> None:
        _positive_integer("horizon", self.horizon)
        if not isinstance(self.decision, ConformalGovernanceDecision):
            raise StateSpaceError(
                "decision must be a ConformalGovernanceDecision",
                context={"reason": "invalid_horizon_governance_evidence"},
            )


@dataclass(frozen=True, slots=True)
class MultiHorizonConformalGovernanceEvidence:
    """Evidence-only conjunction of calibration gates across horizons."""

    source_calibration_fingerprint: str
    decisions: tuple[HorizonConformalGovernanceEvidence, ...]
    all_eligible: bool
    fingerprint: str

    def __post_init__(self) -> None:
        _sha256(
            "source_calibration_fingerprint",
            self.source_calibration_fingerprint,
        )
        _sha256("fingerprint", self.fingerprint)
        if not self.decisions:
            raise StateSpaceError(
                "multi-horizon governance evidence requires decisions",
                context={"reason": "empty_horizon_governance_evidence"},
            )
        horizons = tuple(item.horizon for item in self.decisions)
        if horizons != tuple(sorted(set(horizons))):
            raise StateSpaceError(
                "governance horizons must be unique and increasing",
                context={"reason": "invalid_horizon_governance_evidence"},
            )
        if not isinstance(self.all_eligible, bool):
            raise StateSpaceError(
                "all_eligible must be a boolean",
                context={"reason": "invalid_horizon_governance_evidence"},
            )
        if self.all_eligible != all(
            item.decision.eligible for item in self.decisions
        ):
            raise StateSpaceError(
                "all_eligible disagrees with horizon decisions",
                context={"reason": "invalid_horizon_governance_evidence"},
            )

    def decision_for(self, horizon: int) -> ConformalGovernanceDecision:
        for item in self.decisions:
            if item.horizon == horizon:
                return item.decision
        raise StateSpaceError(
            "horizon is absent from governance evidence",
            context={"reason": "missing_horizon", "horizon": horizon},
        )


def evaluate_multihorizon_stratified_conformal(
    arbitrator: MultiHorizonArbitrator,
    report: MultiHorizonReport,
    *,
    regime_by_origin: Mapping[int, str | None],
    config: StratifiedConformalConfig | None = None,
) -> MultiHorizonStratifiedCalibration:
    """Calibrate every horizon using only regimes known at forecast issue time."""

    if not isinstance(arbitrator, MultiHorizonArbitrator):
        raise StateSpaceError(
            "arbitrator must be a MultiHorizonArbitrator",
            context={"reason": "invalid_horizon_stratified_source"},
        )
    if not isinstance(report, MultiHorizonReport):
        raise StateSpaceError(
            "report must be a MultiHorizonReport",
            context={"reason": "invalid_horizon_stratified_source"},
        )
    # The multi-horizon engine owns configuration identity.  Reuse its
    # fail-closed validator before extracting any downstream calibration evidence.
    arbitrator._validate_report_identity(report)
    actual_config = config or StratifiedConformalConfig()
    if not isinstance(actual_config, StratifiedConformalConfig):
        raise StateSpaceError(
            "config must be a StratifiedConformalConfig",
            context={"reason": "invalid_horizon_stratified_config"},
        )

    assignments = _canonical_origin_assignments(
        report,
        regime_by_origin=regime_by_origin,
    )
    assignment_map = dict(assignments)
    assignment_fingerprint = _assignment_fingerprint(assignments)
    horizon_reports: list[HorizonStratifiedCalibration] = []

    for summary in report.summaries:
        observations = tuple(
            StratifiedForecastObservation(
                target_index=step.target_index,
                actual=step.actual,
                predictive=step.forecast.predictive,
                regime=assignment_map[step.origin_cutoff],
            )
            for step in summary.settlements
        )
        calibrated = evaluate_stratified_conformal(
            observations,
            config=actual_config,
        )
        validate_stratified_conformal_report(calibrated)
        fingerprint = _horizon_calibration_fingerprint(
            horizon=summary.horizon,
            source_summary_fingerprint=summary.fingerprint,
            report_fingerprint=calibrated.fingerprint,
        )
        horizon_reports.append(
            HorizonStratifiedCalibration(
                horizon=summary.horizon,
                source_summary_fingerprint=summary.fingerprint,
                report=calibrated,
                fingerprint=fingerprint,
            )
        )

    reports = tuple(horizon_reports)
    fingerprint = _calibration_fingerprint(
        source_report_fingerprint=report.fingerprint,
        regime_assignment_fingerprint=assignment_fingerprint,
        reports=reports,
    )
    return MultiHorizonStratifiedCalibration(
        source_report_fingerprint=report.fingerprint,
        regime_assignments=assignments,
        regime_assignment_fingerprint=assignment_fingerprint,
        reports=reports,
        fingerprint=fingerprint,
    )


def conformalize_multihorizon_ladder_stratified(
    ladder: HorizonLadder,
    calibration: MultiHorizonStratifiedCalibration,
    *,
    regime_by_horizon: Mapping[int, str | None],
) -> MultiHorizonStratifiedIntervalLadder:
    """Issue one integrity-checked stratified interval per future horizon."""

    if not isinstance(ladder, HorizonLadder):
        raise StateSpaceError(
            "ladder must be a HorizonLadder",
            context={"reason": "invalid_horizon_stratified_ladder"},
        )
    validate_multihorizon_stratified_calibration(calibration)
    if ladder.source_report_fingerprint != calibration.source_report_fingerprint:
        raise StateSpaceError(
            "forecast ladder and calibration come from different reports",
            context={"reason": "horizon_stratified_source_mismatch"},
        )

    horizons = tuple(forecast.horizon for forecast in ladder.forecasts)
    future_assignments = _canonical_horizon_assignments(
        regime_by_horizon,
        horizons=horizons,
    )
    assignment_map = dict(future_assignments)
    intervals: list[HorizonStratifiedInterval] = []
    for forecast in ladder.forecasts:
        calibrated = calibration.report_for(forecast.horizon)
        interval = conformalize_next_stratified_forecast(
            forecast.predictive,
            calibrated,
            target_index=forecast.target_index,
            regime=assignment_map[forecast.horizon],
        )
        intervals.append(
            HorizonStratifiedInterval(
                horizon=forecast.horizon,
                forecast=interval,
            )
        )

    frozen_intervals = tuple(intervals)
    fingerprint = _interval_ladder_fingerprint(
        source_forecast_ladder_fingerprint=ladder.fingerprint,
        source_calibration_fingerprint=calibration.fingerprint,
        regime_assignments=future_assignments,
        intervals=frozen_intervals,
    )
    return MultiHorizonStratifiedIntervalLadder(
        source_forecast_ladder_fingerprint=ladder.fingerprint,
        source_calibration_fingerprint=calibration.fingerprint,
        regime_assignments=future_assignments,
        intervals=frozen_intervals,
        fingerprint=fingerprint,
    )


def evaluate_multihorizon_conformal_governance(
    calibration: MultiHorizonStratifiedCalibration,
    *,
    gate: ConformalGovernanceGate | None = None,
) -> MultiHorizonConformalGovernanceEvidence:
    """Evaluate the same calibration evidence gate independently per horizon."""

    validate_multihorizon_stratified_calibration(calibration)
    actual_gate = gate or ConformalGovernanceGate()
    if not isinstance(actual_gate, ConformalGovernanceGate):
        raise StateSpaceError(
            "gate must be a ConformalGovernanceGate",
            context={"reason": "invalid_horizon_governance_gate"},
        )

    decisions = tuple(
        HorizonConformalGovernanceEvidence(
            horizon=item.horizon,
            decision=evaluate_conformal_governance(
                item.report,
                gate=actual_gate,
            ),
        )
        for item in calibration.reports
    )
    all_eligible = all(item.decision.eligible for item in decisions)
    fingerprint = _governance_fingerprint(
        source_calibration_fingerprint=calibration.fingerprint,
        decisions=decisions,
        all_eligible=all_eligible,
    )
    return MultiHorizonConformalGovernanceEvidence(
        source_calibration_fingerprint=calibration.fingerprint,
        decisions=decisions,
        all_eligible=all_eligible,
        fingerprint=fingerprint,
    )


def validate_multihorizon_stratified_calibration(
    calibration: MultiHorizonStratifiedCalibration,
) -> None:
    """Fail closed if wrapped per-horizon calibration evidence was altered."""

    if not isinstance(calibration, MultiHorizonStratifiedCalibration):
        raise StateSpaceError(
            "calibration must be a MultiHorizonStratifiedCalibration",
            context={"reason": "invalid_horizon_stratified_calibration"},
        )
    _validate_assignment_tuple(calibration.regime_assignments)
    expected_assignment = _assignment_fingerprint(calibration.regime_assignments)
    if calibration.regime_assignment_fingerprint != expected_assignment:
        raise StateSpaceError(
            "regime assignment fingerprint mismatch",
            context={"reason": "horizon_stratified_identity_mismatch"},
        )

    seen: set[int] = set()
    for item in calibration.reports:
        if item.horizon in seen:
            raise StateSpaceError(
                "duplicate horizon in stratified calibration",
                context={"reason": "horizon_stratified_identity_mismatch"},
            )
        seen.add(item.horizon)
        validate_stratified_conformal_report(item.report)
        if any(
            bucket.key.horizon != item.horizon
            for bucket in item.report.buckets
        ):
            raise StateSpaceError(
                "stratified report contains a foreign horizon bucket",
                context={"reason": "horizon_stratified_identity_mismatch"},
            )
        expected_item = _horizon_calibration_fingerprint(
            horizon=item.horizon,
            source_summary_fingerprint=item.source_summary_fingerprint,
            report_fingerprint=item.report.fingerprint,
        )
        if item.fingerprint != expected_item:
            raise StateSpaceError(
                "horizon calibration fingerprint mismatch",
                context={
                    "reason": "horizon_stratified_identity_mismatch",
                    "horizon": item.horizon,
                },
            )

    expected = _calibration_fingerprint(
        source_report_fingerprint=calibration.source_report_fingerprint,
        regime_assignment_fingerprint=calibration.regime_assignment_fingerprint,
        reports=calibration.reports,
    )
    if calibration.fingerprint != expected:
        raise StateSpaceError(
            "multi-horizon stratified calibration fingerprint mismatch",
            context={"reason": "horizon_stratified_identity_mismatch"},
        )


def _canonical_origin_assignments(
    report: MultiHorizonReport,
    *,
    regime_by_origin: Mapping[int, str | None],
) -> tuple[tuple[int, str | None], ...]:
    if not isinstance(regime_by_origin, Mapping):
        raise StateSpaceError(
            "regime_by_origin must be a mapping",
            context={"reason": "invalid_pre_target_regime_mapping"},
        )
    used_origins = sorted(
        {
            step.origin_cutoff
            for summary in report.summaries
            for step in summary.settlements
        }
    )
    supplied_keys = set(regime_by_origin)
    for key in supplied_keys:
        _positive_integer("origin_cutoff", key)
    assignments = tuple(
        (origin, _regime_value(regime_by_origin.get(origin)))
        for origin in used_origins
    )
    return assignments


def _canonical_horizon_assignments(
    regime_by_horizon: Mapping[int, str | None],
    *,
    horizons: Sequence[int],
) -> tuple[tuple[int, str | None], ...]:
    if not isinstance(regime_by_horizon, Mapping):
        raise StateSpaceError(
            "regime_by_horizon must be a mapping",
            context={"reason": "invalid_future_regime_mapping"},
        )
    expected = set(horizons)
    supplied = set(regime_by_horizon)
    if supplied != expected:
        raise StateSpaceError(
            "future regime mapping must exactly cover forecast horizons",
            context={
                "reason": "invalid_future_regime_mapping",
                "expected_horizons": sorted(expected),
                "actual_horizons": sorted(supplied),
            },
        )
    return tuple(
        (horizon, _regime_value(regime_by_horizon[horizon]))
        for horizon in horizons
    )


def _validate_assignment_tuple(
    assignments: Sequence[tuple[int, str | None]],
) -> None:
    if not assignments:
        raise StateSpaceError(
            "regime assignments cannot be empty",
            context={"reason": "invalid_pre_target_regime_mapping"},
        )
    origins = tuple(origin for origin, _ in assignments)
    if origins != tuple(sorted(set(origins))):
        raise StateSpaceError(
            "regime assignment origins must be unique and increasing",
            context={"reason": "invalid_pre_target_regime_mapping"},
        )
    for origin, regime in assignments:
        _positive_integer("origin_cutoff", origin)
        _regime_value(regime)


def _validate_horizon_assignment_tuple(
    assignments: Sequence[tuple[int, str | None]],
    *,
    expected_horizons: Sequence[int],
) -> None:
    actual = tuple(horizon for horizon, _ in assignments)
    if actual != tuple(expected_horizons):
        raise StateSpaceError(
            "future regime assignments disagree with interval horizons",
            context={"reason": "invalid_future_regime_mapping"},
        )
    for horizon, regime in assignments:
        _positive_integer("horizon", horizon)
        _regime_value(regime)


def _regime_value(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateSpaceError(
            "regime values must be strings or None",
            context={"reason": "invalid_pre_target_regime"},
        )
    normalized = value.strip()
    if not normalized:
        raise StateSpaceError(
            "regime values cannot be empty",
            context={"reason": "invalid_pre_target_regime"},
        )
    if len(normalized) > 128:
        raise StateSpaceError(
            "regime values must be at most 128 characters",
            context={"reason": "invalid_pre_target_regime"},
        )
    return normalized


def _assignment_fingerprint(
    assignments: Sequence[tuple[int, str | None]],
) -> str:
    return _digest(
        {
            "schema": "jeeves.multihorizon-stratified.assignments.v1",
            "assignments": [list(item) for item in assignments],
        }
    )


def _horizon_calibration_fingerprint(
    *,
    horizon: int,
    source_summary_fingerprint: str,
    report_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.multihorizon-stratified.horizon.v1",
            "horizon": horizon,
            "source_summary_fingerprint": source_summary_fingerprint,
            "report_fingerprint": report_fingerprint,
        }
    )


def _calibration_fingerprint(
    *,
    source_report_fingerprint: str,
    regime_assignment_fingerprint: str,
    reports: Sequence[HorizonStratifiedCalibration],
) -> str:
    return _digest(
        {
            "schema": "jeeves.multihorizon-stratified.calibration.v1",
            "source_report_fingerprint": source_report_fingerprint,
            "regime_assignment_fingerprint": regime_assignment_fingerprint,
            "horizon_fingerprints": [item.fingerprint for item in reports],
        }
    )


def _interval_ladder_fingerprint(
    *,
    source_forecast_ladder_fingerprint: str,
    source_calibration_fingerprint: str,
    regime_assignments: Sequence[tuple[int, str | None]],
    intervals: Sequence[HorizonStratifiedInterval],
) -> str:
    return _digest(
        {
            "schema": "jeeves.multihorizon-stratified.interval-ladder.v1",
            "source_forecast_ladder_fingerprint": (
                source_forecast_ladder_fingerprint
            ),
            "source_calibration_fingerprint": source_calibration_fingerprint,
            "regime_assignments": [list(item) for item in regime_assignments],
            "intervals": [
                {
                    "horizon": item.horizon,
                    "target_index": item.forecast.interval.target_index,
                    "lower": item.forecast.interval.lower,
                    "upper": item.forecast.interval.upper,
                    "effective_alpha": item.forecast.interval.effective_alpha,
                    "stratum_horizon": item.forecast.stratum.horizon,
                    "stratum_regime": item.forecast.stratum.regime,
                    "requested_regime": item.forecast.requested_regime,
                    "used_fallback": item.forecast.used_fallback,
                }
                for item in intervals
            ],
        }
    )


def _governance_fingerprint(
    *,
    source_calibration_fingerprint: str,
    decisions: Sequence[HorizonConformalGovernanceEvidence],
    all_eligible: bool,
) -> str:
    return _digest(
        {
            "schema": "jeeves.multihorizon-conformal-governance.v1",
            "source_calibration_fingerprint": source_calibration_fingerprint,
            "all_eligible": all_eligible,
            "decisions": [
                {
                    "horizon": item.horizon,
                    "fingerprint": item.decision.fingerprint,
                    "eligible": item.decision.eligible,
                    "reasons": list(item.decision.reasons),
                }
                for item in decisions
            ],
        }
    )


def _positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateSpaceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_horizon_stratified_numeric", "field": name},
        )
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_horizon_stratified_identity", "field": name},
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise StateSpaceError(
            f"{name} must be hexadecimal",
            context={"reason": "invalid_horizon_stratified_identity", "field": name},
        ) from exc
    return value


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "HorizonConformalGovernanceEvidence",
    "HorizonStratifiedCalibration",
    "HorizonStratifiedInterval",
    "MultiHorizonConformalGovernanceEvidence",
    "MultiHorizonStratifiedCalibration",
    "MultiHorizonStratifiedIntervalLadder",
    "conformalize_multihorizon_ladder_stratified",
    "evaluate_multihorizon_conformal_governance",
    "evaluate_multihorizon_stratified_conformal",
    "validate_multihorizon_stratified_calibration",
]
