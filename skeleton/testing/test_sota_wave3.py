"""Tests for the wave-3 SOTA modules + the extended non-lexical wordlist.

Covers intelligence/cascade.py, memory/compaction.py,
resilience/faults.py, and the 2026-08-30 NON_LEXICAL_WORDS extension in
memory/distill.py.
"""

from __future__ import annotations

import pytest

from skeleton.intelligence.cascade import (
    CascadeRouter,
    ModelResponse,
    difficulty_estimate,
)
from skeleton.memory.compaction import ContextCompactor, Turn
from skeleton.resilience.faults import FaultClass, classify, recovery_plan
from skeleton.memory.distill import (
    NON_LEXICAL_WORDS,
    is_non_lexical,
    worth_remembering,
)


# ── Cascade router ───────────────────────────────────────────────────────

def _cheap(claim_conf):
    return lambda q: ModelResponse(text="cheap:" + q[:10], confidence=claim_conf)


def _strong():
    return lambda q: ModelResponse(text="strong:" + q[:10], confidence=0.95)


def test_difficulty_scales_with_complexity():
    easy = difficulty_estimate("hi")
    hard = difficulty_estimate(
        "Prove the amortized constraint on this scheduler; "
        "derive the bound formally and optimize the retry policy"
    )
    assert hard > easy
    assert 0.0 <= easy <= 1.0 and 0.0 <= hard <= 1.0


def test_router_serves_confident_cheap_answer():
    r = CascadeRouter(_cheap(0.9), _strong())
    d = r.route("what is a vector")
    assert d.model == "cheap" and not d.escalated
    assert d.reason == "cheap_confident"


def test_router_escalates_low_confidence():
    r = CascadeRouter(_cheap(0.3), _strong())
    d = r.route("what is a vector")
    assert d.model == "strong" and d.escalated
    assert d.reason == "confidence_escalation"
    assert r.escalations == 1


def test_router_strong_direct_on_hard_query():
    r = CascadeRouter(_cheap(0.9), _strong(), route_threshold=0.5)
    d = r.route("Prove and formally derive the theorem on constraint optimization")
    assert d.model == "strong" and not d.escalated
    assert d.reason == "difficulty_threshold"


def test_router_cost_accounting_beats_all_strong():
    r = CascadeRouter(_cheap(0.9), _strong())
    for _ in range(10):
        r.route("simple question")
    stats = r.stats()
    assert stats["cost_vs_all_strong"] < 0.5


# ── Context compaction ───────────────────────────────────────────────────

def _turns(n, words=200):
    return [Turn(role="user" if i % 2 == 0 else "assistant",
                 content=" ".join([f"w{i}"] * words))
            for i in range(n)]


def test_compactor_passes_through_under_budget():
    c = ContextCompactor(token_budget=100_000)
    out = c.compact(_turns(4, words=10))
    assert not out.compacted and out.dropped_turns == 0


def test_compactor_head_tail_and_marker():
    c = ContextCompactor(token_budget=200, head_ratio=0.2)
    out = c.compact(_turns(12, words=40))
    assert out.compacted
    assert out.dropped_turns > 0
    assert out.marker is not None and "compacted" in out.marker
    # head (task) and tail (recent) both preserved around the marker
    assert out.turns[0].role == "user"
    assert out.turns[-1].role == "assistant"
    assert out.total_tokens() <= 220  # budget + marker slack


def test_compactor_rejects_bad_ratio():
    with pytest.raises(ValueError):
        ContextCompactor(head_ratio=1.5)


# ── Failure taxonomy ─────────────────────────────────────────────────────

class _FakeErr(Exception):
    pass


def test_classify_transient():
    assert classify(TimeoutError("timed out")) is FaultClass.TRANSIENT
    assert classify(_FakeErr("rate limit 429")) is FaultClass.TRANSIENT


def test_classify_permanent():
    assert classify(_FakeErr("401 unauthorized")) is FaultClass.PERMANENT
    assert classify(_FakeErr("permission denied")) is FaultClass.PERMANENT


def test_classify_context_and_output_and_logic():
    assert classify(_FakeErr("stale cache, missing context")) is FaultClass.CONTEXT
    assert classify(_FakeErr("JSON parse error: malformed")) is FaultClass.OUTPUT
    assert classify(_FakeErr("the plan chose the wrong tool")) is FaultClass.LOGIC


def test_recovery_plans_match_class():
    t = recovery_plan(TimeoutError("timed out"), attempt=2)
    assert t.action == "retry" and t.backoff_s > 0
    p = recovery_plan(_FakeErr("403 forbidden"))
    assert p.action == "fail" and p.max_attempts == 0
    o = recovery_plan(_FakeErr("validation: must return a dict"))
    assert o.action == "repair"


# ── Extended non-lexical wordlist ────────────────────────────────────────

def test_wordlist_covers_common_filler_forms():
    for w in ["ok", "yep", "thx", "tysm", "gotcha", "mhm", "uh huh",
              "aight", "sounds good", "roger", "copy that", "haha",
              "gtg", "ttyl", "meh", "idk", "takk"]:
        assert w in NON_LEXICAL_WORDS, w
        assert is_non_lexical(w)
        assert is_non_lexical(w.upper())
        assert is_non_lexical(w + "!")


def test_wordlist_never_blocks_real_content():
    assert not is_non_lexical("yes, the plan is approved")
    assert not is_non_lexical("ok so the Rust rewrite ships Tuesday")
    assert worth_remembering("sure, and the budget grows 15% in Q3")
