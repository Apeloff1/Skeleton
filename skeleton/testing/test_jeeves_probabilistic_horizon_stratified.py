import math
from dataclasses import replace

import pytest

from skeleton.jeeves.probabilistic_arbitration import (
    CrossFamilyArbitrator,
    CrossFamilyConfig,
    ExpertKind,
)
from skeleton.jeeves.probabilistic_conformal import ConformalConfig
from skeleton.jeeves.probabilistic_conformal_stratified import (
    StratifiedConformalConfig,
)
from skeleton.jeeves.probabilistic_governance import ConformalGovernanceGate
from skeleton.jeeves.probabilistic_horizon_stratified import (
    conformalize_multihorizon_ladder_stratified,
    evaluate_multihorizon_conformal_governance,
    evaluate_multihorizon_stratified_conformal,
    validate_multihorizon_stratified_calibration,
)
from skeleton.jeeves.probabilistic_horizons import (
    MultiHorizonArbitrator,
    MultiHorizonConfig,
)
from skeleton.jeeves.probabilistic_state_space import StateSpaceError


def _series(count: int) -> tuple[float, ...]:
    return tuple(
        15.0
        + 0.05 * index
        + 0.8 * math.sin(2.0 * math.pi * index / 8.0)
        + 0.2 * math.sin(2.0 * math.pi * index / 3.0 + 0.4)
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
            step=2,
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


def _config(*, fallback: bool = True) -> StratifiedConformalConfig:
    return StratifiedConformalConfig(
        conformal=ConformalConfig(
            alpha=0.10,
            min_calibration=4,
            calibration_window=16,
            adaptive_rate=0.0,
            min_alpha=0.01,
            max_alpha=0.40,
        ),
        condition_on_regime=True,
        fallback_to_horizon=fallback,
        max_regimes=8,
    )


def _regimes(report) -> dict[int, str]:
    origins = {
        step.origin_cutoff
        for summary in report.summaries
        for step in summary.settlements
    }
    return {
        origin: "calm" if origin % 2 else "volatile"
        for origin in origins
    }


def _permissive_gate() -> ConformalGovernanceGate:
    return ConformalGovernanceGate(
        min_scored_steps=1,
        max_absolute_coverage_gap=1.0,
        max_bucket_coverage_gap=1.0,
        max_fallback_rate=1.0,
        min_evidenced_buckets=1,
        min_regime_buckets=0,
        min_bucket_uses=1,
    )


def test_stratified_calibration_keeps_horizon_and_regime_buckets_separate() -> None:
    engine = _engine()
    report = engine.evaluate(_series(48))
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )

    assert calibration.horizons == (1, 2, 4)
    for horizon in calibration.horizons:
        current = calibration.report_for(horizon)
        keys = {(bucket.key.horizon, bucket.key.regime) for bucket in current.buckets}
        assert (horizon, None) in keys
        assert (horizon, "calm") in keys
        assert (horizon, "volatile") in keys
        assert all(key_horizon == horizon for key_horizon, _ in keys)


def test_regime_labels_are_bound_to_forecast_origin_not_realized_target() -> None:
    engine = _engine()
    report = engine.evaluate(_series(48))
    regimes = _regimes(report)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=regimes,
        config=_config(),
    )

    for summary in report.summaries:
        by_target = {
            step.target_index: step.origin_cutoff
            for step in summary.settlements
        }
        calibrated = calibration.report_for(summary.horizon)
        for step in calibrated.steps:
            origin = by_target[step.interval.target_index]
            assert step.requested_regime == regimes[origin]


def test_stratified_calibration_is_deterministic_and_integrity_checked() -> None:
    engine = _engine()
    report = engine.evaluate(_series(46))
    regimes = _regimes(report)

    left = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=regimes,
        config=_config(),
    )
    right = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=regimes,
        config=_config(),
    )

    assert left == right
    assert left.fingerprint == right.fingerprint
    assert left.regime_assignment_fingerprint == right.regime_assignment_fingerprint
    validate_multihorizon_stratified_calibration(left)


