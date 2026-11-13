"""B034 — World-grounded NPC cognition.

Success criterion (game_creation_batches.json): "NPC decisions use
authoritative perception/state with bounded memory and deterministic
fallback."

* :func:`perceive` derives an NPC's percepts **only** from the authoritative
  :class:`WorldState` (range-limited, occlusion-aware). A planner never sees the
  raw world, so it cannot act on facts the NPC could not perceive.
* :class:`NpcMind` keeps a bounded, deterministic memory of percepts.
* :func:`decide` asks an optional planner (e.g. an LLM adapter) for an action and
  validates it against the percepts and the action vocabulary. On any failure —
  exception, budget overrun, unknown action, target not perceived/remembered —
  it falls back to a deterministic utility policy and records why.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

ACTIONS = ("idle", "flee", "attack", "approach", "talk", "eat", "rest", "wander")
MAX_MEMORY = 32


class CognitionError(ValueError):
    pass


@dataclass(frozen=True)
class Entity:
    entity_id: str
    kind: str  # "npc" | "player" | "food" | "wall" | ...
    x: int
    y: int
    hostile: bool = False


@dataclass(frozen=True)
class WorldState:
    tick: int
    entities: tuple[Entity, ...]

    def by_id(self) -> dict[str, Entity]:
        return {e.entity_id: e for e in self.entities}


@dataclass(frozen=True)
class Percept:
    entity_id: str
    kind: str
    x: int
    y: int
    hostile: bool
    distance: float
    tick: int


def _blocked(world: WorldState, a: Entity, b: Entity) -> bool:
    walls = {(e.x, e.y) for e in world.entities if e.kind == "wall"}
    if not walls:
        return False
    steps = max(abs(b.x - a.x), abs(b.y - a.y))
    for i in range(1, steps):
        px = a.x + round((b.x - a.x) * i / steps)
        py = a.y + round((b.y - a.y) * i / steps)
        if (px, py) in walls:
            return True
    return False


def perceive(world: WorldState, npc_id: str, *, radius: float = 8.0) -> tuple[Percept, ...]:
    ents = world.by_id()
    if npc_id not in ents:
        raise CognitionError(f"unknown npc {npc_id!r}")
    me = ents[npc_id]
    out = []
    for e in world.entities:
        if e.entity_id == npc_id or e.kind == "wall":
            continue
        d = math.hypot(e.x - me.x, e.y - me.y)
        if d <= radius and not _blocked(world, me, e):
            out.append(Percept(e.entity_id, e.kind, e.x, e.y, e.hostile, round(d, 6), world.tick))
    return tuple(sorted(out, key=lambda p: (p.distance, p.entity_id)))


@dataclass
class NpcMind:
    npc_id: str
    hunger: float = 0.0  # 0..1
    fatigue: float = 0.0  # 0..1
    health: float = 1.0  # 0..1
    max_memory: int = MAX_MEMORY
    memory: OrderedDict[str, Percept] = field(default_factory=OrderedDict)

    def __post_init__(self) -> None:
        if not 1 <= self.max_memory <= 1024:
            raise CognitionError("max_memory out of range")
        for name in ("hunger", "fatigue", "health"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and math.isfinite(v) and 0.0 <= v <= 1.0):
                raise CognitionError(f"{name} must be within [0, 1]")

    def observe(self, percepts: tuple[Percept, ...]) -> None:
        for p in percepts:
            self.memory.pop(p.entity_id, None)
            self.memory[p.entity_id] = p
        while len(self.memory) > self.max_memory:
            self.memory.popitem(last=False)

    def digest(self) -> str:
        body = {"npc": self.npc_id, "h": self.hunger, "f": self.fatigue, "hp": self.health,
                "mem": [[k, v.tick] for k, v in self.memory.items()]}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Decision:
    action: str
    target: str | None
    source: str  # "planner" | "fallback"
    reason: str


Planner = Callable[[Mapping[str, object]], Mapping[str, object]]


def _fallback(mind: NpcMind, percepts: tuple[Percept, ...]) -> tuple[str, str | None]:
    hostiles = [p for p in percepts if p.hostile]
    food = [p for p in percepts if p.kind == "food"]
    social = [p for p in percepts if p.kind in ("npc", "player") and not p.hostile]
    if hostiles:
        h = hostiles[0]
        if mind.health < 0.4 or h.distance > 1.5:
            return ("flee", h.entity_id) if mind.health < 0.4 else ("approach", h.entity_id)
        return "attack", h.entity_id
    if mind.hunger >= 0.6 and food:
        return ("eat", food[0].entity_id) if food[0].distance <= 1.5 else ("approach", food[0].entity_id)
    if mind.fatigue >= 0.7:
        return "rest", None
    if social and social[0].distance <= 2.0:
        return "talk", social[0].entity_id
    return "wander", None


def decide(world: WorldState, mind: NpcMind, *, planner: Planner | None = None, radius: float = 8.0,
           budget_calls: int = 1) -> Decision:
    """One cognition tick: perceive authoritative state, remember, decide."""
    percepts = perceive(world, mind.npc_id, radius=radius)
    mind.observe(percepts)
    if planner is None or budget_calls < 1:
        a, t = _fallback(mind, percepts)
        return Decision(a, t, "fallback", "no planner" if planner is None else "budget exhausted")
    view = {"npc": mind.npc_id, "tick": world.tick, "hunger": mind.hunger, "fatigue": mind.fatigue,
            "health": mind.health, "actions": list(ACTIONS),
            "percepts": [p.__dict__.copy() for p in percepts],
            "memory": [p.entity_id for p in mind.memory.values()]}
    try:
        out = planner(view)
        action = out.get("action") if isinstance(out, Mapping) else None
        target = out.get("target") if isinstance(out, Mapping) else None
        reason = None
        if action not in ACTIONS:
            reason = "invalid action"
        elif target is not None and (not isinstance(target, str) or target not in mind.memory):
            reason = "target not perceived"
        elif action in ("attack", "eat", "talk") and (target is None or target not in {p.entity_id for p in percepts}):
            reason = "contact action needs a currently perceived target"
        if reason is None:
            return Decision(action, target, "planner", "ok")
    except Exception as exc:  # planner faults must never break the tick
        reason = f"planner error: {type(exc).__name__}"
    a, t = _fallback(mind, percepts)
    return Decision(a, t, "fallback", reason)
