"""Deterministic twelve-profession NPC agents on real sparse terrain.

Every resident observes tiles, walks only four-way passable edges, gathers
finite physical stocks, and carries resources back to a common depot.
No location teleportation, infinite spawn, invisible off-map extraction,
provider LLM, or disguised NPC population counter. Goal selection is
deterministic utility-based; a small local bounded BFS performs navigation.
"""
from __future__ import annotations
from collections import deque
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_terrain import (
    Cell, TerrainState, _write_cell, cell_at, validate_terrain,
)

ROLES = ("forager", "forester", "mason", "farmer", "builder", "courier",
         "scout", "guardian", "healer", "naturalist", "engineer", "caretaker")
AGENT_SCHEMA = "original-world-physical-agents.v1"
MAX_AGENTS = 32
MAX_TICKS = 1000
MAX_PATH_SCAN = 256
MAX_RADIUS = 12


@dataclass(frozen=True)
class Person:
    id: int
    profession: str
    x: int
    y: int
    energy: int = 12
    hunger: int = 0
    health: int = 20
    experience: int = 0
    cargo_kind: str = ""
    cargo: int = 0
    discoveries: int = 0
    relationships: int = 4


@dataclass(frozen=True)
class PhysicalSociety:
    terrain_design_id: str
    inhabitants: tuple[Person, ...]
    tick: int = 0
    event_head: str = "0" * 64
    event_count: int = 0


@dataclass(frozen=True)
class NpcReceipt:
    number: int
    agent_id: int
    profession: str
    operation: str
    source: tuple[int, int]
    destination: tuple[int, int]
    material: str
    quantity: int


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode()).hexdigest()


def _walkable(terrain: TerrainState, x: int, y: int) -> bool:
    try:
        return not cell_at(terrain, x, y).blocking
    except FoundationError:
        return False


def _neighbors(terrain: TerrainState, x: int, y: int):
    source = cell_at(terrain, x, y)
    for px, py in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if _walkable(terrain, px, py):
            dest = cell_at(terrain, px, py)
            if abs(dest.elevation - source.elevation) <= 2:
                yield px, py


def _path(terrain: TerrainState, start: tuple[int, int], goal):
    if goal(*start):
        return (start,)
    frontier = deque((start,))
    previous = {start: None}
    while frontier and len(previous) < MAX_PATH_SCAN:
        current = frontier.popleft()
        for neighbor in _neighbors(terrain, *current):
            if (neighbor in previous or
                    abs(neighbor[0] - start[0]) + abs(neighbor[1] - start[1]) > MAX_RADIUS):
                continue
            previous[neighbor] = current
            if goal(*neighbor):
                path = [neighbor]
                cursor = current
                while cursor is not None:
                    path.append(cursor)
                    cursor = previous[cursor]
                return tuple(reversed(path))
            frontier.append(neighbor)
    return ()


def validate_society(society: PhysicalSociety, terrain: TerrainState):
    validate_terrain(terrain)
    if not isinstance(society, PhysicalSociety):
        raise FoundationError("invalid autonomous inhabitants")
    if society.terrain_design_id != terrain.design_id:
        raise FoundationError("physical inhabitants were authored for another world")
    if not isinstance(society.inhabitants, tuple) or not 1 <= len(society.inhabitants) <= MAX_AGENTS:
        raise FoundationError("invalid real NPC roster")
    ids = []
    for person in society.inhabitants:
        if not isinstance(person, Person) or person.profession not in ROLES:
            raise FoundationError("unrecognized inhabitant role")
        if type(person.id) is not int or not 0 <= person.id < MAX_AGENTS:
            raise FoundationError("invalid inhabitant identity")
        for field, cap in (
            ("energy", 20), ("hunger", 20), ("health", 20),
            ("experience", 1000), ("cargo", 3),
            ("discoveries", 1000), ("relationships", 20),
        ):
            value = getattr(person, field)
            if type(value) is not int or not 0 <= value <= cap:
                raise FoundationError("illegal inhabitant " + field)
        if (person.cargo_kind not in ("", "wood", "stone", "food", "water")
                or (person.cargo_kind == "") != (person.cargo == 0)):
            raise FoundationError("cargo ledger inconsistent")
        cell_at(terrain, person.x, person.y)
        if not _walkable(terrain, person.x, person.y):
            raise FoundationError("inhabitant occupies an unbridged solid hazard")
        ids.append(person.id)
    if ids != sorted(set(ids)):
        raise FoundationError("inhabitants must have unique stable sorted identities")
    for field in ("tick", "event_count"):
        value = getattr(society, field)
        if type(value) is not int or not 0 <= value <= MAX_TICKS:
            raise FoundationError("invalid physical society " + field)
    if not isinstance(society.event_head, str) or len(society.event_head) != 64:
        raise FoundationError("invalid physical inhabitant receipt chain")


