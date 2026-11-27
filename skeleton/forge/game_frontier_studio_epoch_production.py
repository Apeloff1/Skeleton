"""Ten concrete temporal production transformations over canonical Forge Studio.

Chronicle source editing, immutable project semantics, authorized host CAS, and
native build ownership remain unchanged. The 450B names below are composable
source-edit coordinates, not independently developed games.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any
import math

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_chronicle_production import (
    CHRONICLE_ACTIONS, CHRONICLES, describe_chronicle,
)
from .game_frontier_studio_campaign_production import (
    CAMPAIGNS, _page, _cast, _quest,
)
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

EPOCHS = (
    "daybreak_routes", "nightfall_networks", "spring_thaw",
    "summer_drought", "autumn_trade", "winter_shelter",
    "flood_recovery", "post_siege_repair", "forest_regrowth",
    "future_convergence",
)
OBJECTIVES = (
    "Connect dawn observation towers through accessible corridors",
    "Build intersecting night-patrol trails and safe crossings",
    "Reveal thawwater drainage paths without moving legacy objects",
    "Reopen a connected drought-season service lane",
    "Build a trading circuit with two radial crossing paths",
    "Form a winter shelter network with diagonal exits",
    "Restore floodplain causeways and raised crossing paths",
    "Provide post-siege evacuation routes around damaged blocks",
    "Reconnect reforested clearings along navigable paths",
    "Join future districts through a redundant civic ring",
)
# Two real sensor predicates and one proposal-only game effect per epoch.
# Timed/replayed observations are supplied by the existing canonical runtime.
EPOCH_SIGNALS = (
    ("daylight", "above", .35, "solar_height", "above", 0.,
     "change_light", "environment", "epoch_lighting", "daybreak"),
    ("daylight", "below", .3, "moon_phase", "above", .2,
     "change_light", "environment", "epoch_lighting", "nightfall"),
    ("temperature_c", "above", 0., "ground_ice_fraction", "below", .4,
     "deform_terrain", "environment", "thawwater", "drainage"),
    ("temperature_c", "above", 24., "soil_wetness", "below", .25,
     "weather_transition", "environment", "drought", "dry"),
    ("wind_mps", "above", 4., "leaf_shadow_area_m2", "above", .2,
     "trigger_foliage_fx", "environment", "leaves", "autumn"),
    ("temperature_c", "below", 0., "ground_ice_fraction", "above", .6,
     "set_flag", "world", "winter_shelter", "active"),
    ("water_depth_m", "above", .4, "tide_height_m", "above", .2,
     "change_tide", "environment", "floodplain", "recede"),
    ("building_integrity", "below", .8, "party_morale", "above", .1,
     "set_flag", "world", "repair_route", "open"),
    ("soil_wetness", "above", .4, "humidity", "above", .6,
     "trigger_foliage_fx", "environment", "forest", "regrow"),
    ("quest_progress", "at_least", .9, "npc_reputation", "above", 10.,
     "advance_quest", "quest", "epoch", "reconcile"),
)
if len(EPOCHS) != 10 or len(EPOCH_SIGNALS) != len(EPOCHS) or len(set(EPOCHS)) != 10:
    raise RuntimeError("ten distinct temporal editing patterns are required")


class EpochActions(Sequence[str]):
    """Stable constant-space rank/unrank of 45B chronicle x ten epochs."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(CHRONICLE_ACTIONS) * len(EPOCHS)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("epoch index must be integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("epoch action outside catalogue")
        parent, axis = divmod(index, 10)
        return ("epoch_" + CHRONICLE_ACTIONS[parent].removeprefix("chronicle_")
                + "__________" + EPOCHS[axis])

    def __contains__(self, operation: object) -> bool:
        if type(operation) is not str or not operation.startswith("epoch_"):
            return False
        stem, delim, axis = operation[len("epoch_"):].rpartition("__________")
        return bool(delim and axis in EPOCHS and "chronicle_" + stem in CHRONICLE_ACTIONS)

    def __iter__(self):
        for parent in CHRONICLE_ACTIONS:
            prefix = "epoch_" + parent.removeprefix("chronicle_") + "__________"
            for axis in EPOCHS:
                yield prefix + axis


EPOCH_ACTIONS = EpochActions()
if len(EPOCH_ACTIONS) != 450_000_000_000:
    raise RuntimeError("450B epoch source combinations expected")


def parent_action(operation: str) -> tuple[str, int]:
    if operation not in EPOCH_ACTIONS:
        raise StudioError("unknown or forged temporal source action")
    stem, _, axis = operation[len("epoch_"):].rpartition("__________")
    return "chronicle_" + stem, EPOCHS.index(axis)


def describe_epoch(operation: str) -> dict[str, Any]:
    parent, axis = parent_action(operation)
    return {
        **describe_chronicle(parent), "operation": operation,
        "base_operation": parent, "epoch": EPOCHS[axis],
        "epoch_index": axis, "epoch_objective": OBJECTIVES[axis],
        "actual_project_mutation": True,
        "source_outputs": ["bounded_temporal_map_cells",
                           "independently_observed_rpg_page",
                           "new_only_actor_and_quest_refinements"],
    }


