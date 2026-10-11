"""Era and invented-theology mechanics for a bounded playable original world.

This layer executes distinct resource-backed technology and ritual choices.
All 40 eras map to explicit tech capabilities. Twenty-four cosmology models
select permitted theological actions; no claim of 24 implemented religions,
scientific hyperrealism or finished graphics is made.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_world_campaign import (
    CampaignAction, CampaignError, CampaignState, create_campaign,
    export_save, import_save, step, validate_state,
)
from .world_styling import ERAS, THEOLOGIES, WorldStyling

SCHEMA = "original-styled-world.v1"
ERA_LEVELS = {
    "primordial-earth": 0, "early-life": 0, "paleolithic": 0,
    "mesolithic": 0, "neolithic": 1, "copper-age": 1,
    "bronze-age": 1, "iron-age": 2, "classical-antiquity": 2,
    "late-antiquity": 2, "early-medieval": 2, "high-medieval": 2,
    "late-medieval": 2, "renaissance": 3, "early-modern": 3,
    "age-of-sail": 3, "enlightenment": 3, "early-industrial": 4,
    "steam-age": 4, "electrical-age": 5, "early-20c": 5,
    "interwar": 5, "mid-20c": 5, "space-age": 6,
    "microcomputer": 6, "digital-network": 6, "early-ai": 6,
    "near-future": 7, "post-scarcity": 8, "solarpunk": 7,
    "dieselpunk": 4, "clockpunk": 3, "atompunk": 6,
    "biopunk": 7, "nanotech-age": 8,
    "interplanetary": 8, "interstellar": 8,
    "posthuman": 8, "deep-future": 8, "cosmic-epoch": 8,
}
TECH_ACTIONS = {
    "knap": 0, "cultivate": 1, "smelt": 2,
    "watermill": 3, "steamworks": 4, "power_grid": 5,
    "automation": 6, "survey_drone": 6,
    "adaptive_habitat": 7, "terraform": 8,
}
RITUAL_ACTIONS = frozenset({
    "reflection", "communal_rite", "ancestor_memory",
    "weather_invocation", "covenant", "oracle",
})
# Capability groups are deliberately separate from religious identities.
# All models support voluntary reflection, but not all permit supernatural
# interventions or ancestor communication. These are INVENTED world rules.
THEOLOGY_ACTIONS = {
    "none": ("reflection", "communal_rite"),
    "secular-material": ("reflection", "communal_rite"),
    "atheist-world": ("reflection", "communal_rite"),
    "agnostic-open": ("reflection", "communal_rite", "oracle"),
    "monotheistic-invented": ("reflection", "communal_rite", "covenant"),
    "polytheistic-invented": ("reflection", "communal_rite", "weather_invocation"),
    "dualistic-invented": ("reflection", "communal_rite", "covenant"),
    "animist-invented": ("reflection", "communal_rite", "weather_invocation"),
    "ancestor-veneration": ("reflection", "communal_rite", "ancestor_memory"),
    "deistic-invented": ("reflection", "communal_rite"),
    "pantheistic-invented": ("reflection", "communal_rite", "weather_invocation"),
    "panentheistic-invented": ("reflection", "communal_rite", "covenant"),
    "non-theistic-spiritual": ("reflection", "communal_rite", "ancestor_memory"),
    "nature-sacred": ("reflection", "communal_rite", "weather_invocation"),
    "cosmic-mythic": ("reflection", "communal_rite", "oracle"),
    "ritual-mechanical": ("reflection", "communal_rite", "weather_invocation"),
    "oracular": ("reflection", "communal_rite", "oracle"),
    "syncretic-invented": ("reflection", "communal_rite", "ancestor_memory", "covenant"),
    "theological-pluralism": ("reflection", "communal_rite", "covenant", "ancestor_memory"),
    "divinity-evolving": ("reflection", "communal_rite", "oracle", "weather_invocation"),
    "faith-as-power": ("reflection", "communal_rite", "weather_invocation", "covenant"),
    "belief-ineffective": ("reflection", "communal_rite"),
    "post-divine": ("reflection", "communal_rite", "ancestor_memory"),
    "machine-sacred": ("reflection", "communal_rite", "oracle"),
}
if set(ERA_LEVELS) != set(ERAS) or set(THEOLOGY_ACTIONS) != set(THEOLOGIES):
    raise RuntimeError("era and theology compiler catalogs differ from styling registry")


@dataclass(frozen=True)
class StyledAction:
    verb: str
    amount: int = 1
    option: str = ""


@dataclass(frozen=True)
class StyledState:
    world: CampaignState
    styling: WorldStyling
    metal: int = 0
    machinery: int = 0
    grid_power: int = 0
    robots: int = 0
    probes: int = 0
    devotion: int = 0
    heritage: int = 0
    visions: int = 0
    loops: int = 0
    events: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class StyledReceipt:
    verb: str
    event_id: str
    number: int
    effects: tuple[str, ...]


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def validate_styled(state: StyledState) -> None:
    if not isinstance(state, StyledState) or not isinstance(state.styling, WorldStyling):
        raise CampaignError("invalid styled world type")
    validate_state(state.world)
    for name in ("metal", "machinery", "grid_power", "robots", "probes",
                 "devotion", "heritage", "visions", "loops", "events"):
        val = getattr(state, name)
        if type(val) is not int or not 0 <= val <= 10000:
            raise CampaignError("invalid styled world resource: " + name)
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64
            or any(c not in "0123456789abcdef" for c in state.event_head)):
        raise CampaignError("invalid styled event digest")


def create_styled_world(
    world_id: str, seed: str = "era-world", styling: WorldStyling | None = None,
) -> StyledState:
    setting = styling if styling is not None else WorldStyling()
    if not isinstance(setting, WorldStyling):
        raise CampaignError("unknown styling")
    if setting.era in {"primordial-earth", "early-life"} and world_id == "civilization-01":
        raise CampaignError("prehuman era cannot host a historical human civic law")
    state = StyledState(create_campaign(world_id, seed), setting)
    validate_styled(state)
    return state


def _spend(world: CampaignState, **costs: int) -> CampaignState:
    updates = {}
    for name, amount in costs.items():
        if getattr(world, name) < amount:
            raise CampaignError("insufficient " + name)
        updates[name] = getattr(world, name) - amount
    return replace(world, **updates)


def _tile(world: CampaignState, **changes: object) -> CampaignState:
    tiles = list(world.sectors)
    tiles[world.position] = replace(tiles[world.position], **changes)
    return replace(world, sectors=tuple(tiles))


def _styled_effect(state: StyledState, action: StyledAction
                   ) -> tuple[StyledState, tuple[str, ...]]:
    verb, n = action.verb, action.amount
    if type(n) is not int or not 1 <= n <= 3:
        raise CampaignError("styled actions require quantity 1..3")
    if action.option:
        raise CampaignError("styled action has no option field")
    world = state.world
    if world.action_points < 1:
        raise CampaignError("no player actions remain")
    world = replace(world, action_points=world.action_points - 1)
    effects = []
    if verb in TECH_ACTIONS:
        tier = ERA_LEVELS[state.styling.era]
        if tier < TECH_ACTIONS[verb]:
            raise CampaignError("technology is unavailable in this era")
        if verb == "knap":
            world = _spend(world, stone=n, wood=n)
            world = replace(world, tools=min(10000, world.tools + n))
            effects.append("Produced physical stone/wood tools")
        elif verb == "cultivate":
            world = _spend(world, seeds=n, water=n)
            tile = world.sectors[world.position]
            world = _tile(world, crop=min(100, tile.crop + n))
            effects.append("Established agricultural plantings")
        elif verb == "smelt":
            world = _spend(world, wood=2 * n, stone=n)
            state = replace(state, metal=state.metal + n)
            tile = world.sectors[world.position]
            world = _tile(world, contamination=min(100, tile.contamination + n))
            effects.append("Produced metal at measurable pollution cost")
        elif verb == "watermill":
            world = _spend(world, wood=2 * n, stone=2 * n)
            state = replace(state, machinery=state.machinery + n)
            effects.append("Constructed a water-powered mechanical device")
        elif verb == "steamworks":
            if state.metal < n:
                raise CampaignError("steamworks requires refined metal")
            world = _spend(world, wood=n)
            state = replace(state, metal=state.metal - n,
                            machinery=state.machinery + 2 * n)
            effects.append("Converted forged material into steam-era machines")
        elif verb == "power_grid":
            if state.metal < 2 * n:
                raise CampaignError("electrical grid requires sufficient metal")
            world = _spend(world, coins=2 * n)
            state = replace(state, metal=state.metal - 2 * n,
                            grid_power=min(10000, state.grid_power + 3 * n))
            effects.append("Built finite electrical storage and distribution")
        elif verb == "automation":
            if state.metal < n or state.grid_power < n:
                raise CampaignError("robot assembly requires metal and power")
            world = _spend(world, knowledge=n)
            state = replace(state, metal=state.metal - n,
                            grid_power=state.grid_power - n,
                            robots=state.robots + n)
            effects.append("Deployed bounded resource-consuming automation")
        elif verb == "survey_drone":
            if state.grid_power < n or state.robots < n:
                raise CampaignError("drone requires robots and stored power")
            state = replace(state, grid_power=state.grid_power - n,
                            probes=state.probes + n)
            effects.append("Launched persistent exploration drones")
        elif verb == "adaptive_habitat":
            if state.metal < n or state.machinery < n:
                raise CampaignError("advanced shelter requires metal and machinery")
            world = _spend(world, wood=n)
            state = replace(state, metal=state.metal - n,
                            machinery=state.machinery - n)
            world = replace(world, health=min(20, world.health + n * 2))
            effects.append("Constructed an adaptive protective habitat")
        elif verb == "terraform":
            if state.grid_power < 2 * n or state.metal < n:
                raise CampaignError("terraforming needs energy and materials")
            world = _spend(world, water=n)
            tile = world.sectors[world.position]
            world = _tile(world, fertility=min(100, tile.fertility + 2 * n))
            state = replace(state, grid_power=state.grid_power - 2 * n,
                            metal=state.metal - n)
            effects.append("Modified a local habitat within bounded resources")
    elif verb in RITUAL_ACTIONS:
        if verb not in THEOLOGY_ACTIONS[state.styling.theology]:
            raise CampaignError("cosmology does not permit that ritual action")
        if verb == "reflection":
            world = _spend(world, energy=n)
            world = replace(world, knowledge=min(100, world.knowledge + n))
            effects.append("Practiced introspection without supernatural claims")
        elif verb == "communal_rite":
            world = _spend(world, food=n)
            world = replace(world, trust=min(100, world.trust + n * 2))
            state = replace(state, devotion=state.devotion + n)
            effects.append("Shared ritual built collective social trust")
        elif verb == "ancestor_memory":
            world = _spend(world, knowledge=n, food=n)
            world = replace(world, trust=min(100, world.trust + n))
            state = replace(state, heritage=state.heritage + n)
            effects.append("Stewarded remembered generations through public care")
        elif verb == "weather_invocation":
            world = _spend(world, food=n, water=n)
            if world.rain_east < n:
                raise CampaignError("insufficient moisture for symbolic rain transfer")
            world = replace(world, rain_east=world.rain_east - n,
                            rain_west=world.rain_west + n)
            state = replace(state, devotion=state.devotion + n)
            effects.append("Original cosmological law transferred existing rainfall")
        elif verb == "covenant":
            if world.promises + n > 12:
                raise CampaignError("civic oath capacity reached")
            world = _spend(world, coins=n)
            world = replace(world, promises=world.promises + n)
            state = replace(state, devotion=state.devotion + n)
            effects.append("Created a costly revocable civic covenant")
        elif verb == "oracle":
            world = _spend(world, knowledge=n)
            state = replace(state, visions=state.visions + n)
            effects.append("Received fallible speculative future information")
    else:
        raise CampaignError("unimplemented era or theology action")
    return replace(state, world=world), tuple(effects)


def styled_step(state: StyledState, action: CampaignAction | StyledAction
                ) -> tuple[StyledState, StyledReceipt]:
    validate_styled(state)
    if state.events >= 10000:
        raise CampaignError("styled event budget exhausted")
    effects: tuple[str, ...]
    if isinstance(action, CampaignAction):
        world, receipt = step(state.world, action)
        effects = receipt.messages
        state_new = replace(state, world=world)
        if action.verb == "end_turn":
            # Comfortable play can reduce stress without erasing resource
            # scarcity; difficult settings may heighten sustained hunger.
            if state.styling.comfort >= 85:
                world = replace(world, hunger=max(0, world.hunger - 1))
            elif state.styling.comfort <= 15:
                world = replace(world, hunger=min(20, world.hunger + 1))
            if state.robots and state.grid_power:
                tile = world.sectors[world.position]
                amount = min(state.robots, tile.food, state.grid_power, 3)
                if amount:
                    world = _tile(world, food=tile.food - amount)
                    world = replace(world, food=world.food + amount)
                    state_new = replace(state_new, grid_power=state.grid_power - amount)
                    effects += ("Automated harvest consumed local food and grid energy",)
            if (state.styling.chronology in {"time-loop", "cyclical-time"}
                    and world.tick % 8 == 0):
                state_new = replace(state_new, loops=state.loops + 1)
                world = replace(world, maze_phase=0)
                effects += ("Cyclical world reset its transient maze phase",)
            state_new = replace(state_new, world=world)
    elif isinstance(action, StyledAction):
        state_new, effects = _styled_effect(state, action)
    else:
        raise CampaignError("invalid styled action type")
    evidence = _digest({
        "schema": SCHEMA, "prior_head": state.event_head,
        "prior_state": asdict(state),
        "next_state": asdict(state_new),
        "action": asdict(action), "effects": effects,
    })
    next_state = replace(state_new, events=state.events + 1,
                         event_head=evidence)
    validate_styled(next_state)
    return next_state, StyledReceipt(
        action.verb, evidence, next_state.events, effects,
    )


def styled_save(state: StyledState) -> str:
    validate_styled(state)
    payload = {
        "schema": SCHEMA, "world": json.loads(export_save(state.world)),
        "styling": state.styling.as_dict(),
        "extras": {key: getattr(state, key) for key in (
            "metal", "machinery", "grid_power", "robots", "probes",
            "devotion", "heritage", "visions", "loops", "events", "event_head",
        )},
    }
    return json.dumps({"payload": payload, "checksum": _digest(payload)},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def styled_restore(text: str) -> StyledState:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 524288:
        raise CampaignError("oversized or invalid styled world save")
    try:
        document = json.loads(text)
        if set(document) != {"payload", "checksum"}:
            raise CampaignError("unrecognized save envelope")
        payload = document["payload"]
        if payload["schema"] != SCHEMA or _digest(payload) != document["checksum"]:
            raise CampaignError("save identity mismatch")
        if set(payload) != {"schema", "world", "styling", "extras"}:
            raise CampaignError("invalid save fields")
        world = import_save(json.dumps(payload["world"]))
        styling = WorldStyling(**{
            **payload["styling"],
            "themes": tuple(payload["styling"]["themes"]),
        })
        extra = payload["extras"]
        if set(extra) != set(StyledState.__dataclass_fields__) - {"world", "styling"}:
            raise CampaignError("invalid styled save resources")
        state = StyledState(world, styling, **extra)
        validate_styled(state)
        return state
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise CampaignError("styled world save validation failed") from exc