def create_society(terrain: TerrainState, count: int = 12) -> PhysicalSociety:
    validate_terrain(terrain)
    if type(count) is not int or not 1 <= count <= MAX_AGENTS:
        raise FoundationError("inhabitant count outside bounded budget")
    placement = []
    frontier = deque([(0, 0)])
    seen = {(0, 0)}
    while frontier and len(placement) < count:
        place = frontier.popleft()
        placement.append(place)
        for next_xy in _neighbors(terrain, *place):
            if next_xy not in seen:
                seen.add(next_xy)
                frontier.append(next_xy)
    if not placement:
        raise FoundationError("no safe settlement foundation")
    roster = tuple(
        Person(index, ROLES[index % len(ROLES)],
               *placement[index % len(placement)])
        for index in range(count)
    )
    result = PhysicalSociety(terrain.design_id, roster)
    validate_society(result, terrain)
    return result


def _specialty(person: Person):
    return {
        "forager": "food", "forester": "wood", "mason": "stone",
        "farmer": "food", "builder": "wood", "courier": "food",
        "scout": "", "guardian": "", "healer": "water",
        "naturalist": "food", "engineer": "stone", "caretaker": "water",
    }[person.profession]


def _resource(cell: Cell, kind: str) -> int:
    return {
        "wood": cell.wood, "stone": cell.stone,
        "food": cell.food, "water": cell.water,
    }.get(kind, 0)


def _acquire(
    terrain: TerrainState, person: Person, kind: str,
) -> tuple[TerrainState, Person, str, str, int]:
    position = (person.x, person.y)
    tile = cell_at(terrain, *position)
    if _resource(tile, kind) > 0:
        updated = _write_cell(
            terrain, replace(tile, **{kind: _resource(tile, kind) - 1}))
        return updated, replace(
            person, energy=max(0, person.energy - 2),
            cargo_kind=kind, cargo=1,
            experience=min(1000, person.experience + 1),
        ), "gather", kind, 1
    path = _path(
        terrain, position,
        lambda x, y: _resource(cell_at(terrain, x, y), kind) > 0,
    )
    if len(path) > 1:
        nx, ny = path[1]
        return terrain, replace(
            person, x=nx, y=ny, energy=max(0, person.energy - 1),
        ), "navigate-to-stock", "", 0
    return terrain, person, "no-reachable-stock", "", 0


def _deliver(terrain: TerrainState, person: Person):
    if (person.x, person.y) != (0, 0):
        path = _path(terrain, (person.x, person.y),
                     lambda x, y: (x, y) == (0, 0))
        if len(path) > 1:
            nx, ny = path[1]
            return terrain, replace(person, x=nx, y=ny,
                                    energy=max(0, person.energy - 1)), "return-to-depot", "", 0
        return terrain, person, "inaccessible-depot", "", 0
    field = {"wood": "lumber", "stone": "masonry",
             "food": "provisions", "water": "freshwater"}[person.cargo_kind]
    if getattr(terrain, field) + person.cargo > 1000:
        return terrain, person, "depot-stock-full", "", 0
    result = replace(terrain, **{field: getattr(terrain, field) + person.cargo})
    cargo = person.cargo
    return result, replace(person, cargo=0, cargo_kind="",
                           relationships=min(20, person.relationships + 1)), "deliver", field, cargo


