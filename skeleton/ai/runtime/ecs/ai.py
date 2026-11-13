"""Deterministic game AI as ECS systems: steering, FSM brains, utility choice.

Components:

``agent``   ``{"max_speed", "max_force", "behavior", "target": entity|None,
              "goal": [x, y]|None, "radius", "wander": angle, "response"}``
``brain``   ``{"state", "since", "transitions": [{"from", "to", "when"}],
              "memory": {...}}``  — finite-state machine with declarative
              conditions (``when`` is a condition record, never code)
``needs``   ``{"name": value 0..1, ...}``  plus ``utility`` ``{"options":
              [{"action", "need", "weight", "curve"}], "choice"}``

Systems (install with :func:`install_ai`):

``ai.sense``     nearest-entity perception into ``brain.memory``
``ai.think``     FSM transitions + utility selection → ``agent.behavior``
``ai.steer``     steering force → ``velocity`` (seek/flee/arrive/pursue/
                 evade/wander/idle), clamped by ``max_force``/``max_speed``

Conditions are pure data evaluated by :func:`check_condition` — e.g.
``{"op": "lt", "key": "dist", "value": 3}`` or ``{"all": [...]}`` — so
blueprints and LLM-authored content can define AI without executable code.
Randomness comes only from the system RNG fork, keeping runs replayable.
"""
from __future__ import annotations

import math
from itertools import islice
from collections.abc import Iterable, Mapping
from typing import Any

from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import SystemContext, SystemDef, TickScheduler

from .physics import q

BEHAVIORS = ("idle", "seek", "flee", "arrive", "pursue", "evade", "wander")
AI_COMPONENTS = ("agent", "brain", "needs", "utility")
MAX_CONDITION_DEPTH = 8
MAX_CONDITION_NODES = 256
MAX_AI_TRANSITIONS = 128
MAX_AI_OPTIONS = 128
MAX_ENTITY_SENSE = 100000
MAX_SENSE_CANDIDATES_PER_TICK = 1_000_000
RESPONSE_S = 0.25  # seconds to close a steering velocity error
_OPS = {
    "lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b, "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
}


def register_ai(world: LiveWorld) -> None:
    for name in AI_COMPONENTS + ("transform", "velocity"):
        world.register_component(name)


def agent_component(*, max_speed: float = 4.0, max_force: float = 16.0, behavior: str = "idle", target: int | None = None,
                    goal: Iterable[float] | None = None, radius: float = 1.0, response: float = RESPONSE_S) -> dict[str, Any]:
    if behavior not in BEHAVIORS:
        raise ValidationError("unknown behavior", context={"behavior": behavior})
    for name, value in (("max_speed",max_speed),("max_force",max_force),("response",response),
                        ("radius",radius)):
        if (type(value) not in (float, int) or not 0 < value <= 100000
                or not math.isfinite(value)):
            raise ValidationError(f"{name} must be finite and bounded positive")
    if target is not None and (type(target) is not int or target < 0):
        raise ValidationError("target must be an entity identifier or None")
    g = list(islice(goal, 3)) if goal is not None else None
    if g is not None and (len(g) != 2 or any(type(x) not in (int, float)
                                               or abs(x) > 1e6 or not math.isfinite(x) for x in g)):
        raise ValidationError("goal must contain two bounded finite coordinates")
    return {"max_speed": float(max_speed), "max_force": float(max_force), "behavior": behavior, "target": target,
            "goal": [q(g[0]), q(g[1])] if g else None, "radius": float(radius), "wander": 0.0, "response": float(response)}


