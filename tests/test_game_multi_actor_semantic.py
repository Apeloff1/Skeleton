"""GF-P0-184: multi-actor semantic physics on the canonical controllers."""
from __future__ import annotations

import pytest

from skeleton.game.simulation import AABB, CharacterController
from skeleton.game.simulation.multi_actor_semantic import (
    ActorBody, MultiActorError, event_signals, run_actors, step_actors,
)

STEP = 16_000_000  # 16 ms


def actor(aid, x, y=500, z=0, grounded=True, mass=70_000, speed=5_000):
    return ActorBody(CharacterController(aid, (x, y, z), speed, grounded),
                     (300, 500, 300), mass)


def test_controller_intent_respects_speed_budget():
    r = step_actors((actor("a", 0),), {"a": (100_000, 0)}, tick=0, step_ns=STEP)
    assert r.actors[0].controller.position[0] == 5_000 * STEP // 1_000_000_000


def test_actors_collide_and_separate_by_mass():
    heavy = actor("heavy", 0, mass=200_000)
    light = actor("light", 500, mass=50_000)
    r = step_actors((heavy, light), {}, tick=0, step_ns=STEP)
    assert ("heavy", "light") in r.contacts
    pos = {a.actor_id: a.controller.position[0] for a in r.actors}
    assert pos["light"] - pos["heavy"] == 600
    assert 500 - pos["light"] < 0 and abs(pos["heavy"]) < abs(pos["light"] - 500)
    kinds = [e.kind for e in r.events]
    assert "contact_begin" in kinds and "shoved" in kinds


def test_contact_end_event():
    a, b = actor("a", 0), actor("b", 550)
    receipts = run_actors((a, b), [{}, {"b": (5_000, 0)}] + [{"b": (5_000, 0)}] * 3,
                          step_ns=STEP)
    kinds = [e.kind for r in receipts for e in r.events]
    assert "contact_begin" in kinds and "contact_end" in kinds


def test_falling_actor_lands_with_hard_impact():
    faller = actor("f", 0, y=3_000, grounded=False)
    receipts = run_actors((faller,), [{}] * 60, step_ns=STEP)
    events = [e for r in receipts for e in r.events]
    assert events and events[0].kind == "hard_impact"
    assert receipts[-1].actors[0].controller.grounded
    assert receipts[-1].actors[0].controller.position[1] == 500


def test_static_collider_pushes_actor_out():
    wall = AABB("wall", (400, 0, -1000), (1400, 2000, 1000))
    r = step_actors((actor("a", 200),), {}, tick=0, step_ns=STEP, statics=(wall,))
    assert r.actors[0].controller.position[0] == 100
    assert ("a", "wall") in r.contacts


def test_replay_is_bit_exact_and_chained():
    actors = (actor("a", 0), actor("b", 900), actor("c", -900, y=1500, grounded=False))
    intents = [{"a": (4_000, 1_000), "b": (-4_000, 0)}] * 30
    one = run_actors(actors, intents, step_ns=STEP)
    two = run_actors(actors, intents, step_ns=STEP)
    assert [r.state_digest for r in one] == [r.state_digest for r in two]
    assert all(one[i].prev_digest == one[i - 1].state_digest for i in range(1, len(one)))


def test_rejects_bad_inputs():
    with pytest.raises(MultiActorError):
        step_actors((actor("a", 0), actor("a", 5)), {}, tick=0, step_ns=STEP)
    with pytest.raises(MultiActorError):
        step_actors((actor("a", 0),), {"ghost": (1, 1)}, tick=0, step_ns=STEP)
    with pytest.raises(MultiActorError):
        step_actors((actor("a", 0),), {}, tick=0, step_ns=1)
    with pytest.raises(MultiActorError):
        ActorBody(CharacterController("x", (0, 0, 0), 1, True), (0, 1, 1), 1)


def test_event_signals_feed_rpg_environment():
    r = step_actors((actor("a", 0), actor("b", 500)), {}, tick=0, step_ns=STEP)
    sig = event_signals(r)
    assert sig["native_contact_count"] == 1.0
    from skeleton.forge.game_frontier_rpg_events import RPG_ENVIRONMENT_SIGNALS
    assert set(sig) <= RPG_ENVIRONMENT_SIGNALS
