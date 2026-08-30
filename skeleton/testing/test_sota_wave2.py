"""Tests for the wave-2 SOTA modules (2026-08-30).

Covers memory/distill.py (worth gate, distillation, budgeted store) and
intelligence/verification.py (bounded loop with marginal-gain stop).
"""

from __future__ import annotations

import pytest

from skeleton.memory.distill import (
    DistilledStore,
    distill,
    worth_remembering,
)
from skeleton.intelligence.verification import (
    VerificationLoop,
    VerificationVerdict,
)


# ── Worth gate ───────────────────────────────────────────────────────────

def test_filler_never_remembered():
    assert not worth_remembering("ok")
    assert not worth_remembering("Thanks!")
    assert not worth_remembering("")


def test_substantive_episode_remembered():
    assert worth_remembering("We decided to ship the Rust rewrite on 2026-09-01 because it halves latency")
    assert worth_remembering("OpenAI raised the cache discount to 90%?")


# ── Distillation ─────────────────────────────────────────────────────────

def test_distill_compresses_and_keeps_entities():
    long_text = (
        "The Cairo meeting decided the launch date moves to March 14. "
        "This matters because the Berlin team needs two extra weeks for QA. "
        "Everyone agreed the tradeoff is worth it."
    )
    fact = distill(long_text)
    assert fact.tokens < len(long_text) // 4
    assert "Cairo" in fact.entities or "Berlin" in fact.entities
    assert fact.gist


def test_distilled_store_enforces_budget():
    store = DistilledStore(token_budget=40)
    store.admit("Alpha project decided to ship in Q1 2027 with the new pipeline", importance=0.9)
    store.admit("Beta initiative chose a different vendor after the March review", importance=0.1)
    stats = store.stats()
    assert stats["tokens_used"] <= 40
    assert stats["facts"] >= 1


def test_distilled_store_search_ranks_entity_hits():
    store = DistilledStore(token_budget=10_000)
    store.admit("Oslo office will host the September summit for 200 attendees", importance=0.5)
    store.admit("The team agreed the budget stays flat through 2027 planning", importance=0.5)
    hits = store.search("Oslo summit")
    assert hits and "Oslo" in hits[0].gist


# ── Bounded verification ─────────────────────────────────────────────────

def _scripted_verdicts(verdicts):
    it = iter(verdicts)
    def verify(claim, context):
        return next(it)
    return verify


def test_loop_stops_on_accept_threshold():
    loop = VerificationLoop(max_rounds=5, accept_threshold=0.9)
    verify = _scripted_verdicts([VerificationVerdict(confidence=0.95)])
    claim, trace = loop.run("claim", verify)
    assert trace.rounds == 1 and trace.stopped_reason == "accepted"


def test_loop_stops_on_marginal_gain():
    loop = VerificationLoop(max_rounds=5, min_gain=0.05)
    verify = _scripted_verdicts([
        VerificationVerdict(confidence=0.5),
        VerificationVerdict(confidence=0.52),   # gain 0.02 < 0.05 → stop
        VerificationVerdict(confidence=0.9),    # never reached
    ])
    _, trace = loop.run("claim", verify)
    assert trace.rounds == 2 and trace.stopped_reason == "marginal_gain"


def test_loop_caps_at_max_rounds_and_revises():
    loop = VerificationLoop(max_rounds=2, accept_threshold=0.99)
    verify = _scripted_verdicts([
        VerificationVerdict(confidence=0.3, revised="v2"),
        VerificationVerdict(confidence=0.8, revised="v3"),
    ])
    claim, trace = loop.run("v1", verify)
    assert trace.rounds == 2
    assert trace.stopped_reason == "max_rounds"
    assert claim == "v3"
    assert trace.history == [0.3, 0.8]
