import pytest

from core.evolution_policy import (
    ChangeMode,
    Direction,
    EvolutionCandidate,
    EvolutionPolicy,
    MetricSpec,
)
from core.jeeves_memory import MemoryBank


def test_memory_recall_prefers_query_overlap_and_reflection_bonus():
    bank = MemoryBank(per_agent_capacity=8, recency_half_life_seconds=1000)
    bank.remember("j1", "optimize renderer batching", memory_id="m1", importance=0.5, created_at=100)
    bank.remember("j1", "database migration notes", memory_id="m2", importance=0.9, created_at=100)
    bank.remember_reflection(
        "j1",
        "renderer batching must preserve frame determinism",
        ["m1"],
        importance=0.9,
    )
    rows = bank.recall("j1", "renderer batching", now=100, limit=3)
    assert rows[0].record.kind == "reflection"
    assert rows[0].score > rows[1].score
    assert rows[-1].record.memory_id == "m2"


def test_memory_is_bounded_and_eviction_removes_identity():
    bank = MemoryBank(per_agent_capacity=2)
    bank.remember("j1", "one", memory_id="m1")
    bank.remember("j1", "two", memory_id="m2")
    bank.remember("j1", "three", memory_id="m3")
    assert bank.get("m1") is None
    assert bank.get("m2") is not None
    assert bank.profile("j1")["count"] == 2


def test_reflection_lineage_must_exist_and_stay_with_agent():
    bank = MemoryBank()
    bank.remember("a", "episode a", memory_id="a1")
    bank.remember("b", "episode b", memory_id="b1")
    with pytest.raises(ValueError, match="unknown reflection source"):
        bank.remember_reflection("a", "lesson", ["missing"])
    with pytest.raises(ValueError, match="same agent"):
        bank.remember_reflection("a", "lesson", ["b1"])


def test_evolution_accepts_measured_improvement_with_evidence():
    policy = EvolutionPolicy(
        (
            MetricSpec("quality", Direction.HIGHER, weight=3, max_regression_fraction=0),
            MetricSpec("latency", Direction.LOWER, weight=1, max_regression_fraction=0.10),
        ),
        minimum_evidence=2,
        evolve_minimum_gain=0.001,
    )
    candidate = EvolutionCandidate(
        candidate_id="c2",
        baseline_id="c1",
        metrics={"quality": 0.90, "latency": 90},
        evidence_ids=("test:1", "bench:1"),
    )
    decision = policy.evaluate({"quality": 0.80, "latency": 100}, candidate)
    assert decision.accepted is True
    assert decision.gain > decision.required_gain
    assert decision.violations == ()


def test_evolution_rejects_protected_regression_even_if_other_metric_wins():
    policy = EvolutionPolicy(
        (
            MetricSpec("reliability", Direction.HIGHER, weight=10, max_regression_fraction=0),
            MetricSpec("speed", Direction.HIGHER, weight=1, max_regression_fraction=1),
        )
    )
    candidate = EvolutionCandidate(
        candidate_id="c2",
        baseline_id="c1",
        metrics={"reliability": 0.99, "speed": 1000},
        evidence_ids=("test:1",),
    )
    decision = policy.evaluate({"reliability": 1.0, "speed": 1}, candidate)
    assert decision.accepted is False
    assert any("reliability" in row for row in decision.violations)


def test_mutation_requires_rollback_and_stricter_gain():
    policy = EvolutionPolicy(
        (MetricSpec("quality", Direction.HIGHER),),
        mutation_minimum_gain=0.10,
    )
    no_rollback = EvolutionCandidate(
        candidate_id="mut1",
        baseline_id="base",
        metrics={"quality": 1.2},
        evidence_ids=("e1",),
        mode=ChangeMode.MUTATE,
    )
    assert policy.evaluate({"quality": 1.0}, no_rollback).accepted is False

    weak = EvolutionCandidate(
        candidate_id="mut2",
        baseline_id="base",
        metrics={"quality": 1.05},
        evidence_ids=("e1",),
        mode=ChangeMode.MUTATE,
        rollback_ref="commit:base",
    )
    assert policy.evaluate({"quality": 1.0}, weak).accepted is False

    strong = EvolutionCandidate(
        candidate_id="mut3",
        baseline_id="base",
        metrics={"quality": 1.2},
        evidence_ids=("e1",),
        mode=ChangeMode.MUTATE,
        rollback_ref="commit:base",
    )
    assert policy.evaluate({"quality": 1.0}, strong).accepted is True
