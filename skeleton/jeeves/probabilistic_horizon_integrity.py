"""Fail-closed integrity validation for Jeeves multi-horizon evidence.

The core multi-horizon engine already fingerprints its configuration, settlement
records, summaries, dependence diagnostics, and forecast ladders.  This module
adds a second, semantic validation plane: it recomputes quantities that a digest
alone cannot prove are mutually consistent.

The validator reconstructs every horizon's delayed-feedback clock, verifies that
issue-time weights equal the latest posterior that had actually matured at that
cutoff, recomputes posterior updates and proper scores, checks reported error and
aggregate metrics, and rebuilds the cross-horizon dependence report directly
from settlements.

This is intentionally evidence-only.  Validation does not mutate model state,
fetch data, authorize execution, or turn historical fit into a live decision.
"""

from __future__ import annotations

import math
import statistics
from typing import Mapping, Sequence

from .probabilistic_arbitration import ExpertKind
from .probabilistic_conformal import ConformalConfig
from .probabilistic_horizons import (
    HorizonSettlement,
    HorizonSummary,
    MultiHorizonConfig,
    MultiHorizonConformalReport,
    MultiHorizonReport,
    _build_dependence_report,
    _posterior_weights,
    _report_fingerprint,
    _summary_fingerprint,
    evaluate_multihorizon_conformal as _evaluate_multihorizon_conformal,
)
from .probabilistic_state_space import StateSpaceError

_TOLERANCE = 1e-10


