"""ECS game AI: steering, data-only FSM conditions, utility choice, determinism."""
from __future__ import annotations

import math

import pytest

from skeleton.ecs.ai import (
    agent_component,
    brain_component,
    check_condition,
    choose_utility,
    curve,
    install_ai,
    steering,
    validate_condition,
)
from skeleton.ecs.physics import PhysicsConfig, body_components, install_physics
from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import TickScheduler

AGENT = {"max_speed": 4.0, "max_force": 8.0, "radius": 1.0}


def world(seed: int = 0):
    w = LiveWorld(seed=seed)
    s = TickScheduler(fixed_dt=1 / 30)
    install_physics(s, w, PhysicsConfig(gravity=(0, 0)))
    install_ai(s, w, before=("physics.integrate",))
    return w, s


def test_seek_and_flee_point_opposite_ways() -> None:
    fx, fy = steering("seek", (0, 0), (0, 0), AGENT, (10, 0))
    assert (fx, fy) == pytest.approx((4, 0))
    fx2, _ = steering("flee", (0, 0), (0, 0), AGENT, (10, 0))
    assert fx2 == pytest.approx(-4)


def test_arrive_slows_inside_radius() -> None:
    far = steering("arrive", (0, 0), (0, 0), AGENT, (10, 0))
    near = steering("arrive", (0, 0), (0, 0), AGENT, (2, 0))
    assert near[0] == pytest.approx(2.0) and far[0] == pytest.approx(4.0)


def test_pursue_leads_a_moving_target() -> None:
    plain = steering("seek", (0, 0), (0, 0), AGENT, (8, 0))
    lead = steering("pursue", (0, 0), (0, 0), AGENT, (8, 0), target_vel=(0, 3))
    assert plain[1] == 0 and lead[1] > 0


def test_idle_brakes_and_no_target_brakes() -> None:
    assert steering("idle", (0, 0), (2, -1), AGENT, None) == (-2, 1)
    assert steering("seek", (0, 0), (1, 0), AGENT, None) == (-1, 0)


@pytest.mark.parametrize(
    "cond, facts, expected",
    [
        ({"op": "lt", "key": "dist", "value": 3}, {"dist": 2}, True),
        ({"op": "lt", "key": "dist", "value": 3}, {"dist": None}, False),
        ({"op": "eq", "key": "state", "value": "x"}, {"state": "x"}, True),
        ({"all": [{"op": "gt", "key": "a", "value": 1}, {"op": "lt", "key": "b", "value": 1}]}, {"a": 2, "b": 0}, True),
        ({"any": [{"op": "gt", "key": "a", "value": 5}, {"op": "lt", "key": "b", "value": 1}]}, {"a": 2, "b": 0}, True),
        ({"not": {"op": "ge", "key": "a", "value": 1}}, {"a": 0}, True),
        ({"op": "lt", "key": "a", "value": 1}, {"a": "str"}, False),
        ({"always": True}, {}, True),
    ],
)
def test_conditions_are_pure_data(cond, facts, expected) -> None:
    validate_condition(cond)
    assert check_condition(cond, facts) is expected


@pytest.mark.parametrize("bad", ["__import__('os')", {"op": "exec", "key": "x"}, {"all": "x"}, {"op": "lt"}])
def test_invalid_conditions_rejected(bad) -> None:
    with pytest.raises(ValidationError):
        validate_condition(bad)


def test_condition_depth_bound() -> None:
    c: dict = {"always": True}
    for _ in range(12):
        c = {"not": c}
    with pytest.raises(ValidationError):
        validate_condition(c)


def test_utility_curves_and_choice() -> None:
    assert curve("inverse", 0.25) == 0.75
    assert curve("logistic", 0.5) == pytest.approx(0.5)
    assert curve("linear", 0.0) == 0.0
    assert curve("linear", 0.75) == pytest.approx(0.75)
    assert curve("linear", 1.0) == 1.0
    # Out-of-domain utility samples must not be silently clamped into a
    # seemingly valid decision score; the bounded model fails closed.
    with pytest.raises(ValidationError, match=r"within \[0, 1\]"):
        curve("linear", 7)
    with pytest.raises(ValidationError):
        curve("cubic", 0.5)
    opts = [{"action": "wander", "need": "boredom", "weight": 1}, {"action": "flee", "need": "fear", "weight": 1.5, "curve": "quadratic"}]
    assert choose_utility(opts, {"boredom": 0.6, "fear": 0.5})[0] == "wander"
    assert choose_utility(opts, {"boredom": 0.2, "fear": 0.9})[0] == "flee"
    assert choose_utility([], {}) == (None, 0.0)


