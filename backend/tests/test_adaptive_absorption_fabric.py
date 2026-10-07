from __future__ import annotations

import pytest

from core.adaptive_absorption_fabric import (
    AbsorbLane,
    AbsorbSignal,
    AdaptiveAbsorptionFabric,
    ClaimLifecycle,
    ClaimStage,
    EvolutionContext,
    EvolutionRateController,
    GenerationMetrics,
    GenerationReport,
    GenerationRole,
    serving_feedback_to_signal,
)


SHA = "a" * 64


def _signal(**overrides) -> AbsorbSignal:
    values = {
        "event_id": "evt-1",
        "source_id": "source-1",
        "content_sha256": SHA,
        "novelty": 0.8,
        "utility": 0.9,
        "uncertainty": 0.3,
        "contradiction_risk": 0.1,
        "poisoning_risk": 0.1,
        "retrieval_gap": 0.1,
    }
    values.update(overrides)
    return AbsorbSignal(**values)


def _metrics(**overrides) -> GenerationMetrics:
    values = {
        "verified_information_gain": 0.72,
        "retrieval_lift": 0.64,
        "verification_rate": 0.90,
        "provenance_completeness": 0.995,
        "contradiction_catch_rate": 0.92,
        "poison_rejection_rate": 0.98,
        "duplicate_suppression": 0.78,
        "freshness_score": 0.80,
        "calibration_score": 0.84,
        "cost_efficiency": 0.72,
        "latency_efficiency": 0.75,
        "serving_regression": 0.0,
    }
    values.update(overrides)
    return GenerationMetrics(**values)


def test_evolution_rate_accelerates_on_drift_and_stagnation_but_damps_on_risk():
    controller = EvolutionRateController(base_rate=0.2)
    calm = controller.rate(EvolutionContext())
    pressure = controller.rate(EvolutionContext(drift=0.9, stagnation=0.8, backlog_pressure=0.7))
    risky = controller.rate(EvolutionContext(
        drift=0.9, stagnation=0.8, backlog_pressure=0.7,
        regression_risk=0.9, epistemic_uncertainty=0.9,
    ))
    assert pressure > calm
    assert risky < pressure
    assert controller.minimum <= risky <= controller.maximum


def test_high_risk_signal_gets_adversarial_mirror_even_when_fast_is_primary():
    fabric = AdaptiveAbsorptionFabric()
    route = fabric.route(_signal(
        novelty=1.0, utility=1.0, uncertainty=0.05,
        contradiction_risk=0.45, poisoning_risk=0.05,
    ))
    assert route.primary in set(AbsorbLane)
    assert AbsorbLane.ADVERSARIAL in (route.primary, *route.mirrors)
    assert route.priority > 0


def test_retrieval_gap_is_routed_to_gap_lane_or_mirrored_there():
    fabric = AdaptiveAbsorptionFabric()
    route = fabric.route(_signal(retrieval_gap=1.0, utility=0.9, uncertainty=0.7))
    assert AbsorbLane.GAP in (route.primary, *route.mirrors)


def test_spawned_challengers_are_deterministic_and_cannot_mutate_verification_below_invariant():
    fabric = AdaptiveAbsorptionFabric()
    context = EvolutionContext(drift=1.0, stagnation=1.0, backlog_pressure=1.0)
    first = fabric.spawn_challengers(context, maximum=8)
    second = fabric.spawn_challengers(context, maximum=8)
    assert first == second
    assert len(first) > 1
    assert all(row.role is GenerationRole.CHALLENGER for row in first)
    assert all(row.genome.verification_floor >= fabric.invariants.minimum_verification_rate for row in first)
    assert all(row.generation_id != fabric.champion.generation_id for row in first)


def test_shadow_assignment_is_repeatable_for_replay():
    fabric = AdaptiveAbsorptionFabric()
    challengers = fabric.spawn_challengers(EvolutionContext(drift=0.8), maximum=6)
    signal = _signal(event_id="evt-repeatable")
    assert fabric.shadow_generations(signal, challengers) == fabric.shadow_generations(signal, challengers)


