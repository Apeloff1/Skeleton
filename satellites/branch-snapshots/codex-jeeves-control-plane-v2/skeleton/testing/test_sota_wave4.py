"""Tests for wave-4 modules: uncertainty gate, structured contracts,
blackboard, and the recovery executor.
"""

from __future__ import annotations

import pytest

from skeleton.intelligence.uncertainty import Candidate, GateVerdict, UncertaintyGate
from skeleton.intelligence.contract import Contract
from skeleton.swarm.blackboard import Blackboard
from skeleton.resilience.recovery import recover


# ── Uncertainty gate ─────────────────────────────────────────────────────

def test_gate_answers_confident_agreement():
    g = UncertaintyGate()
    d = g.decide([
        Candidate("Paris is the capital", 0.9),
        Candidate("Paris is the capital", 0.85),
        Candidate("Paris is the capital", 0.8),
    ])
    assert d.verdict is GateVerdict.ANSWER
    assert d.best is not None and d.best.confidence == 0.9


def test_gate_abstains_on_divergence():
    g = UncertaintyGate()
    d = g.decide([
        Candidate("alpha", 0.6),
        Candidate("beta", 0.6),
        Candidate("gamma", 0.6),
    ])
    assert d.verdict is GateVerdict.ABSTAIN
    assert d.entropy > 0.9


def test_gate_escalates_low_confidence():
    g = UncertaintyGate()
    d = g.decide([Candidate("maybe this", 0.2), Candidate("or that", 0.2)])
    assert d.verdict is GateVerdict.ESCALATE
    assert g.stats()["escalations"] == 1


def test_gate_abstains_on_empty_candidates():
    g = UncertaintyGate()
    assert g.decide([]).verdict is GateVerdict.ABSTAIN


# ── Structured contracts ─────────────────────────────────────────────────

SCHEMA = {
    "name": {"type": str, "required": True},
    "count": {"type": int, "default": 0, "coerce": True},
    "tags": {"type": list, "default": list},
}


def test_contract_validate_flags_missing_and_wrong_type():
    c = Contract(SCHEMA)
    issues = c.validate({"count": "not a number"})
    problems = {(i.field, i.problem) for i in issues}
    assert ("name", "missing") in problems
    assert ("count", "wrong_type") in problems


def test_contract_repair_fills_defaults_and_coerces():
    c = Contract(SCHEMA)
    out = c.repair({"name": "x", "count": "42", "junk": True})
    assert out.ok
    assert out.payload == {"name": "x", "count": 42, "tags": []}
    assert set(out.repaired) >= {"count", "tags", "junk"}


def test_contract_repair_reports_unfixable():
    c = Contract(SCHEMA)
    out = c.repair({"count": {"nested": True}})
    assert not out.ok
    assert any(i.field == "name" for i in out.issues)


# ── Blackboard ───────────────────────────────────────────────────────────

def test_blackboard_post_read_and_order():
    bb = Blackboard()
    bb.post("intel.prices", {"gold": 100}, producer="scout", confidence=0.4)
    bb.post("intel.prices", {"gold": 101}, producer="oracle", confidence=0.9)
    entries = bb.read("intel.prices")
    assert len(entries) == 2
    assert entries[0].producer == "oracle"  # confidence-ordered


def test_blackboard_expiry():
    clock = [1000.0]
    bb = Blackboard(clock=lambda: clock[0])
    bb.post("t", {}, producer="a", ttl_s=10.0)
    clock[0] = 1011.0
    expired = bb.sweep()
    assert len(expired) == 1
    assert bb.read() == []


def test_blackboard_stats():
    bb = Blackboard()
    bb.post("a", {}, producer="x")
    bb.post("b", {}, producer="y")
    stats = bb.stats()
    assert stats["live"] == 2 and stats["topics"] == ["a", "b"]


# ── Recovery executor ────────────────────────────────────────────────────

def test_recover_transient_retries_then_succeeds():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timed out")
        return "ok"
    out = recover(flaky, sleep=lambda s: None)
    assert out.ok and out.result == "ok"
    assert len(out.attempts) == 3
    assert out.attempts[0].fault_class == "transient"


def test_recover_permanent_fails_fast():
    def forbidden():
        raise PermissionError("403 forbidden")
    out = recover(forbidden, sleep=lambda s: None)
    assert not out.ok
    assert out.final_plan.fault_class.value == "permanent"
    assert len(out.attempts) == 1


def test_recover_context_uses_refresh_hook():
    state = {"refreshed": False, "n": 0}
    def stale():
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("missing context, not seeded")
        return "fresh"
    out = recover(stale,
                  refresh_context=lambda: state.update(refreshed=True),
                  sleep=lambda s: None)
    assert out.ok and state["refreshed"]


def test_recover_logic_uses_replan_hook():
    def bad():
        raise ValueError("the plan chose the wrong tool")
    out = recover(bad, replan=lambda exc: (lambda: "replanned"),
                  sleep=lambda s: None)
    assert out.ok and out.result == "replanned"
