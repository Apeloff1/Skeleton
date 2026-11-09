"""45,000 executable cross-system Forge Studio production expansions.

Ten genuinely distinct authored gameplay systems compose with every one of
the 4,500 existing source-mutating recipes. An expansion first executes its
exact base recipe, then authors bounded world tile geometry and a concrete
RPGEventPage with two independently evaluated environmental/quest sensors.
Selected systems additionally move newly created actors or extend a newly
created quest, without modifying unrelated existing actors or canon.

45,000 is the number of composed editable production contracts, NOT the number
of independent handwritten game engines. Immutable StudioProject remains sole
ownership, and all results pass its existing versioned save/native compiler.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject, StudioQuestStage
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction, RPGEventPage
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_production_recipes import (
    RECIPE_ACTIONS, RECIPE_INDEX, TREATMENTS, describe_recipe,
)

GAMEPLAY_LAYERS = (
    "wayfinding", "seasons", "destructibles", "weather",
    "combat", "commerce", "stealth", "verticality",
    "migration", "story_convergence",
)
# Every system contains two REAL sensor predicates and a canonical game
# action proposal, evaluated by the existing deterministic RPG event runtime.
_LAYER_EFFECTS = (
    ("compass_heading_deg", "at_least", 90., "fog_visibility_m", "below", 250.,
     "inspect_instrument", "ui", "compass", "pathway"),
    ("temperature_c", "below", 5., "ground_ice_fraction", "above", .3,
     "change_light", "environment", "seasonal", "winter"),
    ("collision_energy_j", "above", 120., "building_integrity", "below", .6,
     "trigger_impact_fx", "environment", "breakable_cover", "fracture"),
    ("wind_mps", "above", 12., "rain_mm_h", "above", 3.,
     "weather_transition", "environment", "local_weather", "storm"),
    ("native_contact_count", "above", 0., "party_morale", "below", .8,
     "start_combat", "character", "encounter", "engage"),
    ("npc_reputation", "above", 10., "quest_progress", "at_least", .1,
     "open_shop", "character", "merchant", "trade"),
    ("sound_occlusion", "above", .55, "daylight", "below", .4,
     "set_flag", "world", "hidden_route", "true"),
    ("updraft_mps", "above", 4., "sky_island_height_m", "above", 150.,
     "apply_gameplay_effect", "character", "traveler", "aerial_lift"),
    ("humidity", "above", .6, "party_morale", "above", .4,
     "trigger_foliage_fx", "environment", "habitat", "migration"),
    ("quest_progress", "at_least", .75, "npc_reputation", "above", 0.,
     "advance_quest", "quest", "active_story", "convergence"),
)
_SCENE_OBJECTIVES = (
    "Read the surveyed compass bearing before continuing",
    "Follow the seasonal signs across the region",
    "Clear or bypass the unstable structure",
    "Reach the storm shelter before conditions worsen",
    "Resolve the encounter using the selected faction strategy",
    "Find the merchant and negotiate a safe supply route",
    "Discover the concealed route without raising an alarm",
    "Reach the elevated crossing with the available lift",
    "Observe the migration without disturbing the wildlife",
    "Bring the plot threads together at the final meeting",
)
if len(GAMEPLAY_LAYERS) != 10 or len(set(GAMEPLAY_LAYERS)) != 10:
    raise RuntimeError("ten distinct executable gameplay expansion systems required")


# Deliberately 45,000 distinct stable names. The base index and layer suffix
# reconstruct an exact, owned composition plan; user input cannot insert code.
EXPANDED_RECIPE_ACTIONS = tuple(
    "expand_" + base.removeprefix("produce_") + "___" + layer
    for base in RECIPE_ACTIONS for layer in GAMEPLAY_LAYERS
)
EXPANDED_RECIPE_INDEX = {name: i for i, name in enumerate(EXPANDED_RECIPE_ACTIONS)}
if len(EXPANDED_RECIPE_ACTIONS) != 45000 or len(EXPANDED_RECIPE_INDEX) != 45000:
    raise RuntimeError("45,000 distinct playable source-editing expansions required")


def describe_expansion(action: str) -> dict[str, Any]:
    if type(action) is not str or action not in EXPANDED_RECIPE_INDEX:
        raise StudioError("unknown original-game production expansion")
    index = EXPANDED_RECIPE_INDEX[action]
    recipe_number, layer_number = divmod(index, 10)
    original = RECIPE_ACTIONS[recipe_number]
    base = describe_recipe(original)
    return {
        **base,
        "operation": action, "base_operation": original,
        "system_layer": GAMEPLAY_LAYERS[layer_number],
        "system_layer_index": layer_number,
        "recipe_steps": base["recipe_steps"] + ["world_gameplay_" + GAMEPLAY_LAYERS[layer_number]],
        "actual_project_mutation": True,
        "cross_system_source_edits": ["map_tiles", "environmental_page"],
    }


def search_expansions(*, query: str = "", domain: str = "",
                      system_layer: str = "", offset: int = 0,
                      limit: int = 32) -> dict[str, Any]:
    """Stable index search, never serialize 45,000 commands on inspection."""
    if (type(query) is not str or len(query) > 96 or
            type(domain) is not str or len(domain) > 32 or
            type(system_layer) is not str or len(system_layer) > 32 or
            domain and domain not in (
                "realm", "architecture", "population", "chronicle",
                "atmosphere", "settlement", "wildland", "stronghold",
                "expedition", "living_story",
            ) or
            system_layer and system_layer not in GAMEPLAY_LAYERS or
            type(offset) is not int or not 0 <= offset <= 45000 or
            type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded 50,000-tool catalog request")
    q = query.strip().lower()
    names = (
        name for name in EXPANDED_RECIPE_ACTIONS
        if (not domain or name.startswith("expand_" + domain + "_")) and
        (not system_layer or name.endswith("___" + system_layer)) and
        (not q or q in name)
    )
    # Avoid materializing the descriptions for every matched recipe.
    matching = 0
    page = []
    for name in names:
        if offset <= matching < offset + limit:
            page.append(describe_expansion(name))
        matching += 1
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": 45000, "matched": matching,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matching else None,
        "domains": [
            "realm", "architecture", "population", "chronicle",
            "atmosphere", "settlement", "wildland", "stronghold",
            "expedition", "living_story",
        ],
        "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS),
        "items": page,
    }


def _overlay_tiles(project: StudioProject, args: Mapping[str, Any],
                   layer_number: int) -> StudioProject:
    """Ten bounded spatial constructions; uses 2D source tile indices."""
    index, map_layer = _layer(project, args)
    x0, y0, w, h = _rectangle(map_layer, args)
    floor = _tile(map_layer, args, "floor")
    wall = _tile(map_layer, args, "wall")
    if floor == wall:
        raise StudioError("gameplay overlay requires distinct authored floor and wall")
    seed = args.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioError("gameplay overlay requires a deterministic integer seed")
    data = list(map_layer.data)
    cx, cy = x0 + (w - 1) / 2, y0 + (h - 1) / 2
    rad = max(1.0, min(w, h) / 3)
    for y in range(y0, y0+h):
        for x in range(x0, x0+w):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            mark = False
            value = floor
            if layer_number == 0:
                mark = abs(dx) <= 1 or (y == int(cy) and abs(dx) <= w // 2)
            elif layer_number == 1:
                mark = (x + y + seed % 7) % 6 in (0, 1)
                value = wall
            elif layer_number == 2:
                mark = (x * 7 + y * 11 + seed % 13) % 17 in (0, 1, 2)
                value = wall
            elif layer_number == 3:
                mark = (y == int(cy)) or (abs(dx) <= 2 and abs(dy) <= 2)
            elif layer_number == 4:
                mark = abs(dist - rad) <= 1 or (abs(dx) <= 1 and abs(dy) <= 1)
                value = wall
            elif layer_number == 5:
                mark = (x-x0) % 4 == 0 or (y-y0) % 4 == 0
            elif layer_number == 6:
                mark = abs(dx + dy) <= 1 or abs(dx - dy) <= 1
            elif layer_number == 7:
                mark = abs(dist-rad) <= 1.0 or abs(dx) <= 1
            elif layer_number == 8:
                mark = abs(dy - 2 * math.sin(dx / 3)) <= 1.1
            else:
                mark = (abs(dx) <= 2 and abs(dy) <= 2) or (
                    (x+y+seed % 5) % 9 == 0
                )
                value = wall
            if mark:
                data[y * map_layer.width + x] = value
    return _replace_layer(project, index, replace(map_layer, data=tuple(data)))


def _overlay_page(project: StudioProject, operation: str,
                  args: Mapping[str, Any], layer_number: int) -> StudioProject:
    base_id = operation.replace("expand_", "xp_", 1).replace("___", "_")
    instance = args.get("instance_id", "a")
    if (type(instance) is not str or not 1 <= len(instance) <= 16 or
            not (instance[0].isalpha() and
                 all(c.isalnum() or c == "_" for c in instance))):
        raise StudioError("overlay instance needs stable bounded identity")
    ident = base_id + "_" + instance
    if len(ident) > 128:
        raise StudioError("gameplay event identity exceeds stable source limit")
    if ident in {x.page_id for x in project.environmental_pages} | {
        x.event_id for x in project.events
    }:
        raise StudioError("expansion event identity already used in project")
    (signal1, comp1, threshold1, signal2, comp2, threshold2,
     kind, channel, target, value) = _LAYER_EFFECTS[layer_number]
    conditions = (
        EnvironmentalTrigger(signal1, comp1, threshold1),
        EnvironmentalTrigger(signal2, comp2, threshold2),
    )
    event = RPGEventPage(
        ident, 10 + layer_number, conditions,
        (RPGEventAction(kind, channel, target, value),),
        cooldown_ms=1000 * (layer_number + 1),
    )
    return replace(project, environmental_pages=project.environmental_pages + (event,))


def _overlay_cast(project: StudioProject, original_actor_count: int,
                  layer_number: int) -> StudioProject:
    """Affect only actors created by this recipe, never existing source cast."""
    if len(project.placements) <= original_actor_count:
        return project
    placements = list(project.placements)
    for idx in range(original_actor_count, len(placements)):
        p = placements[idx]
        ordinal = idx-original_actor_count
        if layer_number == 0:
            placements[idx] = replace(p, facing_deg=90.)
        elif layer_number == 1:
            placements[idx] = replace(p, z=p.z+ordinal*.5)
        elif layer_number == 2:
            placements[idx] = replace(p, facing_deg=(p.facing_deg+180)%360)
        elif layer_number == 3:
            placements[idx] = replace(p, x=p.x+2*math.sin(ordinal))
        elif layer_number == 4:
            placements[idx] = replace(p, facing_deg=(ordinal*45)%360)
        elif layer_number == 5:
            placements[idx] = replace(p, x=p.x+ordinal*1.5)
        elif layer_number == 6:
            placements[idx] = replace(p, y=p.y+ordinal*1.7)
        elif layer_number == 7:
            placements[idx] = replace(p, z=p.z+4+ordinal*.2)
        elif layer_number == 8:
            placements[idx] = replace(p, x=p.x+ordinal, y=p.y+ordinal*.5)
        else:
            placements[idx] = replace(p, facing_deg=(p.facing_deg+90)%360)
    return replace(project, placements=tuple(placements))


def _overlay_story(project: StudioProject, original_quest_count: int,
                   layer_number: int) -> StudioProject:
    """Append a real reachable playable stage to newly generated quest only."""
    if len(project.native_quests) <= original_quest_count:
        return project
    quests = list(project.native_quests)
    for i in range(original_quest_count, len(quests)):
        q = quests[i]
        entry = q.stages[0]
        ident = f"{q.quest_id}_gameplay_{layer_number}"
        if len(ident) > 128 or ident in {s.stage_id for s in q.stages}:
            raise StudioError("overlay quest stage identity collision")
        if len(entry.next_stage_ids) >= 32:
            raise StudioError("quest has no room for a newly playable side route")
        terminal = next((s.stage_id for s in reversed(q.stages) if not s.next_stage_ids), None)
        if not terminal:
            raise StudioError("quest expansion requires a valid reachable ending")
        stage = StudioQuestStage(
            ident, _SCENE_OBJECTIVES[layer_number], (terminal,))
        next_entry = replace(entry, next_stage_ids=entry.next_stage_ids + (ident,))
        quests[i] = replace(q, stages=(next_entry, *q.stages[1:], stage))
    return replace(project, native_quests=tuple(quests))


def edit_expansion(
    project: StudioProject, operation: str, args: Mapping[str, Any],
    perform: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject],
) -> StudioProject:
    """Transactional source transformation: base game recipe + real gameplay."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
            or operation not in EXPANDED_RECIPE_INDEX
            or not isinstance(args, Mapping) or not callable(perform)):
        raise StudioError("unknown original-game production expansion")
    number = EXPANDED_RECIPE_INDEX[operation]
    base_number, layer_number = divmod(number, 10)
    actor_count, quest_count = len(project.placements), len(project.native_quests)
    base = RECIPE_ACTIONS[base_number]
    # Existing recipe owns blueprint composition and source ID semantics.
    candidate = perform(project, base, args)
    candidate = _overlay_tiles(candidate, args, layer_number)
    candidate = _overlay_page(candidate, operation, args, layer_number)
    candidate = _overlay_cast(candidate, actor_count, layer_number)
    candidate = _overlay_story(candidate, quest_count, layer_number)
    return candidate