def test_claim_lifecycle_fails_closed_and_requires_attestation_for_verified_state():
    claim = ClaimLifecycle("claim-1")
    with pytest.raises(ValueError):
        claim.transition(ClaimStage.PROMOTED)
    claim = claim.transition(ClaimStage.NORMALIZED).transition(ClaimStage.CLAIMED)
    with pytest.raises(ValueError):
        claim.transition(ClaimStage.VERIFIED)
    claim = claim.transition(ClaimStage.VERIFIED, attestation_id="attestation-1")
    claim = claim.transition(ClaimStage.CANDIDATE).transition(ClaimStage.PROMOTED)
    assert claim.stage is ClaimStage.PROMOTED
    assert claim.attestation_ids == ("attestation-1",)


def test_promotion_rejects_candidate_that_gains_speed_by_weakening_provenance():
    fabric = AdaptiveAbsorptionFabric()
    challenger = fabric.spawn_challengers(EvolutionContext(drift=0.7), maximum=1)[0]
    report = GenerationReport(
        challenger,
        _metrics(
            verified_information_gain=0.95,
            retrieval_lift=0.90,
            cost_efficiency=0.95,
            latency_efficiency=0.95,
            provenance_completeness=0.90,
        ),
        ("e1", "e2", "e3"),
        "snapshot:old",
        1000,
    )
    decision = fabric.select_promotion(_metrics(), (report,))
    assert not decision.accepted
    assert decision.candidate_id is None
    assert any("provenance" in reason for reason in decision.violations)


def test_promotion_selects_measurably_better_safe_pareto_challenger():
    fabric = AdaptiveAbsorptionFabric()
    challengers = fabric.spawn_challengers(EvolutionContext(drift=0.8, stagnation=0.7), maximum=2)
    baseline = _metrics(
        verified_information_gain=0.60,
        retrieval_lift=0.52,
        verification_rate=0.86,
        provenance_completeness=0.99,
        contradiction_catch_rate=0.88,
        poison_rejection_rate=0.96,
        duplicate_suppression=0.68,
        freshness_score=0.70,
        calibration_score=0.78,
        cost_efficiency=0.64,
        latency_efficiency=0.66,
    )
    strong = GenerationReport(
        challengers[0],
        _metrics(),
        ("benchmark", "replay", "canary"),
        "snapshot:g0",
        2500,
    )
    weak = GenerationReport(
        challengers[1],
        _metrics(
            verified_information_gain=0.65,
            retrieval_lift=0.54,
            duplicate_suppression=0.69,
            freshness_score=0.71,
            calibration_score=0.79,
            cost_efficiency=0.65,
            latency_efficiency=0.67,
        ),
        ("benchmark", "replay", "canary"),
        "snapshot:g0",
        2500,
    )
    decision = fabric.select_promotion(baseline, (weak, strong))
    assert decision.accepted
    assert decision.candidate_id == strong.generation.generation_id
    promoted = fabric.promote(strong, baseline)
    assert promoted.champion.generation_id == strong.generation.generation_id
    assert promoted.champion.role is GenerationRole.CHAMPION


def test_promotion_requires_meaningful_shadow_sample_and_rollback_ref():
    fabric = AdaptiveAbsorptionFabric()
    challenger = fabric.spawn_challengers(EvolutionContext(drift=0.8), maximum=1)[0]
    report = GenerationReport(challenger, _metrics(), ("e1", "e2", "e3"), "", 25)
    decision = fabric.select_promotion(_metrics(verified_information_gain=0.60), (report,))
    assert not decision.accepted
    assert any("rollback" in reason for reason in decision.violations)
    assert any("sample" in reason for reason in decision.violations)


def test_serving_feedback_is_one_way_gap_signal_not_a_memory_write():
    signal = serving_feedback_to_signal(
        event_id="feedback-1",
        source_id="serving-outbox",
        content_sha256=SHA,
        retrieval_miss=0.9,
        uncertainty=0.8,
        stale_hit=0.7,
        user_correction=0.6,
    )
    assert signal.modality == "serving-feedback"
    assert signal.retrieval_gap == 0.9
    assert signal.staleness == 0.7
    assert signal.contradiction_risk == 0.6
    route = AdaptiveAbsorptionFabric().route(signal)
    assert AbsorbLane.GAP in (route.primary, *route.mirrors)
