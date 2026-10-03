"""ECS 2D physics: integration, narrowphase, resolution, events, determinism."""
from __future__ import annotations

import pytest

from skeleton.ecs.physics import (
    CONTACT_CHANNEL,
    PhysicsConfig,
    body_components,
    broadphase,
    contacts_for,
    install_physics,
    manifold,
    q,
)
from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import TickScheduler


def make(config: PhysicsConfig | None = None, seed: int = 0):
    w = LiveWorld(seed=seed)
    s = TickScheduler(fixed_dt=1 / 60)
    install_physics(s, w, config)
    return w, s


def test_quantise_is_stable_and_squashes_negative_zero() -> None:
    assert q(0.1 + 0.2) == q(0.3)
    assert str(q(-0.0)) == "0.0"


def test_free_fall_matches_semi_implicit_euler() -> None:
    w, s = make()
    b = w.spawn(body_components(0, 10))
    s.run(w, 60)
    vy = w.get(b, "velocity")["vy"]
    assert vy == pytest.approx(-9.81, abs=1e-6)
    assert w.get(b, "transform")["y"] == pytest.approx(10 - 9.81 * (61 / 120), abs=1e-4)


def test_static_and_gravity_scale() -> None:
    w, s = make()
    st = w.spawn(body_components(0, 0, static=True))
    floaty = w.spawn(body_components(5, 5, gravity_scale=0.0, vx=1.0))
    s.run(w, 30)
    assert w.get(st, "transform") == {"x": 0.0, "y": 0.0, "rot": 0.0}
    assert w.get(floaty, "transform")["y"] == 5.0
    assert w.get(floaty, "transform")["x"] == pytest.approx(5.5, abs=1e-6)


def test_speed_cap_and_damping() -> None:
    w, s = make(PhysicsConfig(gravity=(0, 0), max_speed=10))
    fast = w.spawn(body_components(0, 0, vx=1000))
    damped = w.spawn(body_components(50, 0, vx=10, damping=2.0))
    s.run(w, 1)
    assert w.get(fast, "velocity")["vx"] == pytest.approx(10)
    s.run(w, 120)
    assert w.get(damped, "velocity")["vx"] < 1.0


@pytest.mark.parametrize(
    "a, b, expect",
    [
        (({"x": 0, "y": 0}, {"shape": "circle", "r": 1}), ({"x": 1.5, "y": 0}, {"shape": "circle", "r": 1}), (1.0, 0.0, 0.5)),
        (({"x": 0, "y": 0}, {"shape": "aabb", "hw": 1, "hh": 1}), ({"x": 0, "y": 1.8}, {"shape": "aabb", "hw": 1, "hh": 1}), (0.0, 1.0, 0.2)),
        (({"x": 0, "y": 0}, {"shape": "aabb", "hw": 2, "hh": 0.5}), ({"x": 0, "y": 0.9}, {"shape": "circle", "r": 0.5}), (0.0, 1.0, 0.1)),
        (({"x": 0, "y": 0.9}, {"shape": "circle", "r": 0.5}), ({"x": 0, "y": 0}, {"shape": "aabb", "hw": 2, "hh": 0.5}), (0.0, -1.0, 0.1)),
    ],
)
def test_manifold_normals_point_a_to_b(a, b, expect) -> None:
    nx, ny, depth = manifold(a[0], a[1], b[0], b[1])
    assert (nx, ny) == pytest.approx(expect[:2])
    assert depth == pytest.approx(expect[2])


def test_manifold_separated_and_coincident() -> None:
    c = {"shape": "circle", "r": 1}
    assert manifold({"x": 0, "y": 0}, c, {"x": 3, "y": 0}, c) is None
    assert manifold({"x": 0, "y": 0}, c, {"x": 0, "y": 0}, c) == (1.0, 0.0, 2)
    box = {"shape": "aabb", "hw": 1, "hh": 1}
    nx, ny, depth = manifold({"x": 0, "y": 0}, box, {"x": 0.2, "y": 0}, {"shape": "circle", "r": 0.1})
    assert (nx, ny) == (1.0, 0.0) and depth == pytest.approx(0.9)