def test_component_validation() -> None:
    with pytest.raises(ValidationError):
        agent_component(behavior="teleport")
    with pytest.raises(ValidationError):
        agent_component(max_speed=0)
    with pytest.raises(ValidationError):
        agent_component(goal=[1, 2, 3])
    with pytest.raises(ValidationError):
        brain_component("a", [{"from": "a"}])
    with pytest.raises(ValidationError):
        brain_component("a", [], behaviors={"a": "fly"})


def test_hunter_fsm_chases_then_rests() -> None:
    w, s = world()
    prey = w.spawn(body_components(10, 0, static=True))
    brain = brain_component("hunt", [{"from": "hunt", "to": "rest", "when": {"op": "lt", "key": "dist", "value": 1.5}}],
                            behaviors={"hunt": "seek", "rest": "idle"})
    hunter = w.spawn({**body_components(0, 0, r=0.4), "agent": agent_component(target=prey), "brain": brain})
    s.run(w, 200)
    assert w.get(hunter, "brain")["state"] == "rest"
    assert w.get(hunter, "agent")["behavior"] == "idle"
    assert w.get(hunter, "transform")["x"] > 8


def test_flee_increases_distance_and_arrive_settles_on_goal() -> None:
    w, s = world()
    threat = w.spawn(body_components(0, 0, static=True))
    runner = w.spawn({**body_components(1, 0), "agent": agent_component(behavior="flee", target=threat)})
    settler = w.spawn({**body_components(-20, -20), "agent": agent_component(behavior="arrive", goal=[-10, -20])})
    s.run(w, 150)
    assert w.get(runner, "transform")["x"] > 10
    tf = w.get(settler, "transform")
    assert math.hypot(tf["x"] + 10, tf["y"] + 20) < 0.5


def test_utility_drives_behavior_when_fsm_has_no_mapping() -> None:
    w, s = world()
    e = w.spawn({**body_components(0, 0), "agent": agent_component(), "brain": brain_component("free", []),
                 "needs": {"boredom": 0.9, "fear": 0.1},
                 "utility": {"options": [{"action": "wander", "need": "boredom"}, {"action": "flee", "need": "fear"}], "choice": None}})
    s.run(w, 3)
    assert w.get(e, "utility")["choice"] == "wander"
    assert w.get(e, "agent")["behavior"] == "wander"


def test_needs_feed_fsm_facts() -> None:
    w, s = world()
    e = w.spawn({**body_components(0, 0), "agent": agent_component(), "needs": {"hunger": 0.8},
                 "brain": brain_component("idle", [{"to": "forage", "when": {"op": "gt", "key": "need.hunger", "value": 0.5}}])})
    s.run(w, 1)
    assert w.get(e, "brain")["state"] == "forage"


def test_sense_counts_neighbors_and_tracks_dead_targets() -> None:
    w, s = world()
    t = w.spawn(body_components(3, 0, static=True))
    w.spawn(body_components(-3, 0, static=True))
    w.spawn(body_components(50, 0, static=True))
    a = w.spawn({**body_components(0, 0, static=True), "agent": agent_component(target=t), "brain": brain_component("x", [])})
    s.run(w, 1)
    mem = w.get(a, "brain")["memory"]
    assert mem["neighbors"] == 2 and mem["dist"] == pytest.approx(3)
    w.despawn(t)
    s.run(w, 1)
    assert w.get(a, "brain")["memory"]["target_alive"] is False


def test_wander_is_seeded_and_replayable() -> None:
    def run(seed: int) -> str:
        w, s = world(seed)
        for i in range(5):
            w.spawn({**body_components(i * 3, 0, r=0.3), "agent": agent_component(behavior="wander")})
        s.run(w, 120)
        return w.state_digest

    assert run(4) == run(4)
    assert run(4) != run(5)
