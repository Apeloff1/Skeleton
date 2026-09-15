from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.absorb import AbsorbEngine, AbsorbLane, AbsorbSignals, GateConfig, Verification
from skeleton.jeeves.absorb_evolution import (
    AbsorbEvolutionArena,
    EvolutionContext,
    EvolutionMetrics,
    GenerationEvaluation,
    GenerationRole,
    gate_fingerprint,
)


def _metrics(**overrides) -> EvolutionMetrics:
    values = {
        "verified_information_gain": 0.76,
        "knowledge_gain_per_compute": 0.78,
        "promotion_precision": 0.98,
        "challenge_catch_rate": 0.92,
        "contradiction_rejection": 0.95,
        "duplicate_suppression": 0.82,
        "freshness": 0.86,
        "calibration": 0.88,
        "throughput_efficiency": 0.80,
        "serving_impact": 0.0,
    }
    values.update(overrides)
    return EvolutionMetrics(**values)


def _baseline() -> EvolutionMetrics:
    return _metrics(
        verified_information_gain=0.62,
        knowledge_gain_per_compute=0.65,
        promotion_precision=0.96,
        challenge_catch_rate=0.88,
        contradiction_rejection=0.92,
        duplicate_suppression=0.72,
        freshness=0.76,
        calibration=0.79,
        throughput_efficiency=0.70,
    )


def test_high_drift_spawns_more_challengers_than_calm_context() -> None:
    arena = AbsorbEvolutionArena(AbsorbEngine())
    calm = arena.spawn_challengers(EvolutionContext())
    hot = arena.spawn_challengers(
        EvolutionContext(drift=1.0, stagnation=1.0, backlog_pressure=1.0)
    )
    assert len(hot) > len(calm)
    assert all(row.role is GenerationRole.CHALLENGER for row in hot)


def test_serving_pressure_damps_evolution_and_shadow_budget() -> None:
    arena = AbsorbEvolutionArena(AbsorbEngine())
    low = EvolutionContext(drift=0.8, stagnation=0.8, serving_pressure=0.0)
    high = EvolutionContext(drift=0.8, stagnation=0.8, serving_pressure=1.0)
    assert arena.rate_controller.rate(high) < arena.rate_controller.rate(low)
    assert arena.rate_controller.budget(high, arena.champion.genome).challengers == 0.0


def test_challenger_generation_is_deterministic_for_replay() -> None:
    arena = AbsorbEvolutionArena(AbsorbEngine())
    context = EvolutionContext(drift=0.9, stagnation=0.7)
    assert arena.spawn_challengers(context) == arena.spawn_challengers(context)


def test_shadow_routes_never_install_challenger_router() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    original_router = engine.router
    challengers = arena.spawn_challengers(EvolutionContext(drift=1.0))
    signals = AbsorbSignals(0.9, 0.9, 0.9, 0.8, 0.2, 0.8)
    verification = Verification(confidence=0.45)

    rows = arena.shadow_routes("evt-1", signals, verification, challengers)

    assert engine.router is original_router
    assert len(rows) == len(challengers)
    assert all(row.generation_id != arena.champion.generation_id for row in rows)
    assert all(not row.mirrored or AbsorbLane.FAST in row.lanes for row in rows)


def test_gate_is_non_evolvable_and_mutation_fails_closed() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    original = gate_fingerprint(engine.gate.config)

    engine.gate.config = GateConfig(min_confidence=0.50)

    assert gate_fingerprint(engine.gate.config) != original
    with pytest.raises(Exception, match="promotion gate changed"):
        arena.spawn_challengers(EvolutionContext(drift=1.0))


def test_unsafe_candidate_cannot_trade_precision_for_throughput() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    challenger = arena.spawn_challengers(EvolutionContext(drift=0.8))[0]
    report = GenerationEvaluation(
        generation=challenger,
        metrics=_metrics(promotion_precision=0.80, throughput_efficiency=1.0),
        sample_count=5000,
        evidence_ids=("benchmark", "replay", "canary"),
        rollback_snapshot=1,
        gate_fingerprint=gate_fingerprint(engine.gate.config),
    )

    decision = arena.select_promotion(_baseline(), (report,))

    assert not decision.accepted
    assert decision.candidate_id is None
    assert any("precision" in violation for violation in decision.violations)


