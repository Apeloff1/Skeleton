"""Deterministic 2D physics as ECS systems.

A compact rigid-body layer for gameplay simulation on
:class:`~skeleton.simulation.ecs.live.LiveWorld` (the full 3D solver lives
in :mod:`skeleton.simulation.physics`; this is the light, scriptable tier
blueprints and sandboxed scripts drive directly).

Components (plain dicts so scripts and snapshots can see them):

``transform``  ``{"x", "y", "rot"}``
``velocity``   ``{"vx", "vy", "w"}``
``body``       ``{"mass", "restitution", "friction", "static", "gravity_scale", "damping"}``
``collider``   ``{"shape": "circle"|"aabb", "r" | "hw","hh", "layer", "mask", "sensor"}``

Systems (install with :func:`install_physics`):

``physics.integrate``  semi-implicit Euler with gravity, damping, speed cap
``physics.collide``    uniform-grid broadphase → exact narrowphase → impulse
                       resolution + positional correction; emits
                       ``physics.contact`` events ``{"a", "b", "nx", "ny",
                       "depth", "sensor"}``

Every float is quantised (:data:`QUANTUM`) after each step so results are
bit-identical across runs and platforms, which keeps world digests and
rollback/replay exact.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.schedule import SystemPhase
from skeleton.simulation.ecs.ticker import SystemContext, SystemDef, TickScheduler

QUANTUM = 1e-9
CONTACT_CHANNEL = "physics.contact"
PHYSICS_COMPONENTS = ("transform", "velocity", "body", "collider")
MAX_SPEED = 1e4
MAX_BODIES = 20_000


def q(value: float) -> float:
    """Quantise to the deterministic grid (and squash -0.0)."""
    out = round(float(value) / QUANTUM) * QUANTUM
    out = round(out, 9)
    return 0.0 if out == 0 else out


@dataclass(frozen=True)
class PhysicsConfig:
    gravity: tuple[float, float] = (0.0, -9.81)
    cell_size: float = 4.0
    max_speed: float = 200.0
    correction: float = 0.8  # positional correction percent
    slop: float = 0.01
    iterations: int = 2

    def __post_init__(self) -> None:
        if self.cell_size <= 0 or self.max_speed <= 0 or not 1 <= self.iterations <= 16:
            raise ValidationError("invalid physics config")


def register_physics(world: LiveWorld) -> None:
    for name in PHYSICS_COMPONENTS:
        world.register_component(name)
    world.register_event(CONTACT_CHANNEL)


def body_components(
    x: float = 0.0, y: float = 0.0, *, vx: float = 0.0, vy: float = 0.0, mass: float = 1.0,
    restitution: float = 0.2, friction: float = 0.1, static: bool = False, gravity_scale: float = 1.0,
    damping: float = 0.0, shape: str = "circle", r: float = 0.5, hw: float = 0.5, hh: float = 0.5,
    layer: int = 1, mask: int = 0xFFFF, sensor: bool = False,
) -> dict[str, Any]:
    """Convenience component bundle for ``world.spawn(...)``."""
    if shape not in {"circle", "aabb"}:
        raise ValidationError("shape must be circle or aabb")
    if not static and mass <= 0:
        raise ValidationError("dynamic bodies need positive mass")
    collider: dict[str, Any] = {"shape": shape, "layer": int(layer), "mask": int(mask), "sensor": bool(sensor)}
    if shape == "circle":
        collider["r"] = q(r)
    else:
        collider["hw"], collider["hh"] = q(hw), q(hh)
    return {
        "transform": {"x": q(x), "y": q(y), "rot": 0.0},
        "velocity": {"vx": q(vx), "vy": q(vy), "w": 0.0},
        "body": {"mass": float(mass), "restitution": float(restitution), "friction": float(friction), "static": bool(static),
                 "gravity_scale": float(gravity_scale), "damping": float(damping)},
        "collider": collider,
    }


# ---------------------------------------------------------------------------
# integration
# ---------------------------------------------------------------------------
def integrate(ctx: SystemContext, config: PhysicsConfig) -> int:
    gx, gy = config.gravity
    dt = ctx.dt
    moved = 0
    for e, tf, vel, body in ctx.query("transform", "velocity", "body"):
        if body.get("static"):
            continue
        gs = float(body.get("gravity_scale", 1.0))
        vx = float(vel["vx"]) + gx * gs * dt
        vy = float(vel["vy"]) + gy * gs * dt
        damp = max(0.0, 1.0 - float(body.get("damping", 0.0)) * dt)
        vx, vy = vx * damp, vy * damp
        speed = math.hypot(vx, vy)
        if speed > config.max_speed:
            k = config.max_speed / speed
            vx, vy = vx * k, vy * k
        nvel = {"vx": q(vx), "vy": q(vy), "w": q(vel.get("w", 0.0))}
        ntf = {"x": q(tf["x"] + nvel["vx"] * dt), "y": q(tf["y"] + nvel["vy"] * dt), "rot": q(tf.get("rot", 0.0) + nvel["w"] * dt)}
        ctx.set(e, "velocity", nvel)
        ctx.set(e, "transform", ntf)
        moved += 1
    return moved


# ---------------------------------------------------------------------------
# collision
# ---------------------------------------------------------------------------
def _extent(col: dict[str, Any]) -> tuple[float, float]:
    if col["shape"] == "circle":
        return col["r"], col["r"]
    return col["hw"], col["hh"]


def manifold(ta: dict, ca: dict, tb: dict, cb: dict) -> tuple[float, float, float] | None:
    """Contact normal (a→b) and depth, or ``None`` when separated."""
    dx, dy = tb["x"] - ta["x"], tb["y"] - ta["y"]
    sa, sb = ca["shape"], cb["shape"]
    if sa == "circle" and sb == "circle":
        rs = ca["r"] + cb["r"]
        d2 = dx * dx + dy * dy
        if d2 >= rs * rs:
            return None
        d = math.sqrt(d2)
        if d == 0:
            return (1.0, 0.0, rs)
        return (dx / d, dy / d, rs - d)
    if sa == "aabb" and sb == "aabb":
        ox = ca["hw"] + cb["hw"] - abs(dx)
        oy = ca["hh"] + cb["hh"] - abs(dy)
        if ox <= 0 or oy <= 0:
            return None
        if ox < oy:
            return ((1.0 if dx >= 0 else -1.0), 0.0, ox)
        return (0.0, (1.0 if dy >= 0 else -1.0), oy)
    # circle vs aabb (normalise so the box is "box")
    flip = sa == "circle"
    box_t, box_c, cir_t, cir_c = (tb, cb, ta, ca) if flip else (ta, ca, tb, cb)
    cx, cy = cir_t["x"] - box_t["x"], cir_t["y"] - box_t["y"]
    px = max(-box_c["hw"], min(box_c["hw"], cx))
    py = max(-box_c["hh"], min(box_c["hh"], cy))
    inside = px == cx and py == cy
    if inside:  # centre inside the box: push out along the shallowest axis
        ox, oy = box_c["hw"] - abs(cx), box_c["hh"] - abs(cy)
        if ox < oy:
            nx, ny, depth = (1.0 if cx >= 0 else -1.0), 0.0, ox + cir_c["r"]
        else:
            nx, ny, depth = 0.0, (1.0 if cy >= 0 else -1.0), oy + cir_c["r"]
    else:
        ddx, ddy = cx - px, cy - py
        d2 = ddx * ddx + ddy * ddy
        if d2 >= cir_c["r"] ** 2:
            return None
        d = math.sqrt(d2)
        nx, ny, depth = ddx / d, ddy / d, cir_c["r"] - d
    # (nx, ny) points box→circle; we need a→b.
    return (-nx, -ny, depth) if flip else (nx, ny, depth)


def broadphase(entries: list[tuple[int, dict, dict]], cell: float) -> list[tuple[int, int]]:
    grid: dict[tuple[int, int], list[int]] = {}
    for idx, (_, tf, col) in enumerate(entries):
        ex, ey = _extent(col)
        x0, x1 = math.floor((tf["x"] - ex) / cell), math.floor((tf["x"] + ex) / cell)
        y0, y1 = math.floor((tf["y"] - ey) / cell), math.floor((tf["y"] + ey) / cell)
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                grid.setdefault((gx, gy), []).append(idx)
    pairs: set[tuple[int, int]] = set()
    for members in grid.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                pairs.add((a, b) if a < b else (b, a))
    return sorted(pairs)


def collide(ctx: SystemContext, config: PhysicsConfig) -> int:
    rows = sorted(ctx.query("transform", "collider", "body", "velocity"), key=lambda r: r[0])
    if len(rows) > MAX_BODIES:
        raise ValidationError("too many physics bodies", context={"maximum": MAX_BODIES})
    tfs = {e: dict(tf) for e, tf, _, _, _ in rows}
    vels = {e: dict(v) for e, _, _, _, v in rows}
    cols = {e: c for e, _, c, _, _ in rows}
    bodies = {e: b for e, _, _, b, _ in rows}
    order = [e for e, *_ in rows]
    contacts: dict[tuple[int, int], tuple[float, float, float, bool]] = {}
    for _ in range(config.iterations):
        entries = [(e, tfs[e], cols[e]) for e in order]
        for ia, ib in broadphase(entries, config.cell_size):
            a, b = order[ia], order[ib]
            ca, cb = cols[a], cols[b]
            if not (ca["mask"] & cb["layer"]) or not (cb["mask"] & ca["layer"]):
                continue
            ba, bb = bodies[a], bodies[b]
            if ba.get("static") and bb.get("static"):
                continue
            m = manifold(tfs[a], ca, tfs[b], cb)
            if m is None:
                continue
            nx, ny, depth = m
            sensor = bool(ca.get("sensor") or cb.get("sensor"))
            contacts.setdefault((a, b), (nx, ny, depth, sensor))
            if sensor:
                continue
            inv_a = 0.0 if ba.get("static") else 1.0 / float(ba["mass"])
            inv_b = 0.0 if bb.get("static") else 1.0 / float(bb["mass"])
            inv = inv_a + inv_b
            if inv == 0:
                continue
            rvx = vels[b]["vx"] - vels[a]["vx"]
            rvy = vels[b]["vy"] - vels[a]["vy"]
            vn = rvx * nx + rvy * ny
            if vn < 0:
                e_rest = min(float(ba.get("restitution", 0.0)), float(bb.get("restitution", 0.0)))
                j = -(1 + e_rest) * vn / inv
                # Coulomb friction along the tangent.
                tx, ty = -ny, nx
                vt = rvx * tx + rvy * ty
                mu = math.sqrt(float(ba.get("friction", 0.0)) * float(bb.get("friction", 0.0)))
                jt = max(-mu * j, min(mu * j, -vt / inv))
                ix, iy = j * nx + jt * tx, j * ny + jt * ty
                vels[a]["vx"] -= ix * inv_a
                vels[a]["vy"] -= iy * inv_a
                vels[b]["vx"] += ix * inv_b
                vels[b]["vy"] += iy * inv_b
            corr = max(depth - config.slop, 0.0) / inv * config.correction
            tfs[a]["x"] -= corr * nx * inv_a
            tfs[a]["y"] -= corr * ny * inv_a
            tfs[b]["x"] += corr * nx * inv_b
            tfs[b]["y"] += corr * ny * inv_b
    for e in order:
        if bodies[e].get("static"):
            continue
        ctx.set(e, "transform", {"x": q(tfs[e]["x"]), "y": q(tfs[e]["y"]), "rot": q(tfs[e].get("rot", 0.0))})
        ctx.set(e, "velocity", {"vx": q(vels[e]["vx"]), "vy": q(vels[e]["vy"]), "w": q(vels[e].get("w", 0.0))})
    for (a, b), (nx, ny, depth, sensor) in sorted(contacts.items()):
        ctx.send(CONTACT_CHANNEL, {"a": a, "b": b, "nx": q(nx), "ny": q(ny), "depth": q(depth), "sensor": sensor})
    return len(contacts)


def install_physics(scheduler: TickScheduler, world: LiveWorld, config: PhysicsConfig | None = None, *, before: Iterable[str] = ()) -> tuple[str, str]:
    """Register components and add ``physics.integrate`` → ``physics.collide``."""
    cfg = config or PhysicsConfig()
    register_physics(world)
    rw = ("transform", "velocity")
    scheduler.add(SystemDef("physics.integrate", lambda ctx: integrate(ctx, cfg), phase=SystemPhase.UPDATE,
                            reads=("body",), writes=rw, before=tuple(before)))
    scheduler.add(SystemDef("physics.collide", lambda ctx: collide(ctx, cfg), phase=SystemPhase.UPDATE,
                            reads=("body", "collider"), writes=rw + ("event:" + CONTACT_CHANNEL,), after=("physics.integrate",),
                            before=tuple(before)))
    return ("physics.integrate", "physics.collide")


def contacts_for(world: LiveWorld, reader_id: str) -> list[dict[str, Any]]:
    return list(world.reader(CONTACT_CHANNEL, reader_id).payloads())


__all__ = [
    "CONTACT_CHANNEL",
    "PHYSICS_COMPONENTS",
    "PhysicsConfig",
    "body_components",
    "broadphase",
    "collide",
    "contacts_for",
    "install_physics",
    "integrate",
    "manifold",
    "q",
    "register_physics",
]
