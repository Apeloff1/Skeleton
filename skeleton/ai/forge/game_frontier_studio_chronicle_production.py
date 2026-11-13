"""Chronicle production: 45B virtual combinations, ten concrete source patterns.

Each chronicle executes a previously registered campaign authoring operation,
paints an additional distinct map layer topology, and appends a genuine
observation-gated RPG page. Only new actor/quest records are refined.
Combinations are not distinct engines, finished games, or native test evidence.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any
import math

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_campaign_production import (
    CAMPAIGN_ACTIONS, CAMPAIGNS, describe_campaign,
    _page as _campaign_page, _cast as _campaign_cast,
    _quest as _campaign_quest,
)
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

CHRONICLES = (
    "first_arrival", "survey_and_discovery", "settlement_growth",
    "regional_upheaval", "emergency_response", "diaspora_routes",
    "institutional_change", "faction_reconciliation",
    "generational_legacy", "renewal_and_return",
)
PURPOSES = (
    "Build arrival waypoints with a navigable return lane",
    "Survey two traversable diagonals and independent observations",
    "Connect civic blocks with walkable streets",
    "Provide multiple escape corridors during upheaval",
    "Construct a protected rescue channel and rendezvous route",
    "Build branching migration corridors with assembly points",
    "Construct institutional access without closing public routes",
    "Connect opposing approaches through a neutral crossing",
    "Document a memorial ring while preserving old passages",
    "Reconnect the return diagonal with a circular bypass",
)
if len(CHRONICLES) != 10 or len(set(CHRONICLES)) != 10:
    raise RuntimeError("chronicle axes must be ten distinct transformations")


class ChronicleActions(Sequence[str]):
    """Exact stable rank/unrank, constant memory; 4.5B campaigns x 10."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(CAMPAIGN_ACTIONS) * len(CHRONICLES)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("chronicle index must be an integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("chronicle operation outside catalog")
        parent, axis = divmod(index, 10)
        return ("chronicle_" + CAMPAIGN_ACTIONS[parent].removeprefix("campaign_")
                + "_________" + CHRONICLES[axis])

    def __contains__(self, item: object) -> bool:
        if type(item) is not str or not item.startswith("chronicle_"):
            return False
        stem, mark, axis = item[len("chronicle_"):].rpartition("_________")
        return bool(mark and axis in CHRONICLES and "campaign_" + stem in CAMPAIGN_ACTIONS)

    def __iter__(self):
        for base in CAMPAIGN_ACTIONS:
            prefix = "chronicle_" + base.removeprefix("campaign_") + "_________"
            for axis in CHRONICLES:
                yield prefix + axis


CHRONICLE_ACTIONS = ChronicleActions()
if len(CHRONICLE_ACTIONS) != 45_000_000_000:
    raise RuntimeError("45-billion chronicle source catalogue mismatch")


def parent_action(operation: str) -> tuple[str, int]:
    if operation not in CHRONICLE_ACTIONS:
        raise StudioError("unknown or forged chronicle source operation")
    stem, axis = operation[len("chronicle_"):].rsplit("_________", 1)
    return "campaign_" + stem, CHRONICLES.index(axis)


def describe_chronicle(operation: str) -> dict[str, Any]:
    base, axis = parent_action(operation)
    return {
        **describe_campaign(base), "operation": operation,
        "base_operation": base, "chronicle": CHRONICLES[axis],
        "chronicle_index": axis, "chronicle_objective": PURPOSES[axis],
        "actual_project_mutation": True,
        "source_outputs": ["real_map_cells", "independent_observed_rpg_page",
                           "new_cast_when_present", "new_quest_when_present"],
    }