def npc_tick(
    terrain: TerrainState, society: PhysicalSociety,
) -> tuple[TerrainState, PhysicalSociety, tuple[NpcReceipt, ...]]:
    validate_society(society, terrain)
    if society.event_count >= MAX_TICKS or society.tick >= MAX_TICKS:
        raise FoundationError("inhabitant simulation tick budget exhausted")
    previous = society
    inhabitants = []
    receipts = []
    world = terrain
    for person in society.inhabitants:
        source = (person.x, person.y)
        p = replace(person, hunger=min(20, person.hunger + 1))
        operation, stock, count = "idle", "", 0
        if p.health == 0:
            operation = "incapacitated"
        elif p.hunger >= 7:
            if (p.x, p.y) == (0, 0) and world.provisions > 0:
                world = replace(world, provisions=world.provisions - 1)
                p = replace(p, hunger=max(0, p.hunger - 7),
                            health=min(20, p.health + 1))
                operation = "eat-finite-food"
            else:
                if p.hunger >= 15:
                    p = replace(p, health=max(0, p.health - 1))
                path = _path(world, (p.x, p.y),
                             lambda x, y: (x, y) == (0, 0))
                if len(path) > 1:
                    p = replace(p, x=path[1][0], y=path[1][1],
                                energy=max(0, p.energy - 1))
                    operation = "return-for-meal"
                else:
                    operation = "starving-no-food"
        elif p.energy <= 2:
            p = replace(p, energy=min(20, p.energy + 4))
            operation = "rest"
        elif p.cargo:
            world, p, operation, stock, count = _deliver(world, p)
        else:
            material = _specialty(p)
            if material:
                world, p, operation, stock, count = _acquire(world, p, material)
            elif p.profession == "scout":
                path = tuple(_neighbors(world, p.x, p.y))
                if path:
                    destination = path[(society.tick + p.id) % len(path)]
                    p = replace(p, x=destination[0], y=destination[1],
                                discoveries=min(1000, p.discoveries + 1),
                                energy=max(0, p.energy - 1))
                    operation = "scout-real-passable-tile"
            elif p.profession in ("guardian", "healer"):
                if p.profession == "healer" and world.provisions > 0 and p.health < 20:
                    world = replace(world, provisions=world.provisions - 1)
                    p = replace(p, health=min(20, p.health + 2))
                    operation = "heal-from-actual-stock"
                else:
                    p = replace(p, relationships=min(20, p.relationships + 1))
                    operation = "maintain-local-trust"
        inhabitants.append(p)
        receipts.append(NpcReceipt(
            society.event_count + 1, p.id, p.profession, operation,
            source, (p.x, p.y), stock, count,
        ))
    outcome = replace(
        society, tick=society.tick + 1,
        inhabitants=tuple(inhabitants), event_count=society.event_count + 1,
        event_head=_digest({
            "schema": AGENT_SCHEMA, "prior": previous.event_head,
            "before": asdict(previous),
            "after": [asdict(p) for p in inhabitants],
            "terrain": world.event_head, "stock": {
                k: getattr(world, k) for k in
                ("lumber", "masonry", "provisions", "freshwater")
            },
            "actions": [asdict(receipt) for receipt in receipts],
        }),
    )
    validate_society(outcome, world)
    return world, outcome, tuple(receipts)


def society_save(society: PhysicalSociety) -> dict:
    return {"schema": AGENT_SCHEMA, "payload": asdict(society),
            "checksum": _digest(asdict(society))}


def society_restore(data: dict, terrain: TerrainState) -> PhysicalSociety:
    try:
        if set(data) != {"schema", "payload", "checksum"} or data["schema"] != AGENT_SCHEMA:
            raise FoundationError("unknown autonomous actor envelope")
        if data["checksum"] != _digest(data["payload"]):
            raise FoundationError("autonomous actors checksum mismatch")
        raw = data["payload"]
        if set(raw) != set(PhysicalSociety.__dataclass_fields__):
            raise FoundationError("unknown persisted actor field")
        raw["inhabitants"] = tuple(Person(**actor) for actor in raw["inhabitants"])
        obj = PhysicalSociety(**raw)
        validate_society(obj, terrain)
        return obj
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise FoundationError("autonomous society save rejected") from exc
