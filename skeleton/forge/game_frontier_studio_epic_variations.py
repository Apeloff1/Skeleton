"""Epic Variation authoring: ten original, layered, canon-preserving world patterns.

45 trillion reversible names compose 4.5T existing saga actions with ten
independent production modes. These are project-source combinations, NOT
independently manufactured games, graphics, or 45T native-world installations.

Each transaction executes a real Saga edit, paints up to eight explicitly
selected bounded tile layers, authors a separate evidence-gated RPG event
page, stages only newly created actors and adds new-only quest paths.
The existing Forge host alone owns CAS, persistence and runtime authority.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject, StudioQuestStage
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction
from .game_frontier_studio_campaign_production import _page
from .game_frontier_studio_saga_production import (
    SAGA_ACTIONS, SAGAS, describe_saga,
)
from .game_frontier_studio_epoch_production import EPOCHS
from .game_frontier_studio_chronicle_production import CHRONICLES
from .game_frontier_studio_campaign_production import CAMPAIGNS
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

EPICS = (
    "continental_odyssey", "sky_archipelago_empire", "abyssal_ocean_frontier",
    "megacity_civilization", "underworld_labyrinth", "living_world_ecosystems",
    "grand_siege_theater", "dimensional_crossroads", "dynasty_of_eras",
    "cosmic_finale",
)
OBJECTIVES = (
    "Create continental travel spines with braided alternatives and trade hubs",
    "Interconnect floating-island landings, updraft lanes and return crossings",
    "Build deep-water shelf routes, island refuges and safe inland transfers",
    "Author concentric metropolitan districts, diagonals and civic spokes",
    "Weave subterranean routes, deliberate dead ends and discoverable bypasses",
    "Link habitat corridors with river-basin routes and seasonal refuges",
    "Author siege lines, flanking alternatives and evacuating civilian paths",
    "Join several world quadrants through reversible threshold crossings",
    "Compose historical and future route echoes without rewriting old scenes",
    "Bring independent story paths into a replayable finale with three exits",
)
# Observation-gated proposals, never executed by this source authoring code.
EVENTS = (
    ("barometric_altitude_m", "above", 150., "quest_progress", "above", .25,
     "world_portal", "navigation", "continental_waypoint", "charted"),
    ("updraft_mps", "above", 2.5, "sky_island_height_m", "above", 140.,
     "world_portal", "navigation", "sky_empire_route", "enabled"),
    ("water_depth_m", "above", 1.2, "tide_height_m", "above", .45,
     "inspect_instrument", "ui", "abyssal_sounding", "recorded"),
    ("building_integrity", "below", .9, "npc_reputation", "above", 12.,
     "set_flag", "world", "megacity_rebuild", "candidate"),
    ("fog_visibility_m", "below", 220., "compass_heading_deg", "above", 80.,
     "show_dialogue", "character", "underworld_scout", "direction"),
    ("humidity", "above", .6, "soil_wetness", "above", .45,
     "trigger_foliage_fx", "environment", "epic_habitat", "restoration"),
    ("native_contact_count", "above", 3., "party_morale", "above", .35,
     "show_dialogue", "character", "siege_defender", "fallback"),
    ("solar_height", "below", 8., "moon_phase", "above", .65,
     "world_portal", "navigation", "dimensional_gateway", "candidate"),
    ("quest_progress", "above", .75, "npc_reputation", "above", 20.,
     "advance_quest", "quest", "dynasty_turn", "choice"),
    ("quest_progress", "at_least", .95, "party_morale", "above", .6,
     "advance_quest", "quest", "cosmic_finale", "choice"),
)
if len(EPICS) != 10 or len(set(EPICS)) != 10 or len(EVENTS) != 10:
    raise RuntimeError("ten unique epic production variants required")


class EpicActions(Sequence[str]):
    """O(1) rank/unrank and membership; no trillion-element allocation."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(SAGA_ACTIONS) * 10

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("epic operation rank must be a real integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("epic operation rank outside declared catalogue")
        parent, axis = divmod(index, 10)
        return ("epic_" + SAGA_ACTIONS[parent].removeprefix("saga_")
                + "____________" + EPICS[axis])

    def __contains__(self, operation: object) -> bool:
        if type(operation) is not str or not operation.startswith("epic_"):
            return False
        parent, delim, axis = operation[len("epic_"):].rpartition("____________")
        return bool(delim and axis in EPICS and "saga_" + parent in SAGA_ACTIONS)

    def __iter__(self):
        for base in SAGA_ACTIONS:
            prefix = "epic_" + base.removeprefix("saga_") + "____________"
            for epic in EPICS:
                yield prefix + epic


EPIC_ACTIONS = EpicActions()
if len(EPIC_ACTIONS) != 45_000_000_000_000:
    raise RuntimeError("Epic source variations must index 45 trillion")


def parent_action(operation: str) -> tuple[str, int]:
    if operation not in EPIC_ACTIONS:
        raise StudioError("unknown exact epic variation source")
    stem, _, name = operation[len("epic_"):].rpartition("____________")
    return "saga_" + stem, EPICS.index(name)


def describe_epic(operation: str) -> dict[str, Any]:
    parent, axis = parent_action(operation)
    return {
        **describe_saga(parent),
        "operation": operation, "base_operation": parent,
        "epic": EPICS[axis], "epic_index": axis, "epic_objective": OBJECTIVES[axis],
        "source_outputs": [
            "bounded_multilayer_topology",
            "independent_observed_game_event",
            "new_only_actor_facing_and_altitude",
            "new_only_optional_native_quest_route",
        ],
        "actual_project_mutation": True,
    }


def search_epics(*, domain: str = "", system_layer: str = "",
                 director: str = "", finish: str = "",
                 worldline: str = "", phase: str = "", campaign: str = "",
                 chronicle: str = "", epoch: str = "", saga: str = "",
                 epic: str = "", offset: int = 0, limit: int = 32
                 ) -> dict[str, Any]:
    """Page directly from exact selected mixed-radix ranks in O(page)."""
    values = (domain, system_layer, director, finish, worldline, phase,
              campaign, chronicle, epoch, saga, epic)
    catalogues = (tuple(d[0] for d in _DOMAINS), GAMEPLAY_LAYERS,
                  DIRECTORS, FINISHES, WORLDLINES, PHASES, CAMPAIGNS,
                  CHRONICLES, EPOCHS, SAGAS, EPICS)
    if (any(type(s) is not str or len(s) > 40 or (s and s not in names)
            for s, names in zip(values, catalogues))
            or type(offset) is not int or not 0 <= offset <= len(EPIC_ACTIONS)
            or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid indexed Epic Variation search")
    chosen = tuple(tuple(i for i, token in enumerate(names)
                         if not constraint or token == constraint)
                   for constraint, names in zip(values, catalogues))
    domains, *axes = chosen
    stride = math.prod(len(a) for a in axes)
    total = len(domains) * 450 * stride
    items = []
    for rank in range(offset, min(offset + limit, total)):
        d, remainder = divmod(rank, 450 * stride)
        recipe, remainder = divmod(remainder, stride)
        positions = [0] * len(axes)
        for j in range(len(axes) - 1, -1, -1):
            remainder, positions[j] = divmod(remainder, len(axes[j]))
        index = domains[d] * 450 + recipe
        for available, position in zip(axes, positions):
            index = index * 10 + available[position]
        items.append(describe_epic(EPIC_ACTIONS[index]))
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(EPIC_ACTIONS), "matched": total,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < total else None,
        "domains": list(catalogues[0]), "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS),
        "directors": list(DIRECTORS), "finishes": list(FINISHES),
        "worldlines": list(WORLDLINES), "phases": list(PHASES),
        "campaigns": list(CAMPAIGNS), "chronicles": list(CHRONICLES),
        "epochs": list(EPOCHS), "sagas": list(SAGAS), "epics": list(EPICS),
        "items": items,
    }


def _pattern(axis: int, u: int, v: int, width: int, height: int,
             seed: int, layer_index: int) -> tuple[bool, bool]:
    """Ten distinct, integer-bounded large-world topology masks.

    Returns (navigable corridor, sparingly authored obstacle). Other
    source cells retain their inherited design and canonical palette.
    """
    cx, cy = (width - 1) / 2, (height - 1) / 2
    dx, dy = u - cx, v - cy
    radius = max(1., min(width, height) / 3.)
    period = (seed % 7) + 5
    noise = (u * 73856093 ^ v * 19349663 ^ seed ^ layer_index * 83492791) & 0xffff
    # A shared safety spine means all ten variants have a connected core.
    cross = abs(dx) <= .5 or abs(dy) <= .5
    if axis == 0:  # continental highways: two diagonals and parallel trunks
        corridor = u % period == 0 or v % period == 0 or abs(dx-dy) <= 1
        obstacle = noise % 23 == 0
    elif axis == 1:  # ringed aerial islands, transfer bridges, return center
        ring = abs(math.hypot(dx, dy) - radius) <= 1.3
        corridor = ring or abs(dx) <= 1 or abs(dy) <= 1 or (u + v) % (period+2) == 0
        obstacle = noise % 29 == 0
    elif axis == 2:  # shelf contour, central reef bypass, coastal landing
        shelf = abs(dy - math.sin((u+seed % 19)/5.)*max(2.,height/6)) <= 1.5
        corridor = shelf or v % period == 0 or abs(dx) <= 1
        obstacle = noise % 17 == 0 and abs(dy) > 2
    elif axis == 3:  # concentric city ring roads and radial boulevards
        ring = abs((math.hypot(dx,dy)+seed%4) % period - period/2) <= 1.
        corridor = ring or u % period == 0 or v % period == 0
        obstacle = noise % 31 == 0
    elif axis == 4:  # deep labyrinth with braided bypasses
        braid = abs(dy - math.sin((u+layer_index)/4)*height/5) <= 1.5
        corridor = braid or (u % period == 0 and v % 3 != 1) or v % (period+2) == 0
        obstacle = noise % 19 == 0 and abs(dx) > 2
    elif axis == 5:  # living migration rivers with horizontal refuge lanes
        eco = abs(dy - math.cos((u+seed%11)/6)*height/4) <= 1.5
        corridor = eco or abs(dx) <= 1 or v % (period+3) == 0
        obstacle = noise % 41 == 0
    elif axis == 6:  # siege fronts and flanking egress trenches
        border = abs(dx) <= 1 or abs(dy) <= 1 or abs(dx-dy) <= 1
        corridor = border or (u + layer_index) % period == 0
        obstacle = noise % 13 == 0 and abs(dx) > 3
    elif axis == 7:  # portal quadrants and reversible central convergence
        ring = abs(math.hypot(dx,dy) - radius) <= 1.
        corridor = ring or abs(dx-dy) <= 1 or abs(dx+dy) <= 1
        obstacle = noise % 37 == 0
    elif axis == 8:  # mirrored historical/future site routes
        echo = abs((u+v+layer_index) % period - period/2) <= 1.
        corridor = echo or abs(dx-dy) <= 1 or abs(dx+dy) <= 1
        obstacle = noise % 27 == 0
    else:  # final three-way approach through multiple annular tiers
        ring = abs((math.hypot(dx,dy)+layer_index) % period - period/2) <= 1.
        corridor = ring or abs(dx) <= 1 or abs(dy) <= 1 or abs(dx+dy) <= 1
        obstacle = noise % 43 == 0
    return corridor or cross, obstacle and not cross


def _paint_world(project: StudioProject, args: Mapping[str, Any],
                 axis: int) -> StudioProject:
    """Edit selected tiles plus at most seven explicitly named sibling layers."""
    selected_index, selected = _layer(project, args)
    first = _rectangle(selected, args)
    floor = _tile(selected, args, "floor")
    wall = _tile(selected, args, "wall")
    seed = args.get("seed")
    layers = args.get("epic_layers", [])
    if (floor == wall or type(seed) is not int or not 0 <= seed <= 2**63 - 1
            or type(layers) is not list or len(layers) > 7
            or any(type(x) is not str or len(x) > 128 for x in layers)
            or len(set(layers)) != len(layers)
            or selected.layer_id in layers):
        raise StudioError("Epic layering requires a distinct palette, seed and up to seven unique sibling layers")
    candidates = [selected_index]
    for name in layers:
        matches = [index for index, candidate in enumerate(project.layers)
                   if candidate.layer_id == name]
        if len(matches) != 1:
            raise StudioError("Epic world source layer must already exist")
        candidates.append(matches[0])
    x0, y0, width, height = first
    updated = project
    for layer_offset, index in enumerate(candidates):
        layer = updated.layers[index]
        if x0 + width > layer.width or y0 + height > layer.height:
            raise StudioError("Epic region must fit every selected original layer")
        if floor >= len(layer.palette) or wall >= len(layer.palette):
            raise StudioError("Epic terrain palettes must agree on tile indexes")
        # A valid numeric tile index is not enough: different source layers
        # may have distinct materials at the same index. Never silently
        # paint stone as water or walls as walkable floors.
        if any(index_value >= 0 and layer.palette[index_value] != selected.palette[index_value]
               for index_value in (floor, wall)):
            raise StudioError("Epic sibling layers must share semantic floor/wall tile identities")
        data = list(layer.data)
        for v in range(height):
            for u in range(width):
                corridor, obstacle = _pattern(axis, u, v, width, height,
                                              seed, layer_offset)
                position = (y0+v)*layer.width+x0+u
                if corridor:
                    data[position] = floor
                elif obstacle:
                    data[position] = wall
        updated = _replace_layer(updated, index, replace(layer, data=tuple(data)))
    return updated


def _event(project: StudioProject, operation: str,
           args: Mapping[str, Any], axis: int) -> StudioProject:
    candidate = _page(project, operation, args, axis)
    earlier = candidate.environmental_pages[-1]
    event = EVENTS[axis]
    replacement = replace(
        earlier,
        conditions=(EnvironmentalTrigger(*event[:3]),
                    EnvironmentalTrigger(*event[3:6])),
        actions=(RPGEventAction(*event[6:]),),
    )
    return replace(candidate, environmental_pages=(
        *candidate.environmental_pages[:-1], replacement,
    ))


def _stage_new_actors(project: StudioProject, initial: int, axis: int,
                      seed: int) -> StudioProject:
    if len(project.placements) <= initial:
        return project
    placements = list(project.placements)
    for index in range(initial, len(placements)):
        cast = placements[index]
        phase = (axis * 31 + index - initial + seed % 17) * math.pi / 180
        magnitude = .25 * (axis + 1)
        placements[index] = replace(
            cast,
            x=cast.x + magnitude * math.cos(phase),
            y=cast.y + magnitude * math.sin(phase),
            z=cast.z + (axis % 3) * .15,
            facing_deg=(cast.facing_deg + 24*axis + 11*(index-initial)) % 360,
        )
    return replace(project, placements=tuple(placements))


def _branch_new_quests(project: StudioProject, initial: int,
                       axis: int, operation: str) -> StudioProject:
    if len(project.native_quests) <= initial:
        return project
    quests = list(project.native_quests)
    suffix = sha256(operation.encode("utf8")).hexdigest()[:12]
    for i in range(initial, len(quests)):
        quest = quests[i]
        entry = next((j for j, stage in enumerate(quest.stages)
                      if stage.stage_id == quest.first_stage_id), None)
        if entry is None:
            raise StudioError("Epic path requires an existing canonical quest entry")
        root = quest.stages[entry]
        end = next((stage.stage_id for stage in reversed(quest.stages)
                    if not stage.next_stage_ids), None)
        if end is None or len(quest.stages) > 4094 or len(root.next_stage_ids) >= 32:
            raise StudioError("Epic branch cannot preserve existing quest terminal")
        optional_id = quest.quest_id + "_epic_" + suffix
        if len(optional_id) > 128 or optional_id in {stage.stage_id for stage in quest.stages}:
            raise StudioError("Epic branch duplicates an authored quest stage")
        # When the entry is already terminal, the new branch *becomes*
        # an ending; pointing back to the former terminal would create a loop.
        terminal_edge = () if end == root.stage_id else (end,)
        stage = StudioQuestStage(optional_id, OBJECTIVES[axis], terminal_edge)
        altered = list(quest.stages)
        altered[entry] = replace(
            root, next_stage_ids=(*root.next_stage_ids, optional_id),
        )
        quests[i] = replace(quest, stages=(*altered, stage))
    return replace(project, native_quests=tuple(quests))


def edit_epic(project: StudioProject, operation: str,
              args: Mapping[str, Any],
              execute: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject]
              ) -> StudioProject:
    """One immutable source transaction with real parent Saga changes first."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
            or operation not in EPIC_ACTIONS or not isinstance(args, Mapping)
            or not callable(execute)):
        raise StudioError("unknown original Epic Variation edit")
    parent, axis = parent_action(operation)
    first_cast = len(project.placements)
    first_quests = len(project.native_quests)
    candidate = execute(project, parent, args)
    candidate = _paint_world(candidate, args, axis)
    candidate = _event(candidate, operation, args, axis)
    candidate = _stage_new_actors(candidate, first_cast, axis, args["seed"])
    return _branch_new_quests(candidate, first_quests, axis, operation)