def test_broadphase_finds_only_nearby_pairs() -> None:
    c = {"shape": "circle", "r": 0.5}
    entries = [(0, {"x": 0, "y": 0}, c), (1, {"x": 0.8, "y": 0}, c), (2, {"x": 100, "y": 100}, c)]
    assert broadphase(entries, 4.0) == [(0, 1)]


def test_ball_comes_to_rest_on_ground_and_emits_contacts() -> None:
    w, s = make()
    w.spawn(body_components(0, -1, static=True, shape="aabb", hw=10, hh=0.5))
    ball = w.spawn(body_components(0, 3, r=0.5, restitution=0.0))
    reader = w.reader(CONTACT_CHANNEL, "test")
    s.run(w, 240)
    tf, vel = w.get(ball, "transform"), w.get(ball, "velocity")
    assert tf["y"] == pytest.approx(0.0, abs=0.05)
    assert abs(vel["vy"]) < 1e-6
    events = reader.payloads()
    assert events and all(e["ny"] == pytest.approx(-1.0) or e["ny"] == pytest.approx(1.0) for e in events)


def test_elastic_head_on_swaps_velocities() -> None:
    w, s = make(PhysicsConfig(gravity=(0, 0)))
    a = w.spawn(body_components(-1, 0, vx=2, restitution=1.0, friction=0))
    b = w.spawn(body_components(1, 0, vx=-2, restitution=1.0, friction=0))
    s.run(w, 40)
    assert w.get(a, "velocity")["vx"] == pytest.approx(-2, abs=1e-6)
    assert w.get(b, "velocity")["vx"] == pytest.approx(2, abs=1e-6)


def test_heavier_body_wins_momentum() -> None:
    w, s = make(PhysicsConfig(gravity=(0, 0)))
    heavy = w.spawn(body_components(-1, 0, vx=1, mass=10, restitution=0, friction=0))
    light = w.spawn(body_components(1, 0, vx=-1, mass=1, restitution=0, friction=0))
    s.run(w, 60)
    total = 10 * w.get(heavy, "velocity")["vx"] + 1 * w.get(light, "velocity")["vx"]
    assert total == pytest.approx(9.0, abs=1e-6)
    assert w.get(heavy, "velocity")["vx"] > 0


def test_sensors_report_but_do_not_resolve() -> None:
    w, s = make(PhysicsConfig(gravity=(0, 0)))
    zone = w.spawn(body_components(0, 0, static=True, sensor=True, shape="aabb", hw=2, hh=2))
    walker = w.spawn(body_components(-3, 0, vx=3))
    s.run(w, 60)
    assert w.get(walker, "velocity")["vx"] == pytest.approx(3)
    ev = contacts_for(w, "probe")
    assert any(e["sensor"] and {e["a"], e["b"]} == {zone, walker} for e in ev)


def test_layer_masks_filter_pairs() -> None:
    w, s = make(PhysicsConfig(gravity=(0, 0)))
    a = w.spawn(body_components(-1, 0, vx=2, layer=1, mask=1))
    w.spawn(body_components(1, 0, vx=-2, layer=2, mask=2))
    s.run(w, 60)
    assert w.get(a, "velocity")["vx"] == pytest.approx(2)


def test_deterministic_and_rollback_exact() -> None:
    def run(seed: int) -> str:
        w, s = make(seed=seed)
        w.spawn(body_components(0, -1, static=True, shape="aabb", hw=20, hh=0.5))
        for i in range(12):
            w.spawn(body_components(-5 + i, 2 + (i % 3), r=0.4, restitution=0.5, vx=(i % 4) - 1.5))
        s.run(w, 120)
        return w.state_digest

    assert run(1) == run(1)
    w, s = make()
    w.spawn(body_components(0, -1, static=True, shape="aabb", hw=20, hh=0.5))
    for i in range(6):
        w.spawn(body_components(i, 3, restitution=0.3))
    s.run(w, 20)
    snap = w.snapshot()
    s.run(w, 40)
    after = w.state_digest
    w.restore(snap)
    s.run(w, 40)
    assert w.state_digest == after


def test_config_and_bundle_validation() -> None:
    with pytest.raises(ValidationError):
        PhysicsConfig(cell_size=0)
    with pytest.raises(ValidationError):
        body_components(shape="triangle")
    with pytest.raises(ValidationError):
        body_components(mass=0)
    assert body_components(mass=0, static=True)["body"]["static"] is True
