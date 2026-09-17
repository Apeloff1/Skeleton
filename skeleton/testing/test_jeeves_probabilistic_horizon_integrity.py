import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    CrossFamilyArbitrator,
    CrossFamilyConfig,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_horizon_integrity import (
    evaluate_multihorizon_conformal,
    validate_multihorizon_report,
)
from skeleton.jeeves.probabilistic_horizons import (
    MultiHorizonArbitrator,
    MultiHorizonConfig,
    _dependence_fingerprint,
    _report_fingerprint,
    _summary_fingerprint,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _series(count: int) -> tuple[float, ...]:
    return tuple(
        20.0
        + 0.04 * index
        + 0.9 * math.sin(2.0 * math.pi * index / 7.0)
        + 0.25 * math.sin(2.0 * math.pi * index / 3.0 + 0.3)
        for index in range(count)
    )


def _engine() -> MultiHorizonArbitrator:
    cross = CrossFamilyArbitrator(
        experts=(
            ExpertKind.LOCAL_LEVEL,
            ExpertKind.LOCAL_LINEAR_TREND,
        ),
        config=CrossFamilyConfig(
            min_train_size=12,
            step=1,
            learning_rate=0.7,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )
    return MultiHorizonArbitrator(
        cross,
        config=MultiHorizonConfig(
            horizons=(1, 2, 4),
            min_train_size=12,
            learning_rate=0.7,
            forgetting_factor=0.99,
            prior_strength=0.02,
            min_weight=1e-3,
            max_log_score_gap=20.0,
        ),
    )


def _refingerprint_report(report, summaries, dependence=None):
    actual_dependence = report.dependence if dependence is None else dependence
    return replace(
        report,
        summaries=tuple(summaries),
        dependence=actual_dependence,
        fingerprint=_report_fingerprint(
            configuration_fingerprint=report.configuration_fingerprint,
            summaries=summaries,
            dependence=actual_dependence,
        ),
    )


def test_valid_report_passes_semantic_integrity_validation() -> None:
    report = _engine().evaluate(_series(44))

    validated = validate_multihorizon_report(report)

    assert validated is report


def test_validator_rejects_aggregate_metric_tampering_not_bound_by_summary_digest() -> None:
    report = _engine().evaluate(_series(44))
    first = report.summaries[0]
    tampered_summary = replace(first, mae=first.mae + 1.0)
    tampered = replace(
        report,
        summaries=(tampered_summary, *report.summaries[1:]),
    )

    # The existing summary digest intentionally contains settlement state and
    # final weights, not the derived aggregate fields.  Semantic validation must
    # therefore catch this independently of a stale-hash check.
    assert tampered_summary.fingerprint == first.fingerprint
    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(tampered)
    assert exc.value.context["reason"] == "multihorizon_summary_metric_mismatch"


def test_validator_rejects_error_geometry_tampering_not_bound_by_summary_digest() -> None:
    report = _engine().evaluate(_series(44))
    first_summary = report.summaries[0]
    first_step = first_summary.settlements[0]
    tampered_step = replace(
        first_step,
        absolute_error=first_step.absolute_error + 2.0,
    )
    tampered_summary = replace(
        first_summary,
        settlements=(tampered_step, *first_summary.settlements[1:]),
    )
    tampered = replace(
        report,
        summaries=(tampered_summary, *report.summaries[1:]),
    )

    # absolute_error is a derived diagnostic and is deliberately recomputed by
    # the semantic validator rather than trusted from the report object.
    assert tampered_summary.fingerprint == first_summary.fingerprint
    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(tampered)
    assert exc.value.context["reason"] == "multihorizon_error_geometry_mismatch"


def test_validator_rejects_forged_delayed_update_chain_even_after_rehashing() -> None:
    report = _engine().evaluate(_series(46))
    summary = report.summary_for(4)
    target = summary.settlements[1]
    forged_prior = tuple(
        (expert, 0.9 if index == 0 else 0.1)
        for index, (expert, _) in enumerate(target.update_prior_weights)
    )
    forged_step = replace(target, update_prior_weights=forged_prior)
    forged_settlements = (
        summary.settlements[0],
        forged_step,
        *summary.settlements[2:],
    )
    forged_summary = replace(
        summary,
        settlements=forged_settlements,
        fingerprint=_summary_fingerprint(
            horizon=summary.horizon,
            settlements=forged_settlements,
            final_weights=summary.final_weights,
        ),
    )
    summaries = tuple(
        forged_summary if item.horizon == 4 else item
        for item in report.summaries
    )
    forged = _refingerprint_report(report, summaries)

    # Both the summary and report hashes now agree with the forged payload.
    # Replaying event-time custody still exposes that the update prior was not
    # the latest posterior available when this target matured.
    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(forged)
    assert exc.value.context["reason"] == "multihorizon_update_prior_mismatch"


def test_validator_rejects_forged_dependence_even_with_consistent_new_hashes() -> None:
    report = _engine().evaluate(_series(46))
    dependence = report.dependence
    assert dependence is not None

    covariance = [list(row) for row in dependence.covariance]
    covariance[0][0] += 5.0
    forged_covariance = tuple(tuple(row) for row in covariance)
    forged_dependence = replace(
        dependence,
        covariance=forged_covariance,
        fingerprint=_dependence_fingerprint(
            horizons=dependence.horizons,
            aligned_origins=dependence.aligned_origins,
            mean_errors=dependence.mean_errors,
            covariance=forged_covariance,
            correlation=dependence.correlation,
        ),
    )
    forged = _refingerprint_report(
        report,
        report.summaries,
        dependence=forged_dependence,
    )

    # A self-consistent forged dependence digest is still insufficient: the
    # validator rebuilds covariance from the underlying aligned settlements.
    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(forged)
    assert exc.value.context["reason"] == "multihorizon_dependence_mismatch"


def test_validator_recomputes_component_and_mixture_proper_scores() -> None:
    report = _engine().evaluate(_series(44))
    summary = report.summaries[0]
    step = summary.settlements[0]
    forged_step = replace(step, mixture_log_score=step.mixture_log_score + 0.5)
    forged_settlements = (forged_step, *summary.settlements[1:])
    forged_summary = replace(
        summary,
        settlements=forged_settlements,
        fingerprint=_summary_fingerprint(
            horizon=summary.horizon,
            settlements=forged_settlements,
            final_weights=summary.final_weights,
        ),
    )
    summaries = (forged_summary, *report.summaries[1:])
    forged = _refingerprint_report(report, summaries)

    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(forged)
    assert exc.value.context["reason"] == "multihorizon_mixture_score_mismatch"


def test_checked_conformal_rejects_tampered_source_before_calibration() -> None:
    report = _engine().evaluate(_series(44))
    first = report.summaries[0]
    tampered = replace(
        report,
        summaries=(
            replace(first, average_epistemic_share=first.average_epistemic_share + 0.1),
            *report.summaries[1:],
        ),
    )

    with pytest.raises(StateSpaceError):
        evaluate_multihorizon_conformal(
            tampered,
            config=ConformalConfig(
                min_calibration=4,
                calibration_window=12,
                adaptive_rate=0.0,
            ),
        )


def test_checked_conformal_preserves_per_horizon_calibration_on_valid_report() -> None:
    report = _engine().evaluate(_series(44))
    calibrated = evaluate_multihorizon_conformal(
        report,
        config=ConformalConfig(
            min_calibration=4,
            calibration_window=12,
            adaptive_rate=0.0,
        ),
    )

    assert calibrated.source_report_fingerprint == report.fingerprint
    assert tuple(item.horizon for item in calibrated.reports) == (1, 2, 4)
    assert all(item.report.steps for item in calibrated.reports)


def test_validator_rejects_forecast_component_weight_drift() -> None:
    report = _engine().evaluate(_series(44))
    summary = report.summaries[0]
    step = summary.settlements[0]
    components = step.forecast.predictive.components
    first_component = replace(components[0], weight=components[0].weight + 0.05)
    second_component = replace(components[1], weight=components[1].weight - 0.05)
    predictive = replace(
        step.forecast.predictive,
        components=(first_component, second_component),
    )
    forecast = replace(step.forecast, predictive=predictive)
    forged_step = replace(step, forecast=forecast)
    forged_settlements = (forged_step, *summary.settlements[1:])
    forged_summary = replace(
        summary,
        settlements=forged_settlements,
        fingerprint=_summary_fingerprint(
            horizon=summary.horizon,
            settlements=forged_settlements,
            final_weights=summary.final_weights,
        ),
    )
    forged = _refingerprint_report(
        report,
        (forged_summary, *report.summaries[1:]),
    )

    with pytest.raises(StateSpaceError) as exc:
        validate_multihorizon_report(forged)
    assert exc.value.context["reason"] == "multihorizon_forecast_weight_mismatch"