def brain_component(initial: str, transitions: Iterable[Mapping[str, Any]], *, behaviors: Mapping[str, str] | None = None) -> dict[str, Any]:
    if type(initial) is not str or not 1 <= len(initial) <= 128:
        raise ValidationError("invalid bounded initial brain state")
    trans = []
    for index, t in enumerate(transitions):
        if index >= MAX_AI_TRANSITIONS:
            raise ValidationError("brain transition inventory exceeds budget")
        if (not isinstance(t, Mapping) or type(t.get("to")) is not str
                or not 1 <= len(t["to"]) <= 128 or
                type(t.get("from", "*")) is not str or
                not 1 <= len(t.get("from", "*")) <= 128):
            raise ValidationError("transitions need bounded state identities")
        validate_condition(t.get("when", {"always": True}))
        trans.append({"from": t.get("from", "*"), "to": t["to"], "when": dict(t.get("when", {"always": True}))})
    beh = dict(behaviors or {})
    if len(beh) > MAX_AI_TRANSITIONS:
        raise ValidationError("brain behavior mapping exceeds budget")
    for b in beh.values():
        if b not in BEHAVIORS:
            raise ValidationError("unknown behavior in brain map", context={"behavior": b})
    return {"state": initial, "since": 0, "transitions": trans, "behaviors": beh, "memory": {}}


# ---------------------------------------------------------------------------
# conditions (data, never code)
# ---------------------------------------------------------------------------
def validate_condition(cond: Any, depth: int = 0) -> None:
    """Exactly typed, acyclic finite AST; no accessors, code or extra operators."""
    seen: set[int] = set()
    budget = [0]

    def walk(node: Any, level: int) -> None:
        budget[0] += 1
        if budget[0] > MAX_CONDITION_NODES or level > MAX_CONDITION_DEPTH:
            raise ValidationError("condition computation budget exceeded")
        if type(node) is not dict or id(node) in seen:
            raise ValidationError("condition must be a nonrecursive plain mapping")
        seen.add(id(node))
        try:
            if set(node) == {"always"}:
                if type(node["always"]) is not bool:
                    raise ValidationError("always condition must be boolean")
                return
            for op in ("all", "any"):
                if set(node) == {op}:
                    sub = node[op]
                    if type(sub) is not list or not 1 <= len(sub) <= 32:
                        raise ValidationError("logical condition list must have 1..32 entries")
                    for child in sub:
                        walk(child, level + 1)
                    return
            if set(node) == {"not"}:
                walk(node["not"], level + 1)
                return
            if (set(node) != {"op", "key", "value"} or node["op"] not in _OPS
                    or type(node["key"]) is not str or not 1 <= len(node["key"]) <= 128
                    or type(node["value"]) not in (float, int, str, bool)):
                raise ValidationError("invalid finite comparison condition")
            value = node["value"]
            if (type(value) is float and not math.isfinite(value)
                    or type(value) is int and value.bit_length() > 128
                    or type(value) is str and len(value) > 512):
                raise ValidationError("unbounded comparison value")
        finally:
            seen.remove(id(node))

    walk(cond, depth)