def validate_multihorizon_report(report: MultiHorizonReport) -> MultiHorizonReport:
    """Validate report semantics, temporal custody, and derived diagnostics.

    The engine-bound validator in :mod:`probabilistic_horizons` additionally
    proves that a report belongs to a particular active arbitrator instance.
    This standalone validator cannot recover hidden initial-prior state from a
    report, so it instead proves all self-contained invariants needed by generic
    downstream evidence consumers such as conformal calibration.
    """

    if not isinstance(report, MultiHorizonReport):
        raise StateSpaceError(
            "report must be a MultiHorizonReport",
            context={"reason": "invalid_multihorizon_report"},
        )
    _validate_digest("configuration_fingerprint", report.configuration_fingerprint)
    _validate_digest(
        "arbitration_configuration_fingerprint",
        report.arbitration_configuration_fingerprint,
    )
    _validate_digest("report_fingerprint", report.fingerprint)

    if not report.experts or len(set(report.experts)) != len(report.experts):
        raise StateSpaceError(
            "multi-horizon report experts must be non-empty and unique",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )
    if any(not isinstance(expert, ExpertKind) for expert in report.experts):
        raise StateSpaceError(
            "multi-horizon report contains an invalid expert",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )

    horizons = tuple(summary.horizon for summary in report.summaries)
    if horizons != report.config.horizons:
        raise StateSpaceError(
            "multi-horizon report summaries do not match configured horizons",
            context={"reason": "multihorizon_report_identity_mismatch"},
        )

    for summary in report.summaries:
        _validate_summary(
            summary,
            config=report.config,
            experts=report.experts,
        )

    rebuilt_dependence = _build_dependence_report(
        report.summaries,
        covariance_floor=report.config.covariance_floor,
    )
    if report.dependence != rebuilt_dependence:
        raise StateSpaceError(
            "cross-horizon dependence diagnostics disagree with settlements",
            context={"reason": "multihorizon_dependence_mismatch"},
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
    return report


def evaluate_multihorizon_conformal(
    report: MultiHorizonReport,
    *,
    config: ConformalConfig | None = None,
) -> MultiHorizonConformalReport:
    """Calibrate only after semantic multi-horizon evidence validation."""

    validate_multihorizon_report(report)
    return _evaluate_multihorizon_conformal(report, config=config)


def _validate_summary(
    summary: HorizonSummary,
    *,
    config: MultiHorizonConfig,
    experts: Sequence[ExpertKind],
) -> None:
    _validate_digest("summary_fingerprint", summary.fingerprint)
    settlements = summary.settlements
    if not settlements:
        raise StateSpaceError(
            "multi-horizon summary requires settlements",
            context={
                "reason": "empty_horizon_summary",
                "horizon": summary.horizon,
            },
        )

    expected_experts = set(experts)
    origins = tuple(step.origin_cutoff for step in settlements)
    if origins[0] != config.min_train_size:
        raise StateSpaceError(
            "horizon evidence does not start at the configured training boundary",
            context={
                "reason": "multihorizon_origin_mismatch",
                "horizon": summary.horizon,
            },
        )
    if origins != tuple(range(origins[0], origins[-1] + 1)):
        raise StateSpaceError(
            "horizon forecast origins must be contiguous",
            context={
                "reason": "multihorizon_origin_gap",
                "horizon": summary.horizon,
            },
        )

    by_origin: dict[int, HorizonSettlement] = {}
    by_target: dict[int, HorizonSettlement] = {}
    recomputed_scores: dict[int, tuple[tuple[ExpertKind, float], ...]] = {}
    for settlement in settlements:
        if settlement.horizon != summary.horizon:
            raise StateSpaceError(
                "summary contains evidence from another horizon",
                context={"reason": "horizon_mismatch"},
            )
        if settlement.origin_cutoff in by_origin or settlement.target_index in by_target:
            raise StateSpaceError(
                "horizon evidence contains duplicate origin or target indices",
                context={
                    "reason": "duplicate_multihorizon_event",
                    "horizon": summary.horizon,
                },
            )
        by_origin[settlement.origin_cutoff] = settlement
        by_target[settlement.target_index] = settlement
        recomputed_scores[settlement.origin_cutoff] = _validate_settlement(
            settlement,
            experts=expected_experts,
        )

    first = settlements[0]
    current = dict(first.forecast.issue_weights)
    _validate_weight_mapping(current, experts=expected_experts)
    last_target = max(by_target)
    for cutoff in range(origins[0], last_target + 2):
        matured = by_target.get(cutoff - 1)
        if matured is not None:
            _assert_weight_vector(
                matured.update_prior_weights,
                current,
                reason="multihorizon_update_prior_mismatch",
                horizon=summary.horizon,
                index=matured.target_index,
            )
            posterior = _posterior_weights(
                prior=current,
                log_scores=dict(recomputed_scores[matured.origin_cutoff]),
                config=config,
            )
            _assert_weight_vector(
                matured.posterior_weights,
                posterior,
                reason="multihorizon_posterior_mismatch",
                horizon=summary.horizon,
                index=matured.target_index,
            )
            current = posterior

        issued = by_origin.get(cutoff)
        if issued is not None:
            _assert_weight_vector(
                issued.forecast.issue_weights,
                current,
                reason="multihorizon_issue_weight_custody_failure",
                horizon=summary.horizon,
                index=issued.origin_cutoff,
            )

    _assert_weight_vector(
        summary.final_weights,
        current,
        reason="multihorizon_final_weight_mismatch",
        horizon=summary.horizon,
        index=last_target,
    )

    expected_mean_log_score = statistics.fmean(
        step.mixture_log_score for step in settlements
    )
    expected_mae = statistics.fmean(step.absolute_error for step in settlements)
    expected_rmse = math.sqrt(
        statistics.fmean(step.squared_error for step in settlements)
    )
    expected_effective = statistics.fmean(
        step.forecast.predictive.effective_expert_count for step in settlements
    )
    expected_epistemic = statistics.fmean(
        step.epistemic_share for step in settlements
    )
    for field, actual, expected in (
        ("mean_log_score", summary.mean_log_score, expected_mean_log_score),
        ("mae", summary.mae, expected_mae),
        ("rmse", summary.rmse, expected_rmse),
        (
            "average_effective_expert_count",
            summary.average_effective_expert_count,
            expected_effective,
        ),
        (
            "average_epistemic_share",
            summary.average_epistemic_share,
            expected_epistemic,
        ),
    ):
        _assert_close(
            field,
            actual,
            expected,
            reason="multihorizon_summary_metric_mismatch",
            horizon=summary.horizon,
        )

    expected_summary = _summary_fingerprint(
        horizon=summary.horizon,
        settlements=settlements,
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


def _validate_settlement(
    settlement: HorizonSettlement,
    *,
    experts: set[ExpertKind],
) -> tuple[tuple[ExpertKind, float], ...]:
    predictive = settlement.forecast.predictive
    component_experts = {component.expert for component in predictive.components}
    if component_experts != experts:
        raise StateSpaceError(
            "forecast components do not match report experts",
            context={
                "reason": "multihorizon_expert_set_mismatch",
                "horizon": settlement.horizon,
                "origin_cutoff": settlement.origin_cutoff,
            },
        )

    forecast_weights = {
        component.expert: component.weight for component in predictive.components
    }
    _assert_weight_vector(
        settlement.forecast.issue_weights,
        forecast_weights,
        reason="multihorizon_forecast_weight_mismatch",
        horizon=settlement.horizon,
        index=settlement.origin_cutoff,
    )

    expected_scores = tuple(
        sorted(
            (
                (component.expert, component.predictive.log_density(settlement.actual))
                for component in predictive.components
            ),
            key=lambda item: item[0].value,
        )
    )
    actual_scores = tuple(
        sorted(settlement.component_log_scores, key=lambda item: item[0].value)
    )
    if tuple(expert for expert, _ in actual_scores) != tuple(
        expert for expert, _ in expected_scores
    ):
        raise StateSpaceError(
            "component log-score expert set is inconsistent",
            context={"reason": "incomplete_horizon_scores"},
        )
    for (expert, actual), (_, expected) in zip(actual_scores, expected_scores):
        _assert_close(
            f"component_log_score:{expert.value}",
            actual,
            expected,
            reason="multihorizon_component_score_mismatch",
            horizon=settlement.horizon,
        )

    _assert_close(
        "mixture_log_score",
        settlement.mixture_log_score,
        predictive.log_density(settlement.actual),
        reason="multihorizon_mixture_score_mismatch",
        horizon=settlement.horizon,
    )
    error = predictive.mean - settlement.actual
    _assert_close(
        "absolute_error",
        settlement.absolute_error,
        abs(error),
        reason="multihorizon_error_geometry_mismatch",
        horizon=settlement.horizon,
    )
    _assert_close(
        "squared_error",
        settlement.squared_error,
        error * error,
        reason="multihorizon_error_geometry_mismatch",
        horizon=settlement.horizon,
    )
    expected_share = predictive.epistemic_variance / max(1e-15, predictive.variance)
    expected_share = min(1.0, max(0.0, expected_share))
    _assert_close(
        "epistemic_share",
        settlement.epistemic_share,
        expected_share,
        reason="multihorizon_epistemic_share_mismatch",
        horizon=settlement.horizon,
    )
    return expected_scores


def _assert_weight_vector(
    actual: Sequence[tuple[ExpertKind, float]],
    expected: Mapping[ExpertKind, float],
    *,
    reason: str,
    horizon: int,
    index: int,
) -> None:
    actual_map = dict(actual)
    _validate_weight_mapping(actual_map, experts=set(expected))
    if set(actual_map) != set(expected):
        raise StateSpaceError(
            "expert weight sets differ",
            context={"reason": reason, "horizon": horizon, "index": index},
        )
    for expert in expected:
        if not math.isclose(
            actual_map[expert],
            expected[expert],
            rel_tol=_TOLERANCE,
            abs_tol=_TOLERANCE,
        ):
            raise StateSpaceError(
                "expert weights disagree with reconstructed evidence state",
                context={
                    "reason": reason,
                    "horizon": horizon,
                    "index": index,
                    "expert": expert.value,
                },
            )


def _validate_weight_mapping(
    weights: Mapping[ExpertKind, float],
    *,
    experts: set[ExpertKind],
) -> None:
    if set(weights) != experts:
        raise StateSpaceError(
            "weight mapping does not match expected experts",
            context={"reason": "invalid_horizon_weights"},
        )
    total = 0.0
    for expert, weight in weights.items():
        if not isinstance(expert, ExpertKind) or not math.isfinite(weight):
            raise StateSpaceError(
                "weight mapping contains invalid values",
                context={"reason": "invalid_horizon_weights"},
            )
        if not 0.0 <= weight <= 1.0:
            raise StateSpaceError(
                "weight mapping values must lie in [0, 1]",
                context={"reason": "invalid_horizon_weights"},
            )
        total += weight
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise StateSpaceError(
            "weight mapping must sum to one",
            context={"reason": "invalid_horizon_weights"},
        )


def _assert_close(
    field: str,
    actual: float,
    expected: float,
    *,
    reason: str,
    horizon: int,
) -> None:
    if not math.isfinite(actual) or not math.isfinite(expected) or not math.isclose(
        actual,
        expected,
        rel_tol=_TOLERANCE,
        abs_tol=_TOLERANCE,
    ):
        raise StateSpaceError(
            f"{field} disagrees with recomputed multi-horizon evidence",
            context={"reason": reason, "horizon": horizon, "field": field},
        )


def _validate_digest(field: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{field} must be a lowercase SHA-256 digest",
            context={"reason": "invalid_multihorizon_digest", "field": field},
        )


__all__ = [
    "evaluate_multihorizon_conformal",
    "validate_multihorizon_report",
]
