"""Tests for the deep-pass modules (2026-08-31).

Covers memory/rot_guard.py, intelligence/verifier.py, swarm/handoff.py,
and intelligence/improve_loop.py.
"""

from __future__ import annotations

import pytest

from skeleton.memory.rot_guard import ContextRotGuard
from skeleton.intelligence.verifier import CodeVerifier
from skeleton.swarm.handoff import HandoffRegistry, HandoffError, TaskState
from skeleton.intelligence.improve_loop import ImproveLoop


# ── Context rot guard ────────────────────────────────────────────────────

def test_rot_guard_fresh_short_prompt():
    g = ContextRotGuard()
    report = g.assess("SHORT RULE\n\nanswer the question", constraints=["SHORT RULE"])
    assert report.verdict == "fresh"
    assert report.risk < 0.4


def test_rot_guard_flags_buried_constraint():
    g = ContextRotGuard()
    body = "CRITICAL RULE: never leak keys\n" + ("filler text line\n" * 400)
    report = g.assess(body, constraints=["CRITICAL RULE: never leak keys"])
    assert report.buried                    # constraint sits in the dead zone
    assert report.burial_score > 0.5


def test_rot_guard_dilution_on_huge_context():
    g = ContextRotGuard(attention_budget=100)
    report = g.assess("word " * 600, constraints=[])
    assert report.dilution_score == 1.0
    assert report.verdict in {"watch", "rot"}


def test_rot_guard_restated_constraint_not_buried():
    g = ContextRotGuard()
    body = "RULE: be brief\n" + ("filler\n" * 200) + "RULE: be brief\n"
    report = g.assess(body, constraints=["RULE: be brief"])
    assert report.restated == 1
    assert not report.buried


# ── Code verifier ────────────────────────────────────────────────────────

def test_verifier_accepts_clean_grounded_code():
    v = CodeVerifier()
    code = (
        "def parse_config(raw):\n"
        "    items = {}\n"
        "    for line in raw.splitlines():\n"
        "        if '=' in line:\n"
        "            k, v = line.split('=', 1)\n"
        "            items[k.strip()] = v.strip()\n"
        "    return items\n"
    )
    report = v.verify(code, request="write a parse_config function")
    assert report.score >= 0.7
    assert "parse_config" in code
    assert not report.issues


def test_verifier_flags_unsafe_and_unbalanced():
    v = CodeVerifier()
    report = v.verify("def f(:\n    eval(user_input\n")
    assert report.score < 0.7
    assert any("delimiters" in i or "unsafe" in i for i in report.issues)


def test_verifier_flags_ungrounded_code():
    v = CodeVerifier()
    code = "def unrelated():\n    return 1\n"
    report = v.verify(code, request="implement quaternion normalization")
    assert any("ignores" in i for i in report.issues)


def test_verifier_verdict_adapter_feeds_verification_loop():
    v = CodeVerifier()
    verdict = v.verdict("def f():\n    return 1\n")
    assert 0.0 <= verdict.confidence <= 1.0


# ── A2A handoff ──────────────────────────────────────────────────────────

def test_handoff_full_lifecycle():
    reg = HandoffRegistry()
    env = reg.submit("translate", {"text": "hello"}, requester="planner")
    assert env.state is TaskState.SUBMITTED
    reg.accept(env.task_id, assignee="translator-1")
    reg.complete(env.task_id, artefacts=[{"out": "bonjour"}])
    done = reg.get(env.task_id)
    assert done.state is TaskState.COMPLETED
    assert done.assignee == "translator-1"
    assert done.artefacts[0]["out"] == "bonjour"


def test_handoff_illegal_transition_raises():
    reg = HandoffRegistry()
    env = reg.submit("x", {}, requester="r")
    with pytest.raises(HandoffError):
        reg.complete(env.task_id)  # can't complete before accepting


def test_handoff_open_tasks_filtered_by_capability():
    reg = HandoffRegistry()
    reg.submit("translate", {}, requester="r")
    reg.submit("review", {}, requester="r")
    assert len(reg.open_tasks("translate")) == 1
    assert len(reg.open_tasks()) == 2


def test_handoff_fail_records_error():
    reg = HandoffRegistry()
    env = reg.submit("x", {}, requester="r")
    reg.accept(env.task_id, assignee="a")
    reg.fail(env.task_id, "backend down")
    assert reg.get(env.task_id).error == "backend down"


# ── Improve loop ─────────────────────────────────────────────────────────

def test_improve_loop_keeps_only_strict_improvements():
    loop = ImproveLoop(max_iterations=10)
    scores = iter([0.5, 0.7, 0.6, 0.9])
    def gen(best, i):
        return i
    result = loop.run(seed=0, generate=gen, evaluate=lambda c: next(scores))
    assert result.best_score == 0.9
    assert sum(1 for it in result.iterations if it.improved) == 2


def test_improve_loop_stops_on_patience():
    loop = ImproveLoop(max_iterations=20, patience=2)
    result = loop.run(seed=0, generate=lambda b, i: b, evaluate=lambda c: 0.5)
    assert result.stopped_reason == "patience"
    assert len(result.iterations) == 2


def test_improve_loop_stops_on_target():
    loop = ImproveLoop(max_iterations=50, target=0.95)
    scores = iter([0.5, 0.8, 0.96])
    result = loop.run(seed=0, generate=lambda b, i: i,
                      evaluate=lambda c: next(scores))
    assert result.stopped_reason == "target"
    assert result.best_score == 0.96
