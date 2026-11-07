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
from collections.abc import Iterable, Mapping
from typing import Any

from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import SystemContext, SystemDef, TickScheduler

from .physics import q

BEHAVIORS = ("idle", "seek", "flee", "arrive", "pursue", "evade", "wander")
AI_COMPONENTS = ("agent", "brain", "needs", "utility")
MAX_CONDITION_DEPTH = 8
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
    if max_speed <= 0 or max_force <= 0 or response <= 0:
        raise ValidationError("max_speed, max_force and response must be positive")
    g = list(goal) if goal is not None else None
    if g is not None and len(g) != 2:
        raise ValidationError("goal must be [x, y]")
    return {"max_speed": float(max_speed), "max_force": float(max_force), "behavior": behavior, "target": target,
            "goal": [q(g[0]), q(g[1])] if g else None, "radius": float(radius), "wander": 0.0, "response": float(response)}


def brain_component(initial: str, transitions: Iterable[Mapping[str, Any]], *, behaviors: Mapping[str, str] | None = None) -> dict[str, Any]:
    trans = []
    for t in transitions:
        if not isinstance(t, Mapping) or not isinstance(t.get("to"), str):
            raise ValidationError("transitions need a 'to' state")
        validate_condition(t.get("when", {"always": True}))
        trans.append({"from": t.get("from", "*"), "to": t["to"], "when": dict(t.get("when", {"always": True}))})
    beh = dict(behaviors or {})
    for b in beh.values():
        if b not in BEHAVIORS:
            raise ValidationError("unknown behavior in brain map", context={"behavior": b})
    return {"state": initial, "since": 0, "transitions": trans, "behaviors": beh, "memory": {}}


# ---------------------------------------------------------------------------
# conditions (data, never code)
# ---------------------------------------------------------------------------
def validate_condition(cond: Any, depth: int = 0) -> None:
    if depth > MAX_CONDITION_DEPTH:
        raise ValidationError("condition nested too deeply")
    if not isinstance(cond, Mapping):
        raise ValidationError("condition must be a mapping")
    if "always" in cond:
        return
    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list):
                raise ValidationError(f"'{key}' must be a list")
            for c in cond[key]:
                validate_condition(c, depth + 1)
            return
    if "not" in cond:
        validate_condition(cond["not"], depth + 1)
        return
    if cond.get("op") not in _OPS or not isinstance(cond.get("key"), str):
        raise ValidationError("condition needs op in lt/le/gt/ge/eq/ne and a key", context={"condition": dict(cond)})


def check_condition(cond: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    if "always" in cond:
        return bool(cond["always"])
    if "all" in cond:
        return all(check_condition(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(check_condition(c, facts) for c in cond["any"])
    if "not" in cond:
        return not check_condition(cond["not"], facts)
    value = facts.get(cond["key"])
    if value is None:
        return False
    try:
        return bool(_OPS[cond["op"]](value, cond.get("value")))
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# utility curves
# ---------------------------------------------------------------------------
def curve(kind: str, x: float) -> float:
    x = max(0.0, min(1.0, float(x)))
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
    best, score = None, -1.0
    for opt in options:
        s = float(opt.get("weight", 1.0)) * curve(str(opt.get("curve", "linear")), float(needs.get(opt.get("need", ""), 0.0)))
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


def steering(behavior: str, pos: tuple[float, float], vel: tuple[float, float], agent: Mapping[str, Any],
             target_pos: tuple[float, float] | None, target_vel: tuple[float, float] = (0.0, 0.0), wander_angle: float = 0.0) -> tuple[float, float]:
    """Desired steering force for one agent (pure function)."""
    ms = float(agent["max_speed"])
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
        slow = float(agent.get("radius", 1.0)) * 4.0
        speed = ms * min(1.0, dist / slow)
    desired = (dx / dist * speed, dy / dist * speed)
    return (desired[0] - vel[0], desired[1] - vel[1])


# ---------------------------------------------------------------------------
# systems
# ---------------------------------------------------------------------------
def sense(ctx: SystemContext, view_radius: float) -> None:
    positions = {e: (tf["x"], tf["y"]) for e, tf in ctx.query("transform")}
    for e, agent, brain in ctx.query("agent", "brain"):
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
        for other, (ox, oy) in positions.items():
            if other != e and math.hypot(ox - px, oy - py) <= view_radius:
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
    register_ai(world)
    b = tuple(before)
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
