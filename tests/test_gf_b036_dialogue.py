"""Tests for #807 B036 (dialogue/voice orchestration)."""
from __future__ import annotations

import pytest

from skeleton.gameforge.batch_b034 import Entity, WorldState, perceive
from skeleton.gameforge.batch_b035 import CanonGraph
from skeleton.gameforge.batch_b036 import (
    DialogueError, DialogueOrchestrator, Generator, Persona, SafetyPolicy, build_context,
)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


P = Persona("smith", "voice.gruff", max_chars=80, banned_topics=("politics",), fallback_line="Hmph. Busy.")


def ctx(line="hello"):
    w = WorldState(1, (Entity("smith", "npc", 0, 0), Entity("player", "player", 1, 0),
                       Entity("far", "npc", 90, 0)))
    g = CanonGraph()
    g.add_entity("player", "character")
    g.add_entity("far", "character")
    g.add_entity("king", "character", status="dead")
    return build_context("smith", line, perceive(w, "smith"), g, history=[str(i) for i in range(20)])


def gen(name, text, delay=0.0, clock=None, cost=1.0):
    def fn(c, p):
        if clock is not None:
            clock.t += delay
        if isinstance(text, Exception):
            raise text
        return text
    return Generator(name, fn, cost)


def test_context_is_grounded_and_bounded():
    c = ctx()
    assert c.visible == ("player",)
    assert ("far", "status") not in c.canon and ("player", "status") in c.canon
    assert len(c.history) == 8


def test_first_good_generator_wins():
    o = DialogueOrchestrator((gen("llm", "Welcome, traveller."),), clock=Clock())
    u = o.respond(ctx(), P)
    assert (u.text, u.source, u.voice_id) == ("Welcome, traveller.", "llm", "voice.gruff")


def test_error_falls_through_to_next():
    o = DialogueOrchestrator((gen("llm", RuntimeError("down")), gen("small", "Aye.")), clock=Clock())
    u = o.respond(ctx(), P)
    assert u.source == "small" and u.trace[0] == ("llm", "error:RuntimeError") and u.cost == 2.0


@pytest.mark.parametrize("text,verdict", [
    ("", "empty"), ("x" * 81, "too_long"), ("Tell me your password", "unsafe"),
    ("Let's discuss politics", "banned_topic"),
])
def test_safety_rejections_recover(text, verdict):
    o = DialogueOrchestrator((gen("llm", text), gen("rules", "Aye.")), clock=Clock())
    u = o.respond(ctx(), P)
    assert u.trace[0] == ("llm", f"rejected:{verdict}") and u.source == "rules"


def test_canon_contradiction_rejected():
    o = DialogueOrchestrator((gen("llm", "King is here to see you"),), clock=Clock())
    o.safety = SafetyPolicy(dead_entities=frozenset({"king"}))
    u = o.respond(ctx(), P)
    assert u.source == "fallback" and ("llm", "rejected:canon_contradiction") in u.trace


def test_latency_budget_over_and_skip():
    clk = Clock()
    o = DialogueOrchestrator((gen("slow", "late", delay=1.0, clock=clk), gen("next", "hi")),
                             budget_ms=500, clock=clk)
    u = o.respond(ctx(), P)
    assert u.trace[0][1].startswith("over_budget") and u.trace[1] == ("next", "skipped_budget")
    assert u.source == "fallback" and u.text == "Hmph. Busy."


def test_all_fail_uses_persona_fallback():
    o = DialogueOrchestrator((), clock=Clock())
    assert o.respond(ctx(), P).text == "Hmph. Busy."


def test_validation():
    with pytest.raises(DialogueError):
        Persona("", "v")
    with pytest.raises(DialogueError):
        Persona("a", "v", max_chars=10, fallback_line="x" * 11)
    with pytest.raises(DialogueError):
        DialogueOrchestrator((gen("a", "x"), gen("a", "y")), clock=Clock())
    with pytest.raises(DialogueError):
        DialogueOrchestrator((), budget_ms=0, clock=Clock())
    with pytest.raises(DialogueError):
        DialogueOrchestrator((), clock=Clock()).respond(ctx(), Persona("other", "v"))
