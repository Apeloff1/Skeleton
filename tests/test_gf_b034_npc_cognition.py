"""Tests for #807 B034 (world-grounded NPC cognition)."""
from __future__ import annotations

import pytest

from skeleton.gameforge.batch_b034 import CognitionError, Entity, NpcMind, WorldState, decide, perceive


def world(*extra, tick=1):
    return WorldState(tick, (Entity("n1", "npc", 0, 0),) + tuple(extra))


def test_perception_is_range_limited_and_sorted():
    w = world(Entity("f1", "food", 3, 0), Entity("f2", "food", 1, 0), Entity("far", "food", 50, 0))
    assert [p.entity_id for p in perceive(w, "n1")] == ["f2", "f1"]


def test_walls_occlude():
    w = world(Entity("w", "wall", 2, 0), Entity("orc", "npc", 4, 0, hostile=True))
    assert perceive(w, "n1") == ()


def test_unknown_npc_rejected():
    with pytest.raises(CognitionError):
        perceive(world(), "ghost")


def test_fallback_flees_when_hurt_and_attacks_when_adjacent():
    w = world(Entity("orc", "npc", 1, 0, hostile=True))
    assert decide(w, NpcMind("n1", health=0.2)).action == "flee"
    d = decide(w, NpcMind("n1"))
    assert (d.action, d.target, d.source) == ("attack", "orc", "fallback")


def test_fallback_hunger_fatigue_social_wander():
    assert decide(world(Entity("f", "food", 1, 0)), NpcMind("n1", hunger=0.9)).action == "eat"
    assert decide(world(Entity("f", "food", 5, 0)), NpcMind("n1", hunger=0.9)).action == "approach"
    assert decide(world(), NpcMind("n1", fatigue=0.8)).action == "rest"
    assert decide(world(Entity("p", "player", 1, 1)), NpcMind("n1")).action == "talk"
    assert decide(world(), NpcMind("n1")).action == "wander"


def test_planner_accepted_when_grounded():
    w = world(Entity("p", "player", 1, 0))
    d = decide(w, NpcMind("n1"), planner=lambda v: {"action": "talk", "target": "p"})
    assert (d.action, d.source) == ("talk", "planner")


def test_planner_cannot_target_unperceived_entity():
    w = world(Entity("p", "player", 1, 0), Entity("hidden", "player", 99, 0))
    d = decide(w, NpcMind("n1"), planner=lambda v: {"action": "attack", "target": "hidden"})
    assert d.source == "fallback" and d.reason == "target not perceived"


def test_planner_view_excludes_unperceived():
    seen = {}
    w = world(Entity("hidden", "player", 99, 0))
    decide(w, NpcMind("n1"), planner=lambda v: seen.update(v) or {"action": "idle"})
    assert seen["percepts"] == []


@pytest.mark.parametrize("planner,reason", [
    (lambda v: {"action": "teleport"}, "invalid action"),
    (lambda v: 1 / 0, "planner error: ZeroDivisionError"),
    (lambda v: None, "invalid action"),
])
def test_planner_faults_fall_back(planner, reason):
    d = decide(world(), NpcMind("n1"), planner=planner)
    assert (d.source, d.reason, d.action) == ("fallback", reason, "wander")


def test_contact_action_on_remembered_but_not_visible_target_falls_back():
    m = NpcMind("n1")
    decide(world(Entity("p", "player", 1, 0), tick=1), m)
    d = decide(world(tick=2), m, planner=lambda v: {"action": "talk", "target": "p"})
    assert d.source == "fallback"
    d2 = decide(world(tick=3), m, planner=lambda v: {"action": "approach", "target": "p"})
    assert d2.source == "planner"


def test_budget_exhausted_uses_fallback():
    d = decide(world(), NpcMind("n1"), planner=lambda v: {"action": "idle"}, budget_calls=0)
    assert d.reason == "budget exhausted"


def test_memory_is_bounded_lru_and_deterministic():
    ents = tuple(Entity(f"f{i}", "food", 1, i % 3) for i in range(10))
    a, b = NpcMind("n1", max_memory=4), NpcMind("n1", max_memory=4)
    for m in (a, b):
        decide(WorldState(1, (Entity("n1", "npc", 0, 0),) + ents), m)
    assert len(a.memory) == 4 and a.digest() == b.digest()


def test_mind_validates_ranges():
    with pytest.raises(CognitionError):
        NpcMind("n1", hunger=1.5)
    with pytest.raises(CognitionError):
        NpcMind("n1", max_memory=0)
