"""Sparse deterministic terrain with actual finite stocks, collision and construction.

32x32 chunks are GENERATED ON DEMAND; no huge memory arrays. A deterministic
hash-derived base cell is immutable, while mined/constructed edits form a
bounded persistent overlay. Coordinates are signed and all operations are
fail-closed. This is a real tile physics/economy kernel, not a renderer, GPU
voxel world, or unlimited fully simulated landscape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError

TERRAIN_SCHEMA = "original-world-sparse-terrain.v1"
CHUNK_SIDE = 32
WORLD_LIMIT = 1 << 20
MAX_EDITS = 2048
MAX_EVENTS = 2048
KINDS = ("meadow", "grove", "stone", "marsh", "cliff", "spring", "sand", "orchard")
BIOMES = ("temperate", "desert", "tundra", "archipelago", "forest", "caverns")


@dataclass(frozen=True)
class Cell:
    x: int
    y: int
    kind: str
    elevation: int
    wood: int
    stone: int
    food: int
    water: int
    bridge: bool = False
    building: str = ""
    visits: int = 0

    @property
    def blocking(self) -> bool:
        return self.kind in ("cliff", "marsh") and not self.bridge


@dataclass(frozen=True)
class TileEdit:
    x: int
    y: int
    kind: str
    wood: int
    stone: int
    food: int
    water: int
    bridge: bool
    building: str
    visits: int


@dataclass(frozen=True)
class TerrainState:
    design_id: str
    biome: str
    position: tuple[int, int] = (0, 0)
    origin: tuple[int, int] = (0, 0)
    energy: int = 20
    lumber: int = 3
    masonry: int = 3
    provisions: int = 5
    freshwater: int = 5
    shelter: int = 0
    edits: tuple[TileEdit, ...] = ()
    turns: int = 0
    events: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class TerrainAction:
    verb: str
    target_x: int
    target_y: int
    amount: int = 1


def _digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _int(value: object, low: int, high: int, label: str):
    if type(value) is not int or not low <= value <= high:
        raise FoundationError("invalid terrain " + label)


def _coords(x: int, y: int) -> None:
    _int(x, -WORLD_LIMIT, WORLD_LIMIT, "x")
    _int(y, -WORLD_LIMIT, WORLD_LIMIT, "y")


def chunk_key(x: int, y: int) -> tuple[int, int]:
    _coords(x, y)
    return x // CHUNK_SIDE, y // CHUNK_SIDE


def _base_cell(design_id: str, biome: str, x: int, y: int) -> Cell:
    _coords(x, y)
    if not isinstance(design_id, str) or len(design_id) != 64:
        raise FoundationError("world identity must be SHA-256 shaped")
    if biome not in BIOMES:
        raise FoundationError("unsupported biome")
    if x == 0 and y == 0:
        return Cell(0, 0, "meadow", 1, 3, 2, 3, 2)
    r = sha256(f"{design_id}:{biome}:{x}:{y}".encode()).digest()
    kind = KINDS[r[0] % len(KINDS)]
    if biome == "desert" and r[0] % 3 == 0:
        kind = "sand"
    elif biome == "archipelago" and r[0] % 3 == 0:
        kind = "marsh"
    elif biome == "caverns" and r[0] % 3 == 0:
        kind = "stone"
    return Cell(
        x, y, kind, r[1] % 6,
        (1 + r[2] % 5) if kind in ("grove", "orchard", "meadow") else 0,
        (1 + r[3] % 6) if kind in ("stone", "cliff", "sand") else 0,
        (1 + r[4] % 4) if kind in ("orchard", "meadow", "grove") else 0,
        (1 + r[5] % 5) if kind in ("spring", "marsh") else 0,
    )


def validate_terrain(state: TerrainState) -> None:
    if not isinstance(state, TerrainState):
        raise FoundationError("invalid terrain world state")
    _base_cell(state.design_id, state.biome, 0, 0)
    for point in (state.position, state.origin):
        if not isinstance(point, tuple) or len(point) != 2:
            raise FoundationError("invalid world position")
        _coords(*point)
    for name in ("energy", "lumber", "masonry", "provisions", "freshwater", "shelter"):
        _int(getattr(state, name), 0, 1000, name)
    _int(state.turns, 0, 1000000, "clock")
    _int(state.events, 0, MAX_EVENTS, "event count")
    if not isinstance(state.edits, tuple) or len(state.edits) > MAX_EDITS:
        raise FoundationError("invalid sparse terrain overlay")
    keys = []
    for tile in state.edits:
        if not isinstance(tile, TileEdit):
            raise FoundationError("invalid tile edit")
        _coords(tile.x, tile.y)
        if tile.kind not in KINDS or tile.building not in ("", "hearth", "mill", "beacon"):
            raise FoundationError("illegal tile kind/building")
        for name in ("wood", "stone", "food", "water", "visits"):
            _int(getattr(tile, name), 0, 1000, "tile " + name)
        if type(tile.bridge) is not bool:
            raise FoundationError("bridge flag is not boolean")
        base = _base_cell(state.design_id, state.biome, tile.x, tile.y)
        for material in ("wood", "stone", "food", "water"):
            if getattr(tile, material) > getattr(base, material):
                raise FoundationError("sparse tile edits cannot create natural resources")
        keys.append((tile.x, tile.y))
    if keys != sorted(set(keys)):
        raise FoundationError("duplicate or unordered terrain edits")
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64
            or any(x not in "0123456789abcdef" for x in state.event_head)):
        raise FoundationError("invalid terrain event head")


def create_terrain(design_id: str, biome: str = "temperate") -> TerrainState:
    state = TerrainState(design_id=design_id, biome=biome)
    validate_terrain(state)
    return state


def cell_at(state: TerrainState, x: int, y: int) -> Cell:
    _coords(x, y)
    base = _base_cell(state.design_id, state.biome, x, y)
    for tile in state.edits:
        if tile.x == x and tile.y == y:
            return replace(base, kind=tile.kind, wood=tile.wood,
                           stone=tile.stone, food=tile.food, water=tile.water,
                           bridge=tile.bridge, building=tile.building,
                           visits=tile.visits)
    return base


def chunk_cells(state: TerrainState, cx: int, cy: int) -> tuple[Cell, ...]:
    _int(cx, -WORLD_LIMIT // CHUNK_SIDE, WORLD_LIMIT // CHUNK_SIDE - 1, "chunk x")
    _int(cy, -WORLD_LIMIT // CHUNK_SIDE, WORLD_LIMIT // CHUNK_SIDE - 1, "chunk y")
    return tuple(cell_at(state, cx * CHUNK_SIDE + dx,
                         cy * CHUNK_SIDE + dy)
                 for dy in range(CHUNK_SIDE) for dx in range(CHUNK_SIDE))


def _write_cell(state: TerrainState, cell: Cell) -> TerrainState:
    entries = {(edit.x, edit.y): edit for edit in state.edits}
    entries[(cell.x, cell.y)] = TileEdit(
        cell.x, cell.y, cell.kind, cell.wood, cell.stone,
        cell.food, cell.water, cell.bridge, cell.building, cell.visits,
    )
    if len(entries) > MAX_EDITS:
        raise FoundationError("terrain edit capacity exceeded")
    return replace(state, edits=tuple(entries[key] for key in sorted(entries)))


def step_terrain(state: TerrainState, action: TerrainAction) -> tuple[TerrainState, str]:
    validate_terrain(state)
    if state.events >= MAX_EVENTS:
        raise FoundationError("terrain event budget exhausted")
    if not isinstance(action, TerrainAction):
        raise FoundationError("invalid terrain action")
    _coords(action.target_x, action.target_y)
    _int(action.amount, 1, 3, "action magnitude")
    if action.verb not in (
        "walk", "jump", "chop", "mine", "forage", "draw", "bridge",
        "dig", "build_hearth", "build_mill", "build_beacon",
        "rest", "eat", "end_turn",
    ):
        raise FoundationError("unsupported physical terrain verb")
    current = state.position
    distance = abs(current[0] - action.target_x) + abs(current[1] - action.target_y)
    needs_adjacent = action.verb in ("walk", "jump")
    if needs_adjacent and distance != 1:
        raise FoundationError("tile travel requires adjacent physical grid position")
    if not needs_adjacent and action.verb != "end_turn" and (
        action.target_x, action.target_y
    ) != current:
        raise FoundationError("tile interaction requires physically present player")
    updated = state
    tile = cell_at(state, action.target_x, action.target_y)
    if action.verb in ("walk", "jump"):
        if tile.blocking and action.verb != "jump":
            raise FoundationError("solid cliff or unbridged flooded tile prevents walking")
        climb = max(0, tile.elevation - cell_at(state, *current).elevation)
        if action.verb == "walk" and climb > 1:
            raise FoundationError("elevation requires jump")
        cost = 2 if action.verb == "jump" else 1
        if state.energy < cost:
            raise FoundationError("insufficient movement stamina")
        if action.verb == "jump" and climb > 3:
            raise FoundationError("jump cannot cross impassable height")
        updated = replace(state, energy=state.energy - cost,
                          position=(action.target_x, action.target_y))
        tile = replace(tile, visits=min(1000, tile.visits + 1))
        updated = _write_cell(updated, tile)
    elif action.verb in ("chop", "mine", "forage", "draw"):
        source = {"chop": "wood", "mine": "stone", "forage": "food", "draw": "water"}[action.verb]
        inventory = {"chop": "lumber", "mine": "masonry",
                     "forage": "provisions", "draw": "freshwater"}[action.verb]
        if getattr(tile, source) < action.amount or state.energy < action.amount:
            raise FoundationError("depleted physical resource or insufficient stamina")
        if getattr(state, inventory) + action.amount > 1000:
            raise FoundationError("resource inventory full")
        updated = replace(state, energy=state.energy - action.amount,
                          **{inventory: getattr(state, inventory) + action.amount})
        updated = _write_cell(updated, replace(
            tile, **{source: getattr(tile, source) - action.amount}))
    elif action.verb == "bridge":
        if tile.kind not in ("marsh", "cliff") or tile.bridge:
            raise FoundationError("bridge must cover an unbridged hazard tile")
        if state.lumber < 2 or state.masonry < 1:
            raise FoundationError("bridge needs two logs and one masonry stock")
        updated = replace(state, lumber=state.lumber - 2,
                          masonry=state.masonry - 1)
        updated = _write_cell(updated, replace(tile, bridge=True))
    elif action.verb == "dig":
        if tile.kind != "cliff" or state.masonry < 1:
            raise FoundationError("dig requires cliff and supported excavation materials")
        updated = replace(state, masonry=state.masonry - 1)
        updated = _write_cell(updated, replace(tile, kind="stone"))
    elif action.verb.startswith("build_"):
        building = action.verb[len("build_"):]
        if tile.building or tile.kind in ("cliff", "marsh") and not tile.bridge:
            raise FoundationError("structure requires safe empty ground")
        cost = {"hearth": (2, 1), "mill": (1, 3), "beacon": (2, 2)}[building]
        if state.lumber < cost[0] or state.masonry < cost[1]:
            raise FoundationError("insufficient construction inventory")
        updated = replace(state, lumber=state.lumber - cost[0],
                          masonry=state.masonry - cost[1],
                          shelter=min(1000, state.shelter + (1 if building == "hearth" else 0)))
        updated = _write_cell(updated, replace(tile, building=building))
    elif action.verb == "rest":
        if state.provisions < action.amount:
            raise FoundationError("rest costs edible provisions")
        updated = replace(state, provisions=state.provisions - action.amount,
                          energy=min(1000, state.energy + 4 * action.amount))
    elif action.verb == "eat":
        if state.provisions < action.amount:
            raise FoundationError("cannot consume food that is not possessed")
        updated = replace(state, provisions=state.provisions - action.amount,
                          energy=min(1000, state.energy + 2 * action.amount))
    else:  # end_turn
        updated = replace(state, turns=state.turns + 1,
                          energy=min(1000, state.energy + max(1, state.shelter)))
    receipt = _digest({
        "schema": TERRAIN_SCHEMA, "prev": state.event_head,
        "before": asdict(state), "after": asdict(updated),
        "action": asdict(action),
    })
    updated = replace(updated, events=state.events + 1, event_head=receipt)
    validate_terrain(updated)
    return updated, receipt


def terrain_save(state: TerrainState) -> str:
    validate_terrain(state)
    payload = {"schema": TERRAIN_SCHEMA, "state": asdict(state)}
    return json.dumps({"payload": payload, "checksum": _digest(payload)},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def terrain_restore(text: str) -> TerrainState:
    if not isinstance(text, str) or len(text.encode()) > 1048576:
        raise FoundationError("terrain save invalid or oversized")
    try:
        obj = json.loads(text)
        if set(obj) != {"payload", "checksum"} or obj["checksum"] != _digest(obj["payload"]):
            raise FoundationError("terrain save checksum mismatch")
        data = obj["payload"]
        if data["schema"] != TERRAIN_SCHEMA or set(data["state"]) != set(TerrainState.__dataclass_fields__):
            raise FoundationError("terrain save version or fields mismatch")
        raw = data["state"]
        raw["position"] = tuple(raw["position"])
        raw["origin"] = tuple(raw["origin"])
        raw["edits"] = tuple(TileEdit(**edit) for edit in raw["edits"])
        result = TerrainState(**raw)
        validate_terrain(result)
        return result
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FoundationError("terrain save rejected") from exc