def check_condition(cond: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    validate_condition(cond)
    def visit(node: Mapping[str, Any]) -> bool:
        if "always" in node:
            return node["always"] is True
        if "all" in node:
            return all(visit(c) for c in node["all"])
        if "any" in node:
            return any(visit(c) for c in node["any"])
        if "not" in node:
            return not visit(node["not"])
        value = facts.get(node["key"])
        if value is None or type(value) not in (int, float, bool, str):
            return False
        if type(value) is float and not math.isfinite(value):
            return False
        try:
            return bool(_OPS[node["op"]](value, node["value"]))
        except (TypeError, ValueError, ArithmeticError):
            return False
    return visit(cond)


# ---------------------------------------------------------------------------
# utility curves
# ---------------------------------------------------------------------------
def curve(kind: str, x: float) -> float:
    # A malformed utility sample must not silently become a valid action
    # score through clamping (especially adversarial negative inputs).
    # Bound native integers before converting them to C doubles for
    # math.isfinite: very large Python ints otherwise raise OverflowError.
    if type(x) not in (int, float) or not 0 <= x <= 1 or not math.isfinite(x):
        raise ValidationError("utility input must be finite and within [0, 1]")
    x = float(x)
    if kind == "linear":
        return x
    if kind == "inverse":
        return 1.0 - x
    if kind == "quadratic":
        return x * x
    if kind == "sqrt":
        return math.sqrt(x)
    if kind == "logistic":
        return 1.0 / (1.0 + math.exp(-12.0 * (x - 0.5)))
    if kind == "step":
        return 1.0 if x >= 0.5 else 0.0
    raise ValidationError("unknown utility curve", context={"curve": kind})


def choose_utility(options: list[Mapping[str, Any]], needs: Mapping[str, float]) -> tuple[str | None, float]:
    if type(options) is not list or len(options) > MAX_AI_OPTIONS or not isinstance(needs, Mapping):
        raise ValidationError("invalid bounded utility inventory")
    best, score = None, -1.0
    for opt in options:
        if not isinstance(opt, Mapping) or type(opt.get("action")) is not str:
            raise ValidationError("utility option requires an action identity")
        weight = opt.get("weight", 1.0)
        if type(weight) not in (float, int) or not 0 <= weight <= 100 or not math.isfinite(weight):
            raise ValidationError("utility weight must be finite and between 0 and 100")
        s = float(weight) * curve(str(opt.get("curve", "linear")), needs.get(opt.get("need", ""), 0.0))
        if s > score + 1e-12:  # ties keep declaration order
            best, score = opt.get("action"), s
    return best, q(score) if best is not None else 0.0


# ---------------------------------------------------------------------------
# steering
# ---------------------------------------------------------------------------
def _clamp(vx: float, vy: float, limit: float) -> tuple[float, float]:
    m = math.hypot(vx, vy)
    if m > limit and m > 0:
        return vx * limit / m, vy * limit / m
    return vx, vy


def _finite_bounded(value: object, limit: float) -> bool:
    """Reject hostile numeric values before float coercion or arithmetic."""
    return (type(value) in (int, float) and -limit <= value <= limit
            and math.isfinite(value))


def steering(behavior: str, pos: tuple[float, float], vel: tuple[float, float], agent: Mapping[str, Any],
             target_pos: tuple[float, float] | None, target_vel: tuple[float, float] = (0.0, 0.0), wander_angle: float = 0.0) -> tuple[float, float]:
    """Desired steering force for one agent (pure function)."""
    if not isinstance(agent, Mapping) or behavior not in BEHAVIORS:
        raise ValidationError("invalid steering behavior or speed")
    raw_speed = agent.get("max_speed")
    if not _finite_bounded(raw_speed, 100000) or raw_speed <= 0:
        raise ValidationError("invalid steering behavior or speed")
    ms = float(raw_speed)
    vectors = (pos, vel, target_vel)
    if (any(type(vector) not in (tuple, list) or len(vector) != 2 for vector in vectors)
            or any(not _finite_bounded(v, 1_000_000_000)
                   for vector in vectors for v in vector)
            or not _finite_bounded(wander_angle, 1_000_000_000)):
        raise ValidationError("nonfinite steering inputs")
    if (target_pos is not None and
            (type(target_pos) not in (tuple, list) or len(target_pos) != 2
             or any(not _finite_bounded(v, 1_000_000_000) for v in target_pos))):
        raise ValidationError("nonfinite target coordinates")
    if behavior == "idle":
        return (-vel[0], -vel[1])
    if behavior == "wander":
        hx, hy = (vel[0], vel[1]) if math.hypot(*vel) > 1e-9 else (1.0, 0.0)
        hm = math.hypot(hx, hy)
        cx, cy = hx / hm * 2.0, hy / hm * 2.0
        dx, dy = cx + math.cos(wander_angle), cy + math.sin(wander_angle)
        dx, dy = _clamp(dx * ms, dy * ms, ms)
        return (dx - vel[0], dy - vel[1])
    if target_pos is None:
        return (-vel[0], -vel[1])
    tx, ty = target_pos
    if behavior in ("pursue", "evade"):
        dist = math.hypot(tx - pos[0], ty - pos[1])
        lead = min(dist / ms, 2.0) if ms > 0 else 0.0
        tx, ty = tx + target_vel[0] * lead, ty + target_vel[1] * lead
    dx, dy = tx - pos[0], ty - pos[1]
    dist = math.hypot(dx, dy)
    if behavior in ("flee", "evade"):
        dx, dy = -dx, -dy
    if dist < 1e-9:
        return (-vel[0], -vel[1])
    speed = ms
    if behavior == "arrive":
        radius = agent.get("radius", 1.0)
        if not _finite_bounded(radius, 100000) or radius <= 0:
            raise ValidationError("invalid finite steering radius")
        slow = float(radius) * 4.0
        speed = ms * min(1.0, dist / slow)
    desired = (dx / dist * speed, dy / dist * speed)
    return (desired[0] - vel[0], desired[1] - vel[1])


# ---------------------------------------------------------------------------
# systems
# ---------------------------------------------------------------------------
def sense(ctx: SystemContext, view_radius: float) -> None:
    if (type(view_radius) not in (int, float)
            or not 0 < view_radius <= 100000 or not math.isfinite(view_radius)):
        raise ValidationError("invalid finite perception radius")
    positions = {e: (tf["x"], tf["y"]) for e, tf in ctx.query("transform")}
    if len(positions) > MAX_ENTITY_SENSE:
        raise ValidationError("perception occupancy budget exceeded")
    # O(N) spatial bucketing plus bounded local neighborhoods, not O(N^2)
    # all-to-all scans. Counts remain deterministic and distance-exact.
    grid: dict[tuple[int,int], list[tuple[int, float, float]]] = {}
    for item, (xx, yy) in positions.items():
        if (type(xx) not in (int, float) or type(yy) not in (int, float)
                or abs(xx) > 1_000_000_000 or abs(yy) > 1_000_000_000
                or not math.isfinite(xx) or not math.isfinite(yy)):
            raise ValidationError("invalid finite perception coordinates")
        cell = (math.floor(xx / view_radius), math.floor(yy / view_radius))
        grid.setdefault(cell, []).append((item, xx, yy))
    agents = list(ctx.query("agent", "brain"))
    if len(agents) > MAX_ENTITY_SENSE:
        raise ValidationError("perception agent budget exceeded")
    # Preflight the exact number of candidate comparisons across every
    # active brain before any ctx.set call. Dense buckets cannot cause
    # quadratic unbounded work or partially published perception updates.
    candidates = 0
    for entity, _agent, _brain in agents:
        if entity not in positions:
            continue
        px, py = positions[entity]
        cx, cy = math.floor(px / view_radius), math.floor(py / view_radius)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                candidates += len(grid.get((gx, gy), ()))
                if candidates > MAX_SENSE_CANDIDATES_PER_TICK:
                    raise ValidationError("perception pair budget exceeded before state mutation")
    for e, agent, brain in agents:
        if e not in positions:
            continue
        px, py = positions[e]
        mem = dict(brain.get("memory", {}))
        tgt = agent.get("target")
        if tgt is not None and tgt in positions:
            tx, ty = positions[tgt]
            mem["dist"] = q(math.hypot(tx - px, ty - py))
            mem["target_alive"] = True
        else:
            mem["dist"] = None
            mem["target_alive"] = tgt is None
        near = 0
        cx, cy = math.floor(px / view_radius), math.floor(py / view_radius)
        for gx in (cx-1, cx, cx+1):
            for gy in (cy-1, cy, cy+1):
                for other, ox, oy in grid.get((gx, gy), ()):
                    if other != e and math.hypot(ox-px, oy-py) <= view_radius:
                        near += 1
        mem["neighbors"] = near
        nb = dict(brain)
        nb["memory"] = mem
        ctx.set(e, "brain", nb)


def think(ctx: SystemContext) -> None:
    needs_by = {e: n for e, n in ctx.query("needs")}
    util_by = {e: u for e, u in ctx.query("utility")}
    for e, brain, agent in ctx.query("brain", "agent"):
        b = dict(brain)
        facts = dict(b.get("memory", {}))
        facts["state"] = b["state"]
        facts["since"] = ctx.tick - int(b.get("since", 0))
        for need, value in (needs_by.get(e) or {}).items():
            facts["need." + need] = value
        for t in b.get("transitions", []):
            if t["from"] in ("*", b["state"]) and t["to"] != b["state"] and check_condition(t["when"], facts):
                b["state"], b["since"] = t["to"], ctx.tick
                break
        a = dict(agent)
        mapped = b.get("behaviors", {}).get(b["state"])
        if mapped:
            a["behavior"] = mapped
        util = util_by.get(e)
        if util is not None and needs_by.get(e) is not None:
            choice, score = choose_utility(list(util.get("options", [])), needs_by[e])
            nu = dict(util)
            nu["choice"], nu["score"] = choice, score
            ctx.set(e, "utility", nu)
            if choice in BEHAVIORS and not mapped:
                a["behavior"] = choice
        ctx.set(e, "brain", b)
        ctx.set(e, "agent", a)


def steer(ctx: SystemContext) -> None:
    tfs = {e: tf for e, tf in ctx.query("transform")}
    vels = {e: v for e, v in ctx.query("velocity")}
    for e, agent in ctx.query("agent"):
        if e not in tfs or e not in vels:
            continue
        pos = (tfs[e]["x"], tfs[e]["y"])
        vel = (vels[e]["vx"], vels[e]["vy"])
        a = dict(agent)
        tpos: tuple[float, float] | None = None
        tvel = (0.0, 0.0)
        tgt = a.get("target")
        if tgt is not None and tgt in tfs:
            tpos = (tfs[tgt]["x"], tfs[tgt]["y"])
            if tgt in vels:
                tvel = (vels[tgt]["vx"], vels[tgt]["vy"])
        elif a.get("goal"):
            tpos = (a["goal"][0], a["goal"][1])
        if a["behavior"] == "wander":
            a["wander"] = q(float(a.get("wander", 0.0)) + (ctx.rng.random() - 0.5) * 0.6)
            ctx.set(e, "agent", a)
        fx, fy = steering(a["behavior"], pos, vel, a, tpos, tvel, float(a.get("wander", 0.0)))
        # Steering is a velocity error; close it over the agent's response time.
        response = max(float(a.get("response", RESPONSE_S)), 1e-3)
        fx, fy = _clamp(fx / response, fy / response, float(a["max_force"]))
        nvx, nvy = _clamp(vel[0] + fx * ctx.dt, vel[1] + fy * ctx.dt, float(a["max_speed"]))
        nv = dict(vels[e])
        nv["vx"], nv["vy"] = q(nvx), q(nvy)
        ctx.set(e, "velocity", nv)


def install_ai(scheduler: TickScheduler, world: LiveWorld, *, view_radius: float = 8.0, before: Iterable[str] = ()) -> tuple[str, str, str]:
    """Add ``ai.sense`` → ``ai.think`` → ``ai.steer`` (put them before physics)."""
    if type(view_radius) not in (int, float) or not 0 < view_radius <= 100000 or not math.isfinite(view_radius):
        raise ValidationError("invalid bounded perception radius")
    register_ai(world)
    b = tuple(islice(before, 65))
    if len(b) > 64 or any(type(n) is not str or not n for n in b):
        raise ValidationError("invalid bounded scheduling dependencies")
    scheduler.add(SystemDef("ai.sense", lambda ctx: sense(ctx, view_radius), reads=("transform", "agent"), writes=("brain",), before=b))
    scheduler.add(SystemDef("ai.think", think, reads=("needs",), writes=("brain", "agent", "utility"), after=("ai.sense",), before=b))
    scheduler.add(SystemDef("ai.steer", steer, reads=("transform",), writes=("velocity", "agent"), after=("ai.think",), before=b))
    return ("ai.sense", "ai.think", "ai.steer")


__all__ = [
    "AI_COMPONENTS",
    "BEHAVIORS",
    "agent_component",
    "brain_component",
    "check_condition",
    "choose_utility",
    "curve",
    "install_ai",
    "register_ai",
    "sense",
    "steer",
    "steering",
    "think",
    "validate_condition",
]
