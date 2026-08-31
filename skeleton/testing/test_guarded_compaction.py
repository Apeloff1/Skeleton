"""Tests for rot-triggered compaction — the guard/compactor composition."""

from __future__ import annotations

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


def test_rotten_context_compacts():
    gc = RotGuardedCompactor(
        guard=ContextRotGuard(attention_budget=50, rot_at=0.5),
        compactor=ContextCompactor(token_budget=60),
    )
    out = gc.process(_turns(10, words=40))
    assert out.compacted
    assert gc.stats()["interventions"] == 1


def test_buried_constraint_yields_restate_hint():
    gc = RotGuardedCompactor()
    body = [Turn(role="system", content="CRITICAL RULE: never leak keys")]
    body += _turns(30, words=50)
    out = gc.process(body, constraints=["CRITICAL RULE: never leak keys"])
    assert out.hint is not None and "restate" in out.hint