def search_epochs(*, domain: str = "", system_layer: str = "",
                  director: str = "", finish: str = "",
                  worldline: str = "", phase: str = "",
                  campaign: str = "", chronicle: str = "", epoch: str = "",
                  offset: int = 0, limit: int = 32) -> dict[str, Any]:
    """O(page size) enumeration from exact mixed-radix indexes."""
    values = (domain, system_layer, director, finish,
              worldline, phase, campaign, chronicle, epoch)
    catalogs = (tuple(row[0] for row in _DOMAINS), GAMEPLAY_LAYERS,
                DIRECTORS, FINISHES, WORLDLINES, PHASES, CAMPAIGNS,
                CHRONICLES, EPOCHS)
    if (any(type(v) is not str or len(v) > 40 or (v and v not in options)
            for v, options in zip(values, catalogs))
            or type(offset) is not int or not 0 <= offset <= len(EPOCH_ACTIONS)
            or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded epoch search")
    selected = tuple(tuple(i for i, v in enumerate(options)
                           if not chosen or v == chosen)
                     for chosen, options in zip(values, catalogs))
    domains, *dimensions = selected
    stride = math.prod(len(group) for group in dimensions)
    matched = len(domains) * 450 * stride
    rows = []
    for rank in range(offset, min(offset + limit, matched)):
        d, rest = divmod(rank, 450 * stride)
        recipe, rest = divmod(rest, stride)
        coordinates = [0] * len(dimensions)
        for i in range(len(dimensions) - 1, -1, -1):
            rest, coordinates[i] = divmod(rest, len(dimensions[i]))
        index = domains[d] * 450 + recipe
        for options, coordinate in zip(dimensions, coordinates):
            index = index * 10 + options[coordinate]
        rows.append(describe_epoch(EPOCH_ACTIONS[index]))
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(EPOCH_ACTIONS), "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "domains": list(catalogs[0]), "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS), "directors": list(DIRECTORS),
        "finishes": list(FINISHES), "worldlines": list(WORLDLINES),
        "phases": list(PHASES), "campaigns": list(CAMPAIGNS),
        "chronicles": list(CHRONICLES), "epochs": list(EPOCHS), "items": rows,
    }


def _epoch_tiles(project: StudioProject, args: Mapping[str, Any],
                 axis: int) -> StudioProject:
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor, wall = _tile(layer, args, "floor"), _tile(layer, args, "wall")
    seed = args.get("seed")
    if floor == wall or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioError("epoch needs distinct floor/wall and bounded source seed")
    cells = list(layer.data)
    cx, cy = (width - 1) / 2, (height - 1) / 2
    radius = max(1, min(width, height) / 3)
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            u, v = x - x0, y - y0
            dx, dy = u - cx, v - cy
            r = math.hypot(dx, dy)
            if axis == 0:
                paint = u == 0 or v == 0 or abs(dx - dy) < 1.2
            elif axis == 1:
                paint = (u + seed) % 6 == 0 or (v + seed) % 6 == 0
            elif axis == 2:
                paint = abs(dy - 2 * math.sin(u / 3)) < 1.1 or abs(dx) < 1
            elif axis == 3:
                paint = abs(dy) < 1 or (u + 2 * v + seed) % 11 == 0
            elif axis == 4:
                paint = abs(r - radius) < 1.5 or abs(dx) < 1 or abs(dy) < 1
            elif axis == 5:
                paint = abs(dx - dy) < 1 or abs(dx + dy) < 1
            elif axis == 6:
                paint = v % 4 == 0 or (u + seed % 7) % 8 == 0
            elif axis == 7:
                paint = abs(dy) < 1.2 or abs(dx) < 1.2 or (u + v) % 9 == 0
            elif axis == 8:
                paint = abs(r - radius / 2) < 1.1 or u % 5 == 0 or v % 5 == 0
            else:
                paint = abs(r - radius) < 1.4 or abs(dx) < 1 or abs(dy) < 1
            if paint:
                cells[y * layer.width + x] = floor
    return _replace_layer(project, index, replace(layer, data=tuple(cells)))


def _epoch_page(project: StudioProject, operation: str,
                args: Mapping[str, Any], axis: int) -> StudioProject:
    # Reuse the validated, unique, hashed event identity and instance guard.
    with_page = _page(project, operation, args, axis)
    page = with_page.environmental_pages[-1]
    effect = EPOCH_SIGNALS[axis]
    amended = replace(page,
        conditions=(EnvironmentalTrigger(*effect[:3]),
                    EnvironmentalTrigger(*effect[3:6])),
        actions=(RPGEventAction(*effect[6:]),))
    return replace(with_page, environmental_pages=(
        *with_page.environmental_pages[:-1], amended,
    ))


def edit_epoch(project: StudioProject, operation: str,
               args: Mapping[str, Any],
               execute: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject]
               ) -> StudioProject:
    """Parent chronicle, epoch-specific terrain, event and new-only canon."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
            or operation not in EPOCH_ACTIONS or not isinstance(args, Mapping)
            or not callable(execute)):
        raise StudioError("unregistered epoch source edit")
    parent, axis = parent_action(operation)
    old_cast, old_quests = len(project.placements), len(project.native_quests)
    candidate = execute(project, parent, args)
    candidate = _epoch_tiles(candidate, args, axis)
    candidate = _epoch_page(candidate, operation, args, axis)
    candidate = _cast(candidate, old_cast, axis)
    return _quest(candidate, old_quests, axis, operation)
