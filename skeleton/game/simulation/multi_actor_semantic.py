"""Multi-actor native semantic physics on the real game controllers (GF-P0-184).

Replaces bounded single-actor reference proxies with a deterministic step
over many actors, each driven by the canonical ``CharacterController`` and
collided with the canonical broadphase/narrowphase.

Units are integers (millimetres, nanoseconds) to keep replay bit-exact.
Each tick:

1. every actor's controller intent (a desired velocity) is clamped to the
   controller speed budget and applied via ``CharacterController.move``;
2. gravity is integrated for airborne actors and the floor plane resolved;
3. actor/actor and actor/static contacts are found with ``broadphase_pairs``
   and ``narrowphase_aabb`` and separated along the minimum-penetration axis;
4. semantic events (``contact_begin``, ``contact_end``, ``landed``,
   ``shoved``, ``hard_impact``) are emitted from the state change.

The output tick receipt chains a digest of the full state so the result can
be replayed and compared by the native audit tooling.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

from .flgb_simulation_runtime import (
    AABB, CharacterController, SimulationContractError,
    broadphase_pairs, narrowphase_aabb,
)

GRAVITY_MM_S2 = -9_810
HARD_IMPACT_MM_S = 6_000
SHOVE_MM = 50
MAX_ACTORS = 512


class MultiActorError(SimulationContractError):
    pass


@dataclass(frozen=True)
class ActorBody:
    controller: CharacterController
    half_extent_mm: tuple[int, int, int]
    mass_g: int
    vertical_velocity_mm_s: int = 0
    role: str = "npc"

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in self.half_extent_mm) or len(self.half_extent_mm) != 3:
            raise MultiActorError("half extents must be 3 positive ints")
        if type(self.mass_g) is not int or self.mass_g <= 0:
            raise MultiActorError("mass must be positive grams")
        if self.role not in ("player", "npc", "creature", "prop"):
            raise MultiActorError("unknown actor role")

    @property
    def actor_id(self) -> str:
        return self.controller.entity_id

    def aabb(self) -> AABB:
        p, h = self.controller.position, self.half_extent_mm
        return AABB(self.actor_id, tuple(p[i] - h[i] for i in range(3)),
                    tuple(p[i] + h[i] for i in range(3)))


@dataclass(frozen=True)
class SemanticEvent:
    tick: int
    kind: str
    actors: tuple[str, ...]
    magnitude: int


@dataclass(frozen=True)
class TickReceipt:
    tick: int
    actors: tuple[ActorBody, ...]
    contacts: frozenset[tuple[str, str]]
    events: tuple[SemanticEvent, ...]
    state_digest: str
    prev_digest: str


def _clamp_intent(actor: ActorBody, intent: tuple[int, int], step_ns: int) -> tuple[int, int, int]:
    budget = actor.controller.max_speed_per_sec * step_ns // 1_000_000_000
    dx, dz = intent
    return (max(-budget, min(budget, dx * step_ns // 1_000_000_000)), 0,
            max(-budget, min(budget, dz * step_ns // 1_000_000_000)))


def _with_position(actor: ActorBody, pos: tuple[int, int, int], grounded: bool,
                   vy: int) -> ActorBody:
    c = actor.controller
    return replace(actor, controller=CharacterController(c.entity_id, pos, c.max_speed_per_sec,
                                                         grounded),
                   vertical_velocity_mm_s=vy)


def _digest(tick: int, actors: Sequence[ActorBody], contacts: Iterable, prev: str) -> str:
    return sha256(json.dumps({
        "tick": tick, "prev": prev,
        "actors": [[a.actor_id, list(a.controller.position), a.controller.grounded,
                    a.vertical_velocity_mm_s] for a in actors],
        "contacts": sorted(list(c) for c in contacts),
    }, separators=(",", ":")).encode()).hexdigest()


def step_actors(
    actors: Sequence[ActorBody],
    intents: Mapping[str, tuple[int, int]],
    *,
    tick: int,
    step_ns: int,
    statics: Sequence[AABB] = (),
    floor_y_mm: int = 0,
    prev_contacts: frozenset[tuple[str, str]] = frozenset(),
    prev_digest: str = "0" * 64,
) -> TickReceipt:
    if not 1 <= len(actors) <= MAX_ACTORS:
        raise MultiActorError("1..512 actors required")
    if type(step_ns) is not int or not 1_000_000 <= step_ns <= 100_000_000:
        raise MultiActorError("step must be 1..100 ms")
    ids = [a.actor_id for a in actors]
    if len(set(ids)) != len(ids):
        raise MultiActorError("duplicate actor id")
    if set(intents) - set(ids):
        raise MultiActorError("intent for unknown actor")
    static_ids = {s.collider_id for s in statics}
    if static_ids & set(ids):
        raise MultiActorError("static collider id collides with actor id")
    events: list[SemanticEvent] = []
    moved: dict[str, ActorBody] = {}
    # 1 + 2: controller intent, gravity, floor.
    for actor in sorted(actors, key=lambda a: a.actor_id):
        delta = _clamp_intent(actor, intents.get(actor.actor_id, (0, 0)), step_ns)
        stepped = actor.controller.move(delta, step_ns)
        x, y, z = stepped.position
        vy = actor.vertical_velocity_mm_s
        if not actor.controller.grounded or y - actor.half_extent_mm[1] > floor_y_mm:
            vy += GRAVITY_MM_S2 * step_ns // 1_000_000_000
            y += vy * step_ns // 1_000_000_000
        grounded = False
        bottom = y - actor.half_extent_mm[1]
        if bottom <= floor_y_mm:
            y = floor_y_mm + actor.half_extent_mm[1]
            if not actor.controller.grounded:
                kind = "hard_impact" if -vy >= HARD_IMPACT_MM_S else "landed"
                events.append(SemanticEvent(tick, kind, (actor.actor_id,), -vy))
            vy, grounded = 0, True
        moved[actor.actor_id] = _with_position(actor, (x, y, z), grounded, vy)
    # 3: contacts against actors and statics, resolved by mass ratio.
    boxes = [a.aabb() for a in moved.values()] + list(statics)
    by_id = {b.collider_id: b for b in boxes}
    contacts: set[tuple[str, str]] = set()
    for left_id, right_id in broadphase_pairs(boxes):
        contact = narrowphase_aabb(by_id[left_id], by_id[right_id])
        if contact is None:
            continue
        pair = (contact.left_id, contact.right_id)
        contacts.add(pair)
        axis = min((0, 2), key=lambda i: contact.penetration_xyz[i])
        depth = contact.penetration_xyz[axis]
        a, b = moved.get(pair[0]), moved.get(pair[1])
        if a is None and b is None:
            continue
        if a is None or b is None:
            actor = a or b
            other = by_id[pair[1] if a else pair[0]]
            centre = (other.min_xyz[axis] + other.max_xyz[axis]) // 2
            sign = 1 if actor.controller.position[axis] >= centre else -1
            pos = list(actor.controller.position)
            pos[axis] += sign * depth
            moved[actor.actor_id] = _with_position(actor, tuple(pos),
                                                   actor.controller.grounded,
                                                   actor.vertical_velocity_mm_s)
            continue
        sign = 1 if a.controller.position[axis] >= b.controller.position[axis] else -1
        total = a.mass_g + b.mass_g
        share_a = depth * b.mass_g // total
        share_b = depth - share_a
        for actor, share, s in ((a, share_a, sign), (b, share_b, -sign)):
            pos = list(actor.controller.position)
            pos[axis] += s * share
            moved[actor.actor_id] = _with_position(actor, tuple(pos),
                                                   actor.controller.grounded,
                                                   actor.vertical_velocity_mm_s)
            if share >= SHOVE_MM:
                events.append(SemanticEvent(tick, "shoved", (actor.actor_id,), share))
    # 4: semantic contact transitions.
    for pair in sorted(contacts - prev_contacts):
        events.append(SemanticEvent(tick, "contact_begin", pair, 0))
    for pair in sorted(prev_contacts - contacts):
        events.append(SemanticEvent(tick, "contact_end", pair, 0))
    ordered = tuple(moved[i] for i in sorted(moved))
    frozen = frozenset(contacts)
    return TickReceipt(tick, ordered, frozen,
                       tuple(sorted(events, key=lambda e: (e.kind, e.actors))),
                       _digest(tick, ordered, frozen, prev_digest), prev_digest)


def run_actors(actors: Sequence[ActorBody],
               intents_per_tick: Sequence[Mapping[str, tuple[int, int]]], *,
               step_ns: int, statics: Sequence[AABB] = (),
               floor_y_mm: int = 0) -> tuple[TickReceipt, ...]:
    receipts: list[TickReceipt] = []
    current = tuple(actors)
    contacts: frozenset[tuple[str, str]] = frozenset()
    prev = "0" * 64
    for tick, intents in enumerate(intents_per_tick):
        r = step_actors(current, intents, tick=tick, step_ns=step_ns,
                        statics=statics, floor_y_mm=floor_y_mm,
                        prev_contacts=contacts, prev_digest=prev)
        receipts.append(r)
        current, contacts, prev = r.actors, r.contacts, r.state_digest
    return tuple(receipts)


def event_signals(receipt: TickReceipt) -> dict[str, float]:
    """Map a tick into RPG environment signals (native_* family)."""
    speeds = [abs(a.vertical_velocity_mm_s) / 1000 for a in receipt.actors]
    energy = sum(a.mass_g / 1000 * (a.vertical_velocity_mm_s / 1000) ** 2 / 2
                 for a in receipt.actors)
    return {
        "native_vertical_speed_mps": max(speeds),
        "native_contact_count": float(len(receipt.contacts)),
        "native_kinetic_energy_j": energy,
    }
