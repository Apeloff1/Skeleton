"""#807 B037: constraint-guided quest synthesis."""
from __future__ import annotations

from skeleton.ai.game_builder.constraint_quest_synthesis import (
    ContentPolicy, WorldModel, synthesize_quest, validate_quest,
)

WORLD = WorldModel(
    start="village",
    edges={"village": ("forest",), "forest": ("cave", "village"), "cave": (), "island": ()},
    npcs={"elder": "village", "hermit": "cave", "pirate": "island"},
)
POLICY = ContentPolicy(banned_terms=("gore",), max_reward_per_step=50, max_total_reward=120)


def _quest(**over):
    q = {"title": "t", "steps": [
        {"id": "a", "location": "village", "npc": "elder", "rewards": [{"kind": "xp", "amount": 10}]},
        {"id": "b", "location": "cave", "npc": "hermit", "requires": ["a"],
         "rewards": [{"kind": "gold", "amount": 20}]},
    ]}
    q.update(over)
    return q


def test_valid_quest_passes() -> None:
    assert validate_quest(_quest(), WORLD, POLICY) == []


def test_unreachable_location_and_npc_rejected() -> None:
    q = _quest(steps=[{"id": "a", "location": "island", "npc": "pirate"}])
    errs = validate_quest(q, WORLD, POLICY)
    assert any("unreachable" in e for e in errs) and len(errs) == 2


def test_prerequisite_order_enforced() -> None:
    q = _quest(steps=[{"id": "a", "location": "village", "requires": ["b"]},
                      {"id": "b", "location": "forest"}])
    assert any("prerequisite" in e for e in validate_quest(q, WORLD, POLICY))


def test_reward_caps_and_kinds_enforced() -> None:
    q = _quest(steps=[{"id": "a", "location": "village", "rewards": [{"kind": "gems", "amount": 999}]}])
    errs = validate_quest(q, WORLD, POLICY)
    assert any("not allowed" in e for e in errs)
    assert any("per-step cap" in e for e in errs)
    assert any("total reward" in e for e in errs)


def test_content_policy_enforced() -> None:
    q = _quest(title="A gore feast")
    assert any("content policy" in e for e in validate_quest(q, WORLD, POLICY))


def test_synthesis_is_seeded_and_always_valid() -> None:
    for seed in range(20):
        a = synthesize_quest(WORLD, POLICY, seed=seed)
        assert a == synthesize_quest(WORLD, POLICY, seed=seed)
        if a["accepted"]:
            assert validate_quest(a["quest"], WORLD, POLICY) == []


def test_impossible_constraints_fail_closed() -> None:
    strict = ContentPolicy(max_reward_per_step=50, max_total_reward=0)
    out = synthesize_quest(WORLD, strict, seed=1, max_attempts=3)
    assert out["accepted"] is False and out["errors"]


def test_quest_synthesis_rejects_unbounded_or_malformed_requests() -> None:
    import pytest
    for opts in ({"seed": True}, {"length": 129}, {"length": 0},
                 {"max_attempts": 65}, {"max_attempts": 0},
                 {"seed": 0, "length": True}):
        with pytest.raises(ValueError):
            synthesize_quest(WORLD, POLICY, **({'seed': 1} | opts))
    with pytest.raises(ValueError):
        synthesize_quest(WORLD, ContentPolicy(allowed_reward_kinds=()), seed=1)
    with pytest.raises(ValueError):
        synthesize_quest(WORLD, ContentPolicy(max_reward_per_step=0), seed=1)


def test_zero_total_reward_is_valid_unsatisfiable_policy_with_rejection_receipt():
    # Zero is a legal, impossible cap. Preserve historical rejection semantics.
    zero = ContentPolicy(max_reward_per_step=10, max_total_reward=0)
    outcome = synthesize_quest(WORLD, zero, seed=11, max_attempts=2)
    assert outcome["accepted"] is False
    assert outcome["attempt"] == 2
    assert "total reward exceeds cap" in outcome["errors"]
    assert synthesize_quest(WORLD, zero, seed=11, max_attempts=2) == outcome