def search_chronicles(*, domain: str = "", system_layer: str = "",
                      director: str = "", finish: str = "",
                      worldline: str = "", phase: str = "",
                      campaign: str = "", chronicle: str = "",
                      offset: int = 0, limit: int = 32) -> dict[str, Any]:
    """Page with arithmetic index reconstruction; never iterate 45B strings."""
    values = (domain, system_layer, director, finish,
              worldline, phase, campaign, chronicle)
    catalogs = (tuple(r[0] for r in _DOMAINS), GAMEPLAY_LAYERS, DIRECTORS,
                FINISHES, WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES)
    if (any(type(v) is not str or len(v) > 40 or (v and v not in names)
            for v, names in zip(values, catalogs))
        or type(offset) is not int or not 0 <= offset <= len(CHRONICLE_ACTIONS)
        or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded chronicle search")
    selected = tuple(tuple(i for i, v in enumerate(names) if not value or v == value)
                     for value, names in zip(values, catalogs))
    domains, *dimensions = selected
    stride = math.prod(map(len, dimensions))
    matched = len(domains) * 450 * stride
    items = []
    for rank in range(offset, min(offset + limit, matched)):
        d, remainder = divmod(rank, 450 * stride)
        recipe, remainder = divmod(remainder, stride)
        coordinates = [0] * len(dimensions)
        for pos in range(len(dimensions)-1, -1, -1):
            remainder, coordinates[pos] = divmod(remainder, len(dimensions[pos]))
        index = domains[d] * 450 + recipe
        for options, coordinate in zip(dimensions, coordinates):
            index = index * 10 + options[coordinate]
        items.append(describe_chronicle(CHRONICLE_ACTIONS[index]))
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(CHRONICLE_ACTIONS), "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset+limit if offset+limit < matched else None,
        "domains": list(catalogs[0]), "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS), "directors": list(DIRECTORS),
        "finishes": list(FINISHES), "worldlines": list(WORLDLINES),
        "phases": list(PHASES), "campaigns": list(CAMPAIGNS),
        "chronicles": list(CHRONICLES), "items": items,
    }


def _chronicle_tiles(project: StudioProject, args: Mapping[str, Any],
                     axis: int) -> StudioProject:
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor, wall = _tile(layer, args, "floor"), _tile(layer, args, "wall")
    seed = args.get("seed")
    if floor == wall or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioError("chronicle needs distinct authored tiles and bounded source seed")
    pixels = list(layer.data)
    cx, cy = (width - 1) / 2, (height - 1) / 2
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            u, v = x - x0, y - y0
            dx, dy = u - cx, v - cy
            radius = math.hypot(dx, dy)
            mark, tile = False, floor
            if axis == 0:
                mark = u == 0 or v == 0 or abs(dx - dy) < 1
            elif axis == 1:
                mark = abs(dx + dy) < 1 or abs(dx - dy) < 1
            elif axis == 2:
                mark = u % 5 == 0 or v % 5 == 0
            elif axis == 3:
                mark = u % 7 in (0, 1) or v % 7 in (0, 1)
            elif axis == 4:
                mark = abs(dy) <= 1 or (u + seed % 11) % 9 == 0
            elif axis == 5:
                mark = abs(dy - 2 * math.sin(dx / 4)) < 1.5 or abs(dx) <= 1
            elif axis == 6:
                mark = abs(radius - min(width, height)/3) < 1.2 or abs(dy) <= 1
            elif axis == 7:
                mark = abs(dx) <= 1 or abs(dy) <= 1 or abs(dx - dy) < 1
            elif axis == 8:
                mark = abs(radius - min(width, height)/4) < 1.2
                tile = wall
            elif axis == 9:
                mark = abs(dx + dy) < 1 or abs(radius - min(width, height)/3) < 1.2
            if mark:
                pixels[y * layer.width + x] = tile
    return _replace_layer(project, index, replace(layer, data=tuple(pixels)))


def edit_chronicle(project: StudioProject, operation: str,
                   args: Mapping[str, Any],
                   execute: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject]
                   ) -> StudioProject:
    """One immutable existing-project transaction with a new source mutation."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
        or operation not in CHRONICLE_ACTIONS or not isinstance(args, Mapping)
        or not callable(execute)):
        raise StudioError("unknown original-game chronicle operation")
    parent, axis = parent_action(operation)
    prior_cast, prior_quests = len(project.placements), len(project.native_quests)
    edited = execute(project, parent, args)
    edited = _chronicle_tiles(edited, args, axis)
    edited = _campaign_page(edited, operation, args, axis)
    edited = _campaign_cast(edited, prior_cast, axis)
    return _campaign_quest(edited, prior_quests, axis, operation)