def test_regime_assignment_identity_changes_when_pre_target_context_changes() -> None:
    engine = _engine()
    report = engine.evaluate(_series(46))
    regimes = _regimes(report)
    changed = dict(regimes)
    first_origin = min(changed)
    changed[first_origin] = (
        "volatile" if changed[first_origin] == "calm" else "calm"
    )

    left = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=regimes,
        config=_config(),
    )
    right = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=changed,
        config=_config(),
    )

    assert left.regime_assignment_fingerprint != right.regime_assignment_fingerprint
    assert left.fingerprint != right.fingerprint


def test_missing_regime_fails_closed_when_horizon_fallback_is_disabled() -> None:
    engine = _engine()
    report = engine.evaluate(_series(44))
    regimes = _regimes(report)
    regimes.pop(min(regimes))

    with pytest.raises(StateSpaceError):
        evaluate_multihorizon_stratified_conformal(
            engine,
            report,
            regime_by_origin=regimes,
            config=_config(fallback=False),
        )


def test_future_ladder_uses_fine_regime_bucket_when_evidence_is_available() -> None:
    values = _series(48)
    engine = _engine()
    report = engine.evaluate(values)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    ladder = engine.forecast_ladder(values, report)
    intervals = conformalize_multihorizon_ladder_stratified(
        ladder,
        calibration,
        regime_by_horizon={1: "calm", 2: "calm", 4: "calm"},
    )

    assert tuple(item.horizon for item in intervals.intervals) == (1, 2, 4)
    for item in intervals.intervals:
        assert item.forecast.interval.horizon == item.horizon
        assert item.forecast.stratum.horizon == item.horizon
        assert item.forecast.stratum.regime == "calm"
        assert item.forecast.requested_regime == "calm"
        assert not item.forecast.used_fallback
        source = ladder.forecast_for(item.horizon)
        assert item.forecast.interval.target_index == source.target_index


def test_unseen_future_regime_falls_back_only_to_same_horizon() -> None:
    values = _series(48)
    engine = _engine()
    report = engine.evaluate(values)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    ladder = engine.forecast_ladder(values, report)
    intervals = conformalize_multihorizon_ladder_stratified(
        ladder,
        calibration,
        regime_by_horizon={1: "novel", 2: "novel", 4: "novel"},
    )

    for item in intervals.intervals:
        assert item.forecast.requested_regime == "novel"
        assert item.forecast.stratum.horizon == item.horizon
        assert item.forecast.stratum.regime is None
        assert item.forecast.used_fallback


def test_future_regime_mapping_must_exactly_cover_ladder_horizons() -> None:
    values = _series(46)
    engine = _engine()
    report = engine.evaluate(values)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    ladder = engine.forecast_ladder(values, report)

    with pytest.raises(StateSpaceError):
        conformalize_multihorizon_ladder_stratified(
            ladder,
            calibration,
            regime_by_horizon={1: "calm", 2: "calm"},
        )

    with pytest.raises(StateSpaceError):
        conformalize_multihorizon_ladder_stratified(
            ladder,
            calibration,
            regime_by_horizon={
                1: "calm",
                2: "calm",
                4: "calm",
                8: "calm",
            },
        )


def test_ladder_rejects_calibration_from_another_historical_report() -> None:
    engine = _engine()
    left_values = _series(46)
    right_values = tuple(value + 0.03 * index for index, value in enumerate(_series(46)))
    left_report = engine.evaluate(left_values)
    right_report = engine.evaluate(right_values)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        left_report,
        regime_by_origin=_regimes(left_report),
        config=_config(),
    )
    ladder = engine.forecast_ladder(right_values, right_report)

    assert ladder.source_report_fingerprint != calibration.source_report_fingerprint
    with pytest.raises(StateSpaceError):
        conformalize_multihorizon_ladder_stratified(
            ladder,
            calibration,
            regime_by_horizon={1: "calm", 2: "calm", 4: "calm"},
        )


