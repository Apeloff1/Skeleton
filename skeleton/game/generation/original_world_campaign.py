"""Playable, offline, event-sourced 12-sector sandbox for four authored worlds.

This is deliberately not a compiler for all 1,296 source world laws.
It implements four original causal scenarios and a shared, deterministic
turn-based simulation across resource, ecology, navigation, governance,
settlement and comfort systems. All world state is immutable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from typing import Iterable

from .original_mechanic_catalog import MECHANICS
from .original_world_catalog import WORLDS

ENGINE_VERSION = "original-campaign.v1"
ROOM_COUNT = 12
MAX_EVENTS = 1024
SECTORS = ("Hearth", "Brook", "Pines", "Cliff", "Market", "Moss",
           "Cove", "Orchard", "Dunes", "Glade", "Ridge", "Lookout")
SCENARIOS = {
    "topology-02": "unobserved routes periodically reconnect",
    "ecology-03": "animal migration shifts precipitation and growth",
    "civilization-01": "only honored promises authorize new civic buildings",
    "serenity-05": "a never-finished communal quilt supports ongoing comfort",
}

# These are playable *operators* aligned to catalog action definitions, not
# a claim that all mechanics in each originating domain are implemented.
ACTION_MECHANICS = {
    "move": "voyage-m08",           # Single Harbor / one-way world access concept
    "observe": "wonder-m01",        # Curiosity Probe
    "forage": "survival-m01",        # Resource Intake
    "gather_wood": "forests-m06",    # Silviculture Compact
    "collect_stone": "geology-m03", # Mineral Survey
    "draw_water": "desert-m01",     # Oasis Rights
    "plant": "agriculture-m01",     # Crop Rotation
    "irrigate": "agriculture-m04",  # Irrigation Balance
    "harvest": "agriculture-m06",   # Harvest Window
    "rest": "serenity-m01",         # Soft Rest
    "eat": "metabolism-m01",       # Energy Budget
    "build_shelter": "survival-m02",# Thermal Shelter
    "repair": "crafting-m04",       # Repair Workflow
    "build_garden": "serenity-m07", # Garden Stewardship
    "craft_tool": "crafting-m01",   # Recipe Compiler
    "trade": "economy-m02",        # Food Futures / trade context
    "talk": "relationships-m03",   # Trust Accumulation
    "gift": "relationships-m05",   # Shared Discovery / cooperative contact
    "assist": "hospitality-m04",   # Emergency Rest
    "research": "education-m01",   # Curiosity Seed
    "survey": "mystery-m01",       # Evidence Collection
    "teach": "education-m02",      # Peer Instruction
    "pledge": "civilization-m01",   # Promise Foundations
    "fulfill": "civilization-m01",  # Promise Foundations
    "vote": "civilization-m02",    # Visitor Referendum
    "redirect_rain": "ecology-m02", # Rain Herding
    "stabilize_route": "topology-m11", # Breadcrumb Anchor
    "weave": "serenity-m08",        # Endless Domestic Life
    "guide_herd": "ecology-m07",    # Migration Shadow
    "heal": "medicine-m05",        # Rehabilitation Program
    "watch": "weather-m05",        # Forecast Revision
    "defend": "combat-m04",        # Shield of Promises
    "restore": "ecology-m06",      # Decomposer Commons
    "explore": "voyage-m04",       # Unending Frontier
    "end_turn": None,
}

class CampaignError(ValueError):
    """Invalid scenario, state, input or insufficient resources."""


@dataclass(frozen=True)
class Sector:
    id: int
    name: str
    biome: str
    food: int
    wood: int
    stone: int
    water: int
    wildlife: int
    fertility: int
    crop: int = 0
    contamination: int = 0
    building: str = ""


@dataclass(frozen=True)
class CampaignAction:
    verb: str
    target: int = -1
    amount: int = 1
    option: str = ""


@dataclass(frozen=True)
class CampaignState:
    world_id: str
    seed: str
    tick: int
    turn: int
    action_points: int
    position: int
    energy: int
    health: int
    hunger: int
    wood: int
    stone: int
    food: int
    water: int
    seeds: int
    tools: int
    medicine: int
    coins: int
    trust: int
    knowledge: int
    courage: int
    quilt: int
    civic_buildings: int
    promises: int
    honored_promises: int
    support_votes: int
    rain_west: int
    rain_east: int
    maze_phase: int
    observed_until: int
    explored: tuple[int, ...]
    anchors: tuple[tuple[int, int], ...]
    sectors: tuple[Sector, ...]
    quest_progress: int
    chapter_complete: bool
    postgame: bool
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class CampaignReceipt:
    action: CampaignAction
    before: str
    after: str
    event_id: str
    event_number: int
    messages: tuple[str, ...]


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _roll(seed: str, label: str, mod: int) -> int:
    return int.from_bytes(sha256((seed + ":" + label).encode()).digest()[:8], "big") % mod


def _require_int(value: int, low: int, high: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CampaignError(f"invalid {field}")


def validate_state(state: CampaignState) -> None:
    if not isinstance(state, CampaignState):
        raise CampaignError("state is not a CampaignState")
    if state.world_id not in SCENARIOS or state.world_id not in WORLDS:
        raise CampaignError("world does not have a playable adapter")
    if not isinstance(state.seed, str) or not 0 < len(state.seed.encode("utf-8")) <= 1024:
        raise CampaignError("invalid world seed")
    bounds = {
        "tick": (0, 1000000), "turn": (0, 1000000),
        "action_points": (0, 4), "position": (0, 11),
        "energy": (0, 20), "health": (0, 20), "hunger": (0, 20),
        "wood": (0, 10000), "stone": (0, 10000),
        "food": (0, 10000), "water": (0, 10000),
        "seeds": (0, 10000), "tools": (0, 10000),
        "medicine": (0, 10000), "coins": (0, 10000),
        "trust": (0, 100), "knowledge": (0, 100),
        "courage": (0, 100), "quilt": (0, 100),
        "civic_buildings": (0, 12), "promises": (0, 12),
        "honored_promises": (0, 100),
        "support_votes": (0, 100),
        "rain_west": (0, 12), "rain_east": (0, 12),
        "maze_phase": (0, 11), "observed_until": (0, 1000001),
        "quest_progress": (0, 100), "event_count": (0, 1000000),
    }
    for key, (low, high) in bounds.items():
        _require_int(getattr(state, key), low, high, key)
    if state.rain_west + state.rain_east != 12:
        raise CampaignError("rain must be conserved")
    if (not isinstance(state.chapter_complete, bool)
            or not isinstance(state.postgame, bool)):
        raise CampaignError("invalid campaign state flags")
    if state.postgame and not state.chapter_complete:
        raise CampaignError("postgame requires chapter completion")
    if (not isinstance(state.event_head, str) or
            len(state.event_head) != 64 or
            any(c not in "0123456789abcdef" for c in state.event_head)):
        raise CampaignError("invalid event head")
    if (not isinstance(state.sectors, tuple) or len(state.sectors) != ROOM_COUNT
            or any(not isinstance(tile, Sector) or tile.id != i or
                   tile.name != SECTORS[i] for i, tile in enumerate(state.sectors))):
        raise CampaignError("invalid terrain topology")
    for sector in state.sectors:
        if sector.biome not in {"forest", "wetland", "steppe", "rock", "meadow"}:
            raise CampaignError("unknown biome")
        for field in ("food", "wood", "stone", "water", "wildlife",
                      "fertility", "crop", "contamination"):
            _require_int(getattr(sector, field), 0, 100, "tile." + field)
        if sector.building not in {"", "shelter", "garden", "civic", "clinic"}:
            raise CampaignError("unknown building")
    if (not isinstance(state.explored, tuple) or
            not all(isinstance(i, int) and not isinstance(i, bool) and
                    0 <= i < ROOM_COUNT for i in state.explored) or
            len(state.explored) != len(set(state.explored)) or
            state.position not in state.explored):
        raise CampaignError("invalid exploration ledger")
    if not isinstance(state.anchors, tuple) or len(state.anchors) > 8:
        raise CampaignError("invalid anchor ledger")
    for edge in state.anchors:
        if (not isinstance(edge, tuple) or len(edge) != 2 or
                any(type(v) is not int or not 0 <= v < ROOM_COUNT for v in edge)
                or edge[0] >= edge[1]):
            raise CampaignError("invalid fixed passage")
    if len(state.anchors) != len(set(state.anchors)):
        raise CampaignError("duplicate anchored passage")


def create_campaign(world_id: str, seed: str = "new-world") -> CampaignState:
    if world_id not in SCENARIOS:
        raise CampaignError("no executable world-law adapter for this authored world")
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 1024:
        raise CampaignError("invalid seed")
    biomes = ("forest", "wetland", "steppe", "rock", "meadow")
    sectors = []
    for i, name in enumerate(SECTORS):
        biome = biomes[_roll(seed, "biome:" + str(i), len(biomes))]
        sectors.append(Sector(
            i, name, biome,
            3 + _roll(seed, "food:" + str(i), 6),
            2 + _roll(seed, "wood:" + str(i), 6),
            2 + _roll(seed, "stone:" + str(i), 5),
            3 + _roll(seed, "water:" + str(i), 6),
            2 + _roll(seed, "wild:" + str(i), 5),
            3 + _roll(seed, "fert:" + str(i), 6),
        ))
    state = CampaignState(
        world_id=world_id, seed=seed, tick=0, turn=0,
        action_points=4, position=0, energy=12, health=15,
        hunger=0, wood=3, stone=2, food=3, water=4, seeds=2,
        tools=1, medicine=1, coins=7, trust=10, knowledge=0,
        courage=5, quilt=0, civic_buildings=0, promises=0,
        honored_promises=0, support_votes=0,
        rain_west=6, rain_east=6, maze_phase=0,
        observed_until=0, explored=(0,), anchors=(),
        sectors=tuple(sectors), quest_progress=0,
        chapter_complete=False, postgame=False,
    )
    validate_state(state)
    return state


def edges(state: CampaignState) -> tuple[tuple[int, int], ...]:
    """Connected cyclic backbone plus time-varying shortcuts and anchors."""
    validate_state(state)
    fixed = {(min(i, (i + 1) % ROOM_COUNT),
              max(i, (i + 1) % ROOM_COUNT)) for i in range(ROOM_COUNT)}
    phase = state.maze_phase
    for a, b in ((phase, phase + 5), (phase + 2, phase + 8)):
        a %= ROOM_COUNT
        b %= ROOM_COUNT
        fixed.add((min(a, b), max(a, b)))
    fixed.update(state.anchors)
    return tuple(sorted(fixed))


def neighbors(state: CampaignState, room: int | None = None) -> tuple[int, ...]:
    at = state.position if room is None else room
    _require_int(at, 0, ROOM_COUNT - 1, "room")
    return tuple(sorted({b if a == at else a
                         for a, b in edges(state) if at in (a, b)}))


def shortest_path(state: CampaignState, goal: int) -> tuple[int, ...]:
    _require_int(goal, 0, ROOM_COUNT - 1, "goal")
    frontier = [state.position]
    parent = {state.position: None}
    for here in frontier:
        if here == goal:
            break
        for nxt in neighbors(state, here):
            if nxt not in parent:
                parent[nxt] = here
                frontier.append(nxt)
    if goal not in parent:
        raise CampaignError("world connectivity violation")
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    return tuple(reversed(path))


def _tile(state: CampaignState, **changes: object) -> tuple[Sector, ...]:
    tiles = list(state.sectors)
    tiles[state.position] = replace(tiles[state.position], **changes)
    return tuple(tiles)


def _spend(state: CampaignState, **costs: int) -> CampaignState:
    changes = {}
    for field, price in costs.items():
        if type(price) is not int or price < 0:
            raise CampaignError("invalid cost")
        current = getattr(state, field)
        if current < price:
            raise CampaignError("insufficient " + field)
        changes[field] = current - price
    return replace(state, **changes)


def _gain(state: CampaignState, field: str, count: int, ceiling: int = 10000) -> CampaignState:
    if type(count) is not int or count < 0:
        raise CampaignError("invalid gain")
    return replace(state, **{field: min(ceiling, getattr(state, field) + count)})


def _require_village(state: CampaignState) -> None:
    if state.position not in (0, 4, 8):
        raise CampaignError("requires a community meeting site")


def _require_option(option: str, choices: tuple[str, ...]) -> None:
    if option not in choices:
        raise CampaignError("invalid action option")


def _one_action(state: CampaignState, action: CampaignAction
                ) -> tuple[CampaignState, tuple[str, ...]]:
    verb, n, target, option = (
        action.verb, action.amount, action.target, action.option,
    )
    tile = state.sectors[state.position]
    if state.action_points <= 0:
        raise CampaignError("end the turn before another action")
    state = replace(state, action_points=state.action_points - 1)
    message = []

    if verb == "move":
        if n != 1 or target not in neighbors(state):
            raise CampaignError("destination is not an adjacent sector")
        if state.energy < 1:
            raise CampaignError("too exhausted to travel")
        discovered = target not in state.explored
        state = replace(state, position=target, energy=state.energy - 1,
                        explored=state.explored + ((target,) if discovered else ()))
        if discovered:
            state = _gain(state, "knowledge", 2, 100)
        message.append("Traveled to " + SECTORS[target])
    elif verb == "observe":
        state = _gain(state, "knowledge", n, 100)
        state = replace(state, observed_until=state.tick + 2)
        message.append("Observed the shifting surroundings")
    elif verb in {"forage", "gather_wood", "collect_stone", "draw_water"}:
        field, source = {
            "forage": ("food", "food"),
            "gather_wood": ("wood", "wood"),
            "collect_stone": ("stone", "stone"),
            "draw_water": ("water", "water"),
        }[verb]
        if getattr(tile, source) < n:
            raise CampaignError("local resource depleted")
        state = replace(state, sectors=_tile(state, **{
            source: getattr(tile, source) - n
        }), energy=max(0, state.energy - 1))
        state = _gain(state, field, n)
        message.append(f"Collected {n} {field}")
    elif verb == "plant":
        state = _spend(state, seeds=n, water=n)
        if tile.crop + n > 12:
            raise CampaignError("field is full")
        state = replace(state, sectors=_tile(state, crop=tile.crop + n))
        message.append("Sowed crop seeds")
    elif verb == "irrigate":
        state = _spend(state, water=n)
        if tile.crop == 0:
            raise CampaignError("no crops to irrigate")
        state = replace(state, sectors=_tile(
            state, fertility=min(100, tile.fertility + n)))
        message.append("Improved local growing conditions")
    elif verb == "harvest":
        if tile.crop < n:
            raise CampaignError("not enough ripe crops")
        state = replace(state, sectors=_tile(state, crop=tile.crop - n))
        state = _gain(state, "food", n * 2)
        message.append("Harvested food")
    elif verb == "rest":
        state = _gain(state, "energy", 3 * n, 20)
        state = replace(state, hunger=min(20, state.hunger + 1))
        message.append("Restored energy")
    elif verb == "eat":
        state = _spend(state, food=n)
        state = replace(state, hunger=max(0, state.hunger - 4 * n),
                        energy=min(20, state.energy + 2 * n))
        message.append("Shared a nourishing meal")
    elif verb == "build_shelter":
        if tile.building:
            raise CampaignError("this site already has a building")
        state = _spend(state, wood=2, stone=1)
        state = replace(state, sectors=_tile(state, building="shelter"))
        state = _gain(state, "trust", 1, 100)
        message.append("Built a shelter")
    elif verb == "repair":
        if tile.building == "":
            raise CampaignError("no building to repair")
        state = _spend(state, wood=1)
        state = replace(state, sectors=_tile(
            state, contamination=max(0, tile.contamination - 2)))
        state = _gain(state, "trust", 1, 100)
        message.append("Repaired local infrastructure")
    elif verb == "build_garden":
        if tile.building:
            raise CampaignError("building slot occupied")
        state = _spend(state, wood=1, seeds=1, water=1)
        state = replace(state, sectors=_tile(state, building="garden",
                                             fertility=min(100, tile.fertility + 3)))
        message.append("Built a community garden")
    elif verb == "craft_tool":
        state = _spend(state, wood=1, stone=1)
        state = _gain(state, "tools", 1)
        message.append("Crafted a durable hand tool")
    elif verb == "trade":
        _require_village(state)
        _require_option(option, ("buy_food", "sell_wood", "buy_seeds"))
        if option == "buy_food":
            state = _spend(state, coins=2 * n)
            state = _gain(state, "food", n)
        elif option == "sell_wood":
            state = _spend(state, wood=n)
            state = _gain(state, "coins", n * 2)
        else:
            state = _spend(state, coins=n)
            state = _gain(state, "seeds", n)
        message.append("Traded in the village market")
    elif verb == "talk":
        _require_village(state)
        state = _gain(state, "trust", n, 100)
        message.append("Discussed local needs")
    elif verb == "gift":
        _require_village(state)
        state = _spend(state, food=n)
        state = _gain(state, "trust", 2 * n, 100)
        message.append("Shared food with neighbors")
    elif verb == "assist":
        _require_village(state)
        state = _spend(state, water=n)
        state = _gain(state, "trust", n * 3, 100)
        message.append("Provided emergency community aid")
    elif verb == "research":
        state = _spend(state, energy=1)
        state = _gain(state, "knowledge", n * 2, 100)
        message.append("Researched a local phenomenon")
    elif verb == "survey":
        if state.knowledge < n:
            raise CampaignError("not enough knowledge to evaluate evidence")
        state = _gain(state, "knowledge", 1, 100)
        message.append("Recorded a verifiable geographic observation")
    elif verb == "teach":
        _require_village(state)
        state = _spend(state, knowledge=n)
        state = _gain(state, "trust", n * 2, 100)
        message.append("Shared useful skills with the community")
    elif verb == "pledge":
        _require_village(state)
        if state.promises + n > 12:
            raise CampaignError("too many unfulfilled commitments")
        state = replace(state, promises=state.promises + n)
        message.append("Made a verifiable civic promise")
    elif verb == "fulfill":
        _require_village(state)
        if state.promises < n:
            raise CampaignError("no outstanding promise")
        state = _spend(state, wood=n, food=n)
        state = replace(state, promises=state.promises - n,
                        honored_promises=state.honored_promises + n)
        state = _gain(state, "trust", n * 3, 100)
        message.append("Fulfilled a civic promise")
    elif verb == "vote":
        _require_village(state)
        if state.trust < 12:
            raise CampaignError("insufficient community trust")
        state = _gain(state, "support_votes", n * 2, 100)
        message.append("Held a public vote")
    elif verb == "redirect_rain":
        _require_option(option, ("west", "east"))
        if state.world_id != "ecology-03":
            raise CampaignError("herd-controlled rainfall only exists in Rain Eaters")
        if option == "west":
            if state.rain_east < n:
                raise CampaignError("insufficient eastern rainfall")
            state = replace(state, rain_west=state.rain_west + n,
                            rain_east=state.rain_east - n)
        else:
            if state.rain_west < n:
                raise CampaignError("insufficient western rainfall")
            state = replace(state, rain_east=state.rain_east + n,
                            rain_west=state.rain_west - n)
        message.append("Guided rain-bearing migration")
    elif verb == "stabilize_route":
        if state.world_id != "topology-02":
            raise CampaignError("anchoring is specific to the Blindside District")
        if target not in neighbors(state) or n != 1:
            raise CampaignError("anchor requires adjacent target")
        edge = tuple(sorted((state.position, target)))
        if edge in state.anchors:
            raise CampaignError("route already stabilized")
        state = _spend(state, wood=1, stone=1)
        state = replace(state, anchors=tuple(sorted(state.anchors + (edge,))))
        message.append("Anchored a changing passage")
    elif verb == "weave":
        if state.world_id != "serenity-05":
            raise CampaignError("the living quilt belongs to the Unfinished Quilt world")
        state = _spend(state, wood=n)
        state = _gain(state, "quilt", n * 2, 100)
        state = _gain(state, "trust", n, 100)
        message.append("Added another piece to the unfinished community quilt")
    elif verb == "guide_herd":
        if tile.wildlife < n:
            raise CampaignError("too few animals to safely guide")
        state = replace(state, sectors=_tile(state,
                                             wildlife=tile.wildlife - n))
        state = _gain(state, "trust", n, 100)
        message.append("Safely guided migrating animals")
    elif verb == "heal":
        state = _spend(state, medicine=n)
        state = _gain(state, "health", n * 4, 20)
        message.append("Applied a medical treatment")
    elif verb == "watch":
        state = replace(state, observed_until=state.tick + 1)
        state = _gain(state, "knowledge", n, 100)
        message.append("Reviewed local weather signals")
    elif verb == "defend":
        state = _spend(state, energy=n)
        state = _gain(state, "courage", n, 100)
        message.append("Reinforced the settlement's protective readiness")
    elif verb == "restore":
        state = _spend(state, water=n, wood=n)
        state = replace(state, sectors=_tile(
            state,
            contamination=max(0, tile.contamination - 2 * n),
            fertility=min(100, tile.fertility + n * 2)))
        state = _gain(state, "trust", n, 100)
        message.append("Restored damaged habitat")
    elif verb == "explore":
        state = _spend(state, energy=n)
        state = _gain(state, "knowledge", n * 2, 100)
        message.append("Surveyed a deeper, optional frontier")
    else:
        raise CampaignError("unimplemented player action")

    # Distinct authored causal laws: do not claim the 1,296 other worlds run.
    if state.world_id == "civilization-01" and verb == "fulfill":
        sector = state.sectors[state.position]
        if not sector.building and state.civic_buildings < 12:
            state = replace(
                state, sectors=_tile(state, building="civic"),
                civic_buildings=state.civic_buildings + 1,
            )
            message.append("An honored promise raised a civic building")
    if state.world_id == "serenity-05" and verb in {"weave", "rest"}:
        if state.quilt >= 4:
            state = _gain(state, "energy", 1, 20)
            message.append("The shared quilt offered additional comfort")
    progress = min(100, len(state.explored) * 2
                   + state.honored_promises * 5
                   + state.trust // 4 + state.knowledge // 5
                   + state.quilt // 2)
    state = replace(state, quest_progress=progress)
    if not state.chapter_complete and progress >= 24:
        state = replace(state, chapter_complete=True, postgame=True)
        message.append("Chapter completed; the persistent world continues")
    return state, tuple(message)


def _advance_turn(state: CampaignState) -> tuple[CampaignState, tuple[str, ...]]:
    if state.turn >= 1000000 or state.tick >= 1000000:
        raise CampaignError("simulation time limit reached")
    tiles = []
    season = (state.turn // 8) % 4
    for tile in state.sectors:
        rain = state.rain_west if tile.id < 6 else state.rain_east
        new_crop = min(12, tile.crop + (1 if tile.crop and rain >= 5 and
                                        tile.fertility >= 3 and season != 3 else 0))
        # Resource recovery is finite per turn, never instantaneous.
        food = min(20, tile.food + (1 if tile.wildlife > 2 and rain >= 4 else 0))
        forest = min(18, tile.wood + (1 if tile.biome == "forest" and
                                     state.turn % 3 == 0 else 0))
        tiles.append(replace(tile, crop=new_crop, food=food, wood=forest))
    starving = state.hunger >= 17
    health = max(0, state.health - (1 if starving else 0))
    new_hunger = min(20, state.hunger + 1)
    next_state = replace(state, sectors=tuple(tiles), tick=state.tick + 1,
                         turn=state.turn + 1, action_points=4,
                         hunger=new_hunger, health=health,
                         energy=min(20, state.energy + 2))
    messages = ["Advanced the seasonally simulated world"]
    if state.world_id == "topology-02" and next_state.tick >= state.observed_until:
        next_state = replace(next_state, maze_phase=(state.maze_phase + 1) % ROOM_COUNT)
        messages.append("Unwatched maze connections shifted")
    if state.world_id == "ecology-03":
        # Native ecology law: animals redirect one rainfall unit at each
        # seasonal boundary. Total rainfall always remains conserved.
        direction = _roll(state.seed, "herd:" + str(next_state.turn), 2)
        if direction == 0 and next_state.rain_east > 1:
            next_state = replace(next_state, rain_west=next_state.rain_west + 1,
                                 rain_east=next_state.rain_east - 1)
        elif direction == 1 and next_state.rain_west > 1:
            next_state = replace(next_state, rain_east=next_state.rain_east + 1,
                                 rain_west=next_state.rain_west - 1)
        messages.append("Living rain herds changed the climate balance")
    if next_state.chapter_complete and next_state.postgame:
        messages.append("Postgame ecosystems and society remain active")
    return next_state, tuple(messages)


def _validate_action(state: CampaignState, action: CampaignAction) -> None:
    if not isinstance(action, CampaignAction):
        raise CampaignError("action must be a CampaignAction")
    if action.verb not in ACTION_MECHANICS:
        raise CampaignError("action is not implemented")
    _require_int(action.amount, 1, 3, "amount")
    _require_int(action.target, -1, ROOM_COUNT - 1, "target")
    if not isinstance(action.option, str) or len(action.option) > 32:
        raise CampaignError("invalid action option")
    mechanic_id = ACTION_MECHANICS[action.verb]
    if mechanic_id is not None and (
        mechanic_id not in MECHANICS or not MECHANICS[mechanic_id].cost_specified
    ):
        raise CampaignError("action references an unverified mechanic")


def step(state: CampaignState, action: CampaignAction
         ) -> tuple[CampaignState, CampaignReceipt]:
    validate_state(state)
    _validate_action(state, action)
    if state.event_count >= MAX_EVENTS:
        raise CampaignError("bounded session event limit reached; export and restart")
    before = _digest(asdict(state))
    if action.verb == "end_turn":
        changed, messages = _advance_turn(state)
    else:
        changed, messages = _one_action(state, action)
    validate_state(changed)
    event_id = _digest({
        "schema": ENGINE_VERSION, "prior_head": state.event_head,
        "prior_state": before, "new_state": asdict(changed),
        "action": asdict(action), "messages": messages,
    })
    result = replace(changed, event_count=state.event_count + 1,
                     event_head=event_id)
    validate_state(result)
    receipt = CampaignReceipt(
        action, before, _digest(asdict(result)),
        event_id, result.event_count, messages,
    )
    return result, receipt


def replay(world_id: str, seed: str,
           actions: Iterable[CampaignAction]
           ) -> tuple[CampaignState, tuple[CampaignReceipt, ...]]:
    if not isinstance(actions, (tuple, list)) or len(actions) > MAX_EVENTS:
        raise CampaignError("actions must be bounded tuple or list")
    state = create_campaign(world_id, seed)
    events = []
    for action in actions:
        state, event = step(state, action)
        events.append(event)
    return state, tuple(events)


def export_save(state: CampaignState) -> str:
    validate_state(state)
    content = {"schema": ENGINE_VERSION, "state": asdict(state)}
    return json.dumps({"payload": content, "checksum": _digest(content)},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def import_save(serialized: str) -> CampaignState:
    if not isinstance(serialized, str) or len(serialized.encode("utf-8")) > 262144:
        raise CampaignError("oversized or invalid save")
    try:
        envelope = json.loads(serialized)
        if set(envelope) != {"payload", "checksum"}:
            raise CampaignError("save envelope invalid")
        payload = envelope["payload"]
        if payload["schema"] != ENGINE_VERSION or _digest(payload) != envelope["checksum"]:
            raise CampaignError("save version or integrity mismatch")
        raw = payload["state"]
        if set(raw) != set(CampaignState.__dataclass_fields__):
            raise CampaignError("save fields mismatch")
        raw["sectors"] = tuple(Sector(**entry) for entry in raw["sectors"])
        raw["explored"] = tuple(raw["explored"])
        raw["anchors"] = tuple(tuple(edge) for edge in raw["anchors"])
        state = CampaignState(**raw)
        validate_state(state)
        return state
    except (KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
        raise CampaignError("save validation failed") from exc
