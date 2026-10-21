"""4,500 executable original-game production recipes over existing typed Forge Studio.

Ten production domains * fifty independently authored blueprints * nine
meaningfully distinct production treatments. Every recipe invokes the
canonical project mutators to change game content and then composes genuine
additional tile geometry, NPC locations, quest paths, or environmental event
conditions. Recipes are reproducible, atomically committed by the existing
Forge Studio batch and never introduce a second project store or runtime.

The 4,500 recipes are composed production workflows, NOT 4,500 separate
game engines, asset models, or handwritten algorithms.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import math
from typing import Any

from .game_frontier_studio import (
    StudioError, StudioProject, StudioQuestStage,
)
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction
from .game_frontier_studio_biome_factory import BIOME_ACTIONS
from .game_frontier_studio_structure_factory import STRUCTURE_ACTIONS
from .game_frontier_studio_encounter_factory import ENCOUNTER_ACTIONS
from .game_frontier_studio_quest_blueprint_factory import QUEST_BLUEPRINT_ACTIONS
from .game_frontier_studio_reactive_scene_factory import REACTIVE_SCENE_ACTIONS
from .game_frontier_studio_map_edit import _name, _integer, _layer, _rectangle, _tile, _replace_layer

# Nine actual source-transforming treatments. No treatment is an alias.
TREATMENTS = (
    "waterways", "highlands", "fortified", "nightfall", "festival",
    "circuit", "secrets", "skyreach", "wilderness",
)
_DOMAINS = (
    ("realm", BIOME_ACTIONS, ("biome",)),
    ("architecture", STRUCTURE_ACTIONS, ("structure",)),
    ("population", ENCOUNTER_ACTIONS, ("encounter",)),
    ("chronicle", QUEST_BLUEPRINT_ACTIONS, ("quest",)),
    ("atmosphere", REACTIVE_SCENE_ACTIONS, ("reaction",)),
    ("settlement", BIOME_ACTIONS, ("biome", "structure")),
    ("wildland", BIOME_ACTIONS, ("biome", "encounter")),
    ("stronghold", STRUCTURE_ACTIONS, ("structure", "encounter")),
    ("expedition", ENCOUNTER_ACTIONS, ("encounter", "quest")),
    ("living_story", QUEST_BLUEPRINT_ACTIONS, ("quest", "reaction")),
)
_ACTION_TAGS = ("terrain_", "structure_", "encounter_", "quest_", "reaction_")
_ROLE_TITLES = {
    "waterways": "Find a passage along the waterways",
    "highlands": "Climb to the highland lookout",
    "fortified": "Inspect the defensive approach",
    "nightfall": "Reach the sanctuary before nightfall",
    "festival": "Meet the citizens at the celebration",
    "circuit": "Restore the abandoned mechanical circuit",
    "secrets": "Discover the overlooked passage",
    "skyreach": "Chart the route between sky islands",
    "wilderness": "Protect the remote natural crossing",
}
_ROLE_SENSOR = (
    ("water_depth_m", 1.0), ("barometric_altitude_m", 400.0),
    ("building_integrity", 0.5), ("daylight", 0.3),
    ("party_morale", 0.5), ("native_gameplay_field_force_n", 100.0),
    ("fog_visibility_m", 150.0), ("updraft_mps", 3.0),
    ("humidity", 0.65),
)


def _slug(name: str) -> str:
    for prefix in _ACTION_TAGS:
        if name.startswith(prefix):
            return name[len(prefix):]
    raise RuntimeError("source blueprint has no canonical action namespace")


def _catalog() -> tuple[str, ...]:
    rows = []
    for domain, blueprints, _ in _DOMAINS:
        if len(blueprints) != 50:
            raise RuntimeError("recipe source family must contain 50 actual blueprints")
        for blueprint in blueprints:
            for treatment in TREATMENTS:
                rows.append(f"produce_{domain}_{_slug(blueprint)}__{treatment}")
    return tuple(rows)


RECIPE_ACTIONS = _catalog()
RECIPE_INDEX = {name: i for i, name in enumerate(RECIPE_ACTIONS)}
if len(RECIPE_ACTIONS) != 4500 or len(RECIPE_INDEX) != 4500:
    raise RuntimeError("recipe catalog must have exactly 4,500 unique production tools")


def describe_recipe(action: str) -> dict[str, Any]:
    """Resolve an actual compiled multi-step workflow without source mutation."""
    if type(action) is not str or action not in RECIPE_INDEX:
        raise StudioError("unknown executable production recipe")
    number = RECIPE_INDEX[action]
    domain_number, offset = divmod(number, 450)
    blueprint_number, treatment_number = divmod(offset, 9)
    domain, blueprints, steps = _DOMAINS[domain_number]
    blueprint = blueprints[blueprint_number]
    treatment = TREATMENTS[treatment_number]
    return {
        "operation": action, "domain": domain, "source_blueprint": blueprint,
        "treatment": treatment, "recipe_steps": list(steps),
        "source_index": blueprint_number,
        "style_index": treatment_number,
        "actual_project_mutation": True,
    }


def search_recipes(*, query: str = "", domain: str = "", offset: int = 0,
                   limit: int = 32) -> dict[str, Any]:
    """Bounded, stable discovery; only matching recipe summaries are materialized."""
    if (type(query) is not str or len(query) > 96 or
            type(domain) is not str or len(domain) > 32 or
            domain and domain not in {d for d, _, _ in _DOMAINS} or
            type(offset) is not int or not 0 <= offset <= 4500 or
            type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded game production recipe search")
    text_query = query.strip().lower()
    eligible = [
        name for name in RECIPE_ACTIONS
        if (not domain or name.startswith("produce_" + domain + "_")) and
        (not text_query or text_query in name)
    ]
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": 4500, "matched": len(eligible),
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < len(eligible) else None,
        "domains": [d for d, _, _ in _DOMAINS],
        "styles": list(TREATMENTS),
        "items": [describe_recipe(name) for name in eligible[offset:offset + limit]],
    }


def _payload(args: Mapping[str, Any], recipe: str) -> dict[str, Any]:
    """Fail closed on arbitrary nested execution plans and project overwrites."""
    allowed = {
        "layer", "x", "y", "width", "height", "floor", "wall",
        "scale", "threshold", "seed", "prefab_id", "count",
        "radius", "spacing", "z", "angle_deg", "dialogue",
        "target", "quest_id", "event_id", "page_id", "priority",
        "cooldown_ms", "event_prefix",
    }
    if set(args) - allowed:
        raise StudioError("recipe accepts parameters only; arbitrary subcommands forbidden")
    params = dict(args)
    if type(params.get("seed")) is not int:
        raise StudioError("recipe needs explicit reproducible integer seed")
    _integer(params, "seed", 0, 2**63 - 1)
    for key in ("quest_id", "event_id", "page_id", "event_prefix"):
        if key not in params:
            # Name lengths remain within the canonical 128-character IDs.
            params[key] = {
                "quest_id": "q_", "event_id": "e_", "page_id": "r_",
                "event_prefix": "n_",
            }[key] + recipe.removeprefix("produce_")
        _name(params, key)
    return params


def _paint_style(project: StudioProject, args: Mapping[str, Any],
                 treatment: int) -> StudioProject:
    """Nine source-mutating geometry treatments with distinct playable layouts."""
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor, wall = _tile(layer, args, "floor"), _tile(layer, args, "wall")
    if floor == wall:
        raise StudioError("world recipe requires two distinct tile materials")
    tiles = list(layer.data)
    cx, cy = x0 + width // 2, y0 + height // 2
    def paint(x: int, y: int, value: int) -> None:
        if x0 <= x < x0 + width and y0 <= y < y0 + height:
            tiles[y * layer.width + x] = value
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            dx, dy = x - cx, y - cy
            distance = math.hypot(dx, dy)
            if treatment == 0 and abs(dx - round(math.sin(y * .8) * width * .12)) <= 1:
                paint(x, y, floor)  # real connected riverbank trail
            elif treatment == 1 and dy <= -height // 3 and abs(dx) <= width // 4:
                paint(x, y, wall)  # elevated plateau ridge
            elif treatment == 2 and (
                x in (x0 + 1, x0 + width - 2) or y in (y0 + 1, y0 + height - 2)
            ):
                paint(x, y, wall)  # enclosed fortification
            elif treatment == 3 and (x + y) % 5 == 0:
                paint(x, y, wall)  # alternate illuminated/night tiles
            elif treatment == 4 and (x % 4 == 0 or y % 4 == 0):
                paint(x, y, floor)  # accessible festival roads
            elif treatment == 5 and ((x - x0) % 3 == 0 or (y - y0) % 3 == 0):
                paint(x, y, floor)  # gridded service and circuit routes
            elif treatment == 6 and abs(dx + dy) <= 1:
                paint(x, y, floor)  # diagonal hidden passage
            elif treatment == 7 and abs(distance - min(width, height) / 3) <= 1.2:
                paint(x, y, floor)  # enclosed sky-platform ring
            elif treatment == 8 and ((x * 11 + y * 7) % 13) <= 2:
                paint(x, y, wall)  # irregular wilderness cover
    return _replace_layer(project, index, replace(layer, data=tuple(tiles)))


def _reposition_actors(project: StudioProject, origin: int, style: int,
                       count: int) -> StudioProject:
    """Nine real distinct placement policies over only freshly spawned actors."""
    placed = list(project.placements)
    if len(placed) - origin != count or count <= 0:
        raise StudioError("encounter recipe did not create its expected new actors")
    start = placed[origin]
    for j, index in enumerate(range(origin, len(placed))):
        p = placed[index]
        theta = (j + 1) * 2 * math.pi / count
        if style == 0:
            placed[index] = replace(p, x=start.x + j * 2, y=start.y + math.sin(j) * 3)
        elif style == 1:
            placed[index] = replace(p, z=p.z + j * 3)
        elif style == 2:
            placed[index] = replace(p, x=start.x + 4 * math.cos(theta),
                                    y=start.y + 4 * math.sin(theta), facing_deg=(theta*180/math.pi+180)%360)
        elif style == 3:
            placed[index] = replace(p, x=p.x + j % 2 * 2, y=p.y + j % 3 * 2)
        elif style == 4:
            placed[index] = replace(p, x=start.x + (j % 4) * 2,
                                    y=start.y + (j // 4) * 3)
        elif style == 5:
            placed[index] = replace(p, x=start.x + j % 3 * 3,
                                    y=start.y + j // 3 * 3)
        elif style == 6:
            placed[index] = replace(p, x=start.x + j * .75,
                                    y=start.y + math.sin(j*.8) * 2, z=p.z - j*.2)
        elif style == 7:
            placed[index] = replace(p, x=start.x + 8*math.cos(theta),
                                    y=start.y + 8*math.sin(theta), z=p.z + 5)
        else:
            placed[index] = replace(p, x=p.x + (j % 3 - 1) * 3, y=p.y + j % 2 * 2)
    return replace(project, placements=tuple(placed))


def _quest_detour(project: StudioProject, quest_id: str, style: int) -> StudioProject:
    """Make an actual playable alternative branch in the freshly authored quest."""
    quests = list(project.native_quests)
    index = next((i for i, q in enumerate(quests) if q.quest_id == quest_id), None)
    if index is None:
        raise StudioError("recipe quest composition did not produce native quest")
    quest = quests[index]
    root = quest.stages[0]
    end = quest.stages[-1]
    new_id = f"{quest_id}_alt_{style}"
    if len(new_id) > 128 or len(root.next_stage_ids) >= 32:
        raise StudioError("new route cannot fit the canonical native quest graph")
    if new_id in {s.stage_id for s in quest.stages}:
        raise StudioError("duplicate original quest alternative")
    new = StudioQuestStage(new_id, _ROLE_TITLES[TREATMENTS[style]],
                           (end.stage_id,))
    edited = replace(quest, stages=(replace(root, next_stage_ids=(
        *root.next_stage_ids, new_id)),) + quest.stages[1:] + (new,))
    quests[index] = edited
    return replace(project, native_quests=tuple(quests))


def _reactive_condition(project: StudioProject, page_id: str, style: int) -> StudioProject:
    """Add a third independently evaluated sensor constraint, not a label."""
    pages = list(project.environmental_pages)
    index = next((i for i, p in enumerate(pages) if p.page_id == page_id), None)
    if index is None:
        raise StudioError("recipe environmental page has not been authored")
    page = pages[index]
    signal, threshold = _ROLE_SENSOR[style]
    if len(page.conditions) >= 32:
        raise StudioError("reaction already uses maximum authored sensors")
    pages[index] = replace(page, conditions=page.conditions + (
        EnvironmentalTrigger(signal, "above", threshold),))
    return replace(project, environmental_pages=tuple(pages))


def _component_blueprint(domain_number: int, original_number: int,
                         requested: str) -> str:
    if domain_number < 5:
        action = _DOMAINS[domain_number][1][original_number]
        if requested != _DOMAINS[domain_number][2][0]:
            raise StudioError("invalid source recipe plan")
        return action
    if requested == "biome":
        return BIOME_ACTIONS[original_number]
    if requested == "structure":
        return STRUCTURE_ACTIONS[original_number]
    if requested == "encounter":
        return ENCOUNTER_ACTIONS[original_number]
    if requested == "quest":
        return QUEST_BLUEPRINT_ACTIONS[original_number]
    if requested == "reaction":
        return REACTIVE_SCENE_ACTIONS[original_number]
    raise StudioError("invalid authoritative recipe component")


def edit_recipe(project: StudioProject, operation: str, args: Mapping[str, Any],
                perform: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject]) -> StudioProject:
    """Execute real, source-bound multi-step original-game production recipe.

    perform MUST be the canonical execute_authoring function, not model input.
    Every sub-operation is one existing, already registered game-authoring
    primitive, and each intermediate object is a validated StudioProject.
    """
    if (not isinstance(project, StudioProject) or
            type(operation) is not str or operation not in RECIPE_INDEX or
            not isinstance(args, Mapping) or not callable(perform)):
        raise StudioError("unknown or untrusted original-game producer")
    meta = describe_recipe(operation)
    domain_number = RECIPE_INDEX[operation] // 450
    source_number = meta["source_index"]
    style = meta["style_index"]
    params = _payload(args, operation)
    draft = project
    for component in meta["recipe_steps"]:
        blueprint = _component_blueprint(domain_number, source_number, component)
        before = len(draft.placements)
        source_args: dict[str, Any]
        if component in ("biome", "structure"):
            source_args = {k: params[k] for k in (
                "layer", "x", "y", "width", "height", "floor", "wall", "seed")}
            if component == "biome":
                source_args["scale"] = params.get("scale", 5)
                source_args["threshold"] = params.get("threshold", .53)
        elif component == "encounter":
            source_args = {k: params[k] for k in (
                "prefab_id", "count", "x", "y", "z", "radius", "spacing", "seed")}
            source_args.update(event_prefix=params["event_prefix"])
            if "dialogue" in params:
                source_args["dialogue"] = params["dialogue"]
        elif component == "quest":
            source_args = {"quest_id": params["quest_id"],
                           "event_id": params["event_id"]}
            if "target" in params:
                source_args["target"] = params["target"]
        else:
            source_args = {"page_id": params["page_id"],
                           "priority": params.get("priority", 0),
                           "cooldown_ms": params.get("cooldown_ms", 0)}
        draft = perform(draft, blueprint, source_args)
        if component == "encounter":
            draft = _reposition_actors(draft, before, style, params["count"])
        elif component == "quest":
            draft = _quest_detour(draft, params["quest_id"], style)
        elif component == "reaction":
            draft = _reactive_condition(draft, params["page_id"], style)
        elif component in ("biome", "structure"):
            draft = _paint_style(draft, params, style)
    return draft