def test_governance_is_evaluated_independently_for_every_horizon() -> None:
    engine = _engine()
    report = engine.evaluate(_series(48))
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    evidence = evaluate_multihorizon_conformal_governance(
        calibration,
        gate=_permissive_gate(),
    )

    assert evidence.all_eligible
    assert tuple(item.horizon for item in evidence.decisions) == (1, 2, 4)
    assert all(item.decision.eligible for item in evidence.decisions)
    assert all(
        item.decision.reasons == ("conformal_evidence_gate_passed",)
        for item in evidence.decisions
    )


def test_one_weak_horizon_prevents_all_horizons_evidence_flag() -> None:
    engine = _engine()
    report = engine.evaluate(_series(48))
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    evidence = evaluate_multihorizon_conformal_governance(
        calibration,
        gate=ConformalGovernanceGate(
            min_scored_steps=10_000,
            max_absolute_coverage_gap=1.0,
            max_bucket_coverage_gap=1.0,
            max_fallback_rate=1.0,
            min_evidenced_buckets=0,
            min_regime_buckets=0,
            min_bucket_uses=1,
        ),
    )

    assert not evidence.all_eligible
    assert all(not item.decision.eligible for item in evidence.decisions)
    assert all(
        "insufficient_conformal_steps" in item.decision.reasons
        for item in evidence.decisions
    )


def test_tampered_assignment_state_is_rejected_before_governance_or_forecast() -> None:
    values = _series(46)
    engine = _engine()
    report = engine.evaluate(values)
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    first_origin, first_regime = calibration.regime_assignments[0]
    tampered = replace(
        calibration,
        regime_assignments=(
            (first_origin, "altered" if first_regime != "altered" else "other"),
            *calibration.regime_assignments[1:],
        ),
    )

    with pytest.raises(StateSpaceError):
        validate_multihorizon_stratified_calibration(tampered)

    with pytest.raises(StateSpaceError):
        evaluate_multihorizon_conformal_governance(
            tampered,
            gate=_permissive_gate(),
        )

    ladder = engine.forecast_ladder(values, report)
    with pytest.raises(StateSpaceError):
        conformalize_multihorizon_ladder_stratified(
            ladder,
            tampered,
            regime_by_horizon={1: "calm", 2: "calm", 4: "calm"},
        )


def test_tampered_child_report_is_rejected() -> None:
    engine = _engine()
    report = engine.evaluate(_series(46))
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=_regimes(report),
        config=_config(),
    )
    first = calibration.reports[0]
    tampered_child = replace(
        first,
        report=replace(first.report, fingerprint="0" * 64),
    )
    tampered = replace(
        calibration,
        reports=(tampered_child, *calibration.reports[1:]),
    )

    with pytest.raises(StateSpaceError):
        validate_multihorizon_stratified_calibration(tampered)


def test_regime_values_are_normalized_before_becoming_evidence() -> None:
    engine = _engine()
    report = engine.evaluate(_series(44))
    regimes = {
        origin: "  calm  "
        for origin in _regimes(report)
    }
    calibration = evaluate_multihorizon_stratified_conformal(
        engine,
        report,
        regime_by_origin=regimes,
        config=_config(),
    )

    assert {regime for _, regime in calibration.regime_assignments} == {"calm"}
    for item in calibration.reports:
        assert all(
            bucket.key.regime in (None, "calm")
            for bucket in item.report.buckets
        )


@pytest.mark.parametrize(
    "bad_value",
    ["", "   ", 7, True, "x" * 129],
)
def test_invalid_pre_target_regime_values_fail_closed(bad_value: object) -> None:
    engine = _engine()
    report = engine.evaluate(_series(44))
    regimes: dict[int, object] = _regimes(report)
    regimes[min(regimes)] = bad_value

    with pytest.raises(StateSpaceError):
        evaluate_multihorizon_stratified_conformal(
            engine,
            report,
            regime_by_origin=regimes,  # type: ignore[arg-type]
            config=_config(),
        )


def test_boolean_origin_key_is_rejected_even_though_bool_is_an_int_subclass() -> None:
    engine = _engine()
    report = engine.evaluate(_series(44))
    regimes = _regimes(report)
    regimes[True] = "calm"

    with pytest.raises(StateSpaceError):
        evaluate_multihorizon_stratified_conformal(
            engine,
            report,
            regime_by_origin=regimes,
            config=_config(),
        )
