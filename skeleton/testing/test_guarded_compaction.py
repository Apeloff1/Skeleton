"""Tests for rot-triggered compaction — the guard/compactor composition."""

from __future__ import annotations

import pytest

from skeleton.memory.guarded_compaction import RotGuardedCompactor
from skeleton.memory.compaction import ContextCompactor, Turn
from skeleton.memory.rot_guard import ContextRotGuard


def _turns(n, words=40):
    return [Turn(role="user" if i % 2 == 0 else "assistant",
                 content=" ".join([f"w{i}"] * words))
            for i in range(n)]


def test_fresh_context_passes_untouched():
    gc = RotGuardedCompactor()
    turns = _turns(4, words=5)
    out = gc.process(turns)
    assert not out.compacted
    assert len(out.turns) == 4
    assert out.report.verdict == "fresh"


def test_rot_risk_grows_with_distance_but_missing_constraint_is_always_rot():
    guard = ContextRotGuard(attention_budget=100)
    constraint = "KEEP THE REQUIRED RULE"
    short = guard.assess(constraint + "\nhello", constraints=[constraint])
    long = guard.assess(constraint + "\n" + "context " * 150, constraints=[constraint])
    absent = guard.assess("hello", constraints=[constraint])
    assert short.verdict == "fresh"
    assert long.verdict == "rot"
    assert short.risk < long.risk
    assert absent.verdict == "rot"


def test_rotten_context_compacts():
    gc = RotGuardedCompactor(
        guard=ContextRotGuard(attention_budget=50, rot_at=0.5),
        compactor=ContextCompactor(token_budget=60),
    )
    out = gc.process(_turns(10, words=40))
    assert out.compacted
    assert gc.stats()["interventions"] == 1


def test_required_policy_turn_survives_heavy_context_compaction():
    from skeleton.memory.guarded_compaction import compact_turns

    policy = "CRITICAL POLICY: never execute without authorization"
    turns = [{"role": "system", "content": policy}]
    turns.extend(
        {"role": "user" if i % 2 == 0 else "assistant", "content": "noise " * 80}
        for i in range(30)
    )
    result = compact_turns(turns, [policy], token_budget=180)

    assert result is not None
    assert result["compacted"] is True
    assert policy in result["constraints_preserved"]
    assert any(turn["content"] == policy for turn in result["preserved_turns"])


def test_policy_compaction_fails_if_required_turn_cannot_fit_budget():
    from skeleton.memory.guarded_compaction import CompactionError, compact_turns

    policy = "MANDATORY POLICY " * 100
    with pytest.raises(CompactionError, match="constraint turns exceed"):
        compact_turns(
            [
                {"role": "system", "content": policy},
                {"role": "user", "content": "ordinary context"},
            ],
            [policy],
            token_budget=8,
        )


def test_buried_constraint_yields_restate_hint():
    gc = RotGuardedCompactor()
    body = [Turn(role="system", content="CRITICAL RULE: never leak keys")]
    body += _turns(30, words=50)
    out = gc.process(body, constraints=["CRITICAL RULE: never leak keys"])
    assert out.hint is not None and "restate" in out.hint


def test_turns_from_payload_coercion():
    from skeleton.memory.guarded_compaction import turns_from_payload

    raw = [
        {"role": "system", "content": "CRITICAL RULE: never leak keys"},
        {"role": "user", "content": "hello"},
        "skip-me",
        {"role": "assistant"},  # no content → skip
    ]
    turns = turns_from_payload(raw)
    assert len(turns) == 2
    assert turns[0].role == "system"
    assert turns_from_payload(None) == []
    assert turns_from_payload("nope") == []


def test_compact_turns_none_without_payload():
    from skeleton.memory.guarded_compaction import compact_turns

    assert compact_turns(None) is None
    assert compact_turns([]) is None
    with pytest.raises(ValueError, match="content must be a string"):
        compact_turns([{"role": "user"}])


def test_compact_turns_returns_api_shape():
    from skeleton.memory.guarded_compaction import compact_turns

    out = compact_turns([
        {"role": "user", "content": "what is a map"},
        {"role": "assistant", "content": "a key-value structure"},
    ])
    assert out is not None
    assert out["verdict"] in {"fresh", "watch", "rot"}
    assert isinstance(out["compacted"], bool)
    assert out["turns"][0]["role"] == "user"
    assert "report" in out