def test_serving_impact_is_zero_tolerance_even_for_large_gain() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    challenger = arena.spawn_challengers(EvolutionContext(drift=1.0))[0]
    report = GenerationEvaluation(
        challenger,
        _metrics(
            verified_information_gain=1.0,
            knowledge_gain_per_compute=1.0,
            throughput_efficiency=1.0,
            serving_impact=0.01,
        ),
        10000,
        ("benchmark", "replay", "canary"),
        1,
        gate_fingerprint(engine.gate.config),
    )

    decision = arena.select_promotion(_baseline(), (report,))

    assert not decision.accepted
    assert any("serving impact" in violation for violation in decision.violations)


def test_pareto_selection_prefers_stronger_safe_generation() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    challengers = arena.spawn_challengers(EvolutionContext(drift=0.8, stagnation=0.7))[:2]
    strong = GenerationEvaluation(
        challengers[0], _metrics(), 4000, ("benchmark", "replay", "canary"), 1,
        gate_fingerprint(engine.gate.config),
    )
    weak = GenerationEvaluation(
        challengers[1],
        _metrics(
            verified_information_gain=0.68,
            knowledge_gain_per_compute=0.69,
            duplicate_suppression=0.74,
            freshness=0.78,
            calibration=0.81,
            throughput_efficiency=0.72,
        ),
        4000,
        ("benchmark", "replay", "canary"),
        1,
        gate_fingerprint(engine.gate.config),
    )

    decision = arena.select_promotion(_baseline(), (weak, strong))

    assert decision.accepted
    assert decision.candidate_id == strong.generation.generation_id
    assert strong.generation.generation_id in decision.pareto_frontier
    assert weak.generation.generation_id not in decision.pareto_frontier


def test_promotion_installs_only_router_and_preserves_gate_and_snapshot() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    gate_before = engine.gate
    config_before = engine.gate.config
    snapshot_before = engine.current_snapshot()
    challenger = arena.spawn_challengers(EvolutionContext(drift=0.9))[0]
    report = GenerationEvaluation(
        challenger, _metrics(), 5000, ("benchmark", "replay", "canary"), 1,
        gate_fingerprint(engine.gate.config),
    )

    decision = arena.promote(_baseline(), report)

    assert decision.accepted
    assert arena.champion.generation_id == challenger.generation_id
    assert arena.champion.role is GenerationRole.CHAMPION
    assert engine.gate is gate_before
    assert engine.gate.config == config_before
    assert engine.current_snapshot() is snapshot_before
    assert engine.router.config == challenger.genome.router_config()


def test_promotion_requires_rollback_evidence_and_minimum_shadow_population() -> None:
    engine = AbsorbEngine()
    arena = AbsorbEvolutionArena(engine)
    challenger = arena.spawn_challengers(EvolutionContext(drift=0.7))[0]
    report = GenerationEvaluation(
        challenger,
        _metrics(),
        10,
        ("only-one",),
        None,
        gate_fingerprint(engine.gate.config),
    )

    decision = arena.select_promotion(_baseline(), (report,))

    assert not decision.accepted
    assert any("samples" in item for item in decision.violations)
    assert any("evidence" in item for item in decision.violations)
    assert any("rollback" in item for item in decision.violations)


def test_crossover_stays_shadow_and_respects_resource_constraints() -> None:
    arena = AbsorbEvolutionArena(AbsorbEngine())
    challengers = arena.spawn_challengers(EvolutionContext(drift=1.0))
    child = arena.crossover(challengers[0], challengers[1], sequence=99)
    assert child.role is GenerationRole.CHALLENGER
    assert len(child.parent_ids) == 2
    assert child.genome.challenge_reserve + child.genome.deep_reserve <= 0.85 + 1e-9
    assert child.genome.champion_compute_fraction >= 0.35
