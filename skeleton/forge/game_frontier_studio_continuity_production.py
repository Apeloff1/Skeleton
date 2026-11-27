"""Continuity production over original authored Forge Studio projects.

4.5T exact virtual compositions extend 450B epoch source operations with ten
distinct reversible story-world treatments. No 4.5T allocation, new state owner,
opaque script execution or provider-side effects. One operation performs a
bounded deterministic tile edit and appends an independently observed RPG page.
Existing cast and quests are preserved; only same-transaction additions change.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_epoch_production import (
    EPOCH_ACTIONS, EPOCHS, describe_epoch,
)
from .game_frontier_studio_chronicle_production import CHRONICLES
from .game_frontier_studio_campaign_production import (
    CAMPAIGNS, _page as _campaign_page, _cast as _campaign_cast,
    _quest as _campaign_quest,
)
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

CONTINUITIES = (
    "narrative_recall", "consequence_weave", "npc_memory_paths",
    "faction_aftershocks", "climate_recovery", "world_scars",
    "alternate_return", "inherited_quests", "place_legacy",
    "epilogue_reentry",
)
PURPOSES = (
    "Reconnect the opening route to a prior chapter location",
    "Surface branching consequences through traversable shortcuts",
    "Create repeat-visit pathways without replacing existing cast",
    "Connect faction boundaries through a neutral-access corridor",
    "Reopen protected passageways during environmental recovery",
    "Keep a visible scar without sealing the primary route",
    "Introduce a second navigable homeward approach",
    "Link inherited chapter paths to new optional quest context",
    "Reserve a public memorial space with uninterrupted access",
    "Open a reentry loop after the narrative epilogue",
)
if len(CONTINUITIES) != 10 or len(set(CONTINUITIES)) != 10:
    raise RuntimeError("continuity requires ten distinct source treatments")


class ContinuityActions(Sequence[str]):
    """Exact rank/unrank of 450B epoch operations by ten treatments."""

    __slots__ = ()

    def __len__(self) -> int:
        return len(EPOCH_ACTIONS) * len(CONTINUITIES)

    def __getitem__(self, index):
        if isinstance(index, slice):
            indices = range(*index.indices(len(self)))
            if len(indices) > 64:
                raise StudioError("virtual catalogue slices are limited to 64 entries")
            return tuple(self[i] for i in indices)
        if type(index) is not int:
            raise TypeError("continuity index must be integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("continuity index outside source catalogue")
        parent, axis = divmod(index, len(CONTINUITIES))
        return ("continuity_" + EPOCH_ACTIONS[parent].removeprefix("epoch_")
                + "__________" + CONTINUITIES[axis])

    def __contains__(self, item: object) -> bool:
        if type(item) is not str or not item.startswith("continuity_"):
            return False
        base, sep, suffix = item[len("continuity_"):].rpartition("__________")
        return bool(sep and suffix in CONTINUITIES
                    and "epoch_" + base in EPOCH_ACTIONS)

    def __iter__(self):
        for parent in EPOCH_ACTIONS:
            prefix = "continuity_" + parent.removeprefix("epoch_") + "__________"
            for continuity in CONTINUITIES:
                yield prefix + continuity


CONTINUITY_ACTIONS = ContinuityActions()
if len(CONTINUITY_ACTIONS) != 4_500_000_000_000:
    raise RuntimeError("continuity operation cardinality must be 4.5 trillion")


def parent_action(operation: str) -> tuple[str, int]:
    if operation not in CONTINUITY_ACTIONS:
        raise StudioError("unregistered continuity production operation")
    stem, suffix = operation[len("continuity_"):].rsplit("__________", 1)
    return "epoch_" + stem, CONTINUITIES.index(suffix)


def describe_continuity(operation: str) -> dict[str, Any]:
    parent, axis = parent_action(operation)
    return {
        **describe_epoch(parent),
        "operation": operation, "base_operation": parent,
        "continuity": CONTINUITIES[axis], "continuity_index": axis,
        "continuity_objective": PURPOSES[axis],
        "actual_project_mutation": True,
        "source_outputs": ["real_bounded_map_cells", "observed_gameplay_page",
                           "new_cast_when_present", "new_quest_when_present"],
    }


def search_continuities(
    *, domain: str = "", system_layer: str = "", director: str = "",
    finish: str = "", worldline: str = "", phase: str = "",
    campaign: str = "", chronicle: str = "", epoch: str = "", continuity: str = "",
    offset: int = 0, limit: int = 32,
) -> dict[str, Any]:
    """O(limit) exact-filter paging without scanning the virtual catalogue."""
    filters = (domain, system_layer, director, finish, worldline,
               phase, campaign, chronicle, epoch, continuity)
    catalogs = (tuple(d[0] for d in _DOMAINS), GAMEPLAY_LAYERS, DIRECTORS,
                FINISHES, WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES, EPOCHS,
                CONTINUITIES)
    if (any(type(value) is not str or len(value) > 40
            or (value and value not in choices)
            for value, choices in zip(filters, catalogs))
        or type(offset) is not int or not 0 <= offset <= len(CONTINUITY_ACTIONS)
        or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded continuity discovery request")
    selected = tuple(
        tuple(i for i, name in enumerate(choices) if not value or value == name)
        for value, choices in zip(filters, catalogs)
    )
    domains, *dimensions = selected
    stride = math.prod(len(options) for options in dimensions)
    matched = len(domains) * 450 * stride
    items = []
    for rank in range(offset, min(offset + limit, matched)):
        domain_index, remainder = divmod(rank, 450 * stride)
        recipe, remainder = divmod(remainder, stride)
        coordinates = [0] * len(dimensions)
        for i in range(len(dimensions) - 1, -1, -1):
            remainder, coordinates[i] = divmod(remainder, len(dimensions[i]))
        index = domains[domain_index] * 450 + recipe
        for options, coordinate in zip(dimensions, coordinates):
            index = index * 10 + options[coordinate]
        items.append(describe_continuity(CONTINUITY_ACTIONS[index]))
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(CONTINUITY_ACTIONS), "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "domains": list(catalogs[0]), "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS), "directors": list(DIRECTORS),
        "finishes": list(FINISHES), "worldlines": list(WORLDLINES),
        "phases": list(PHASES), "campaigns": list(CAMPAIGNS),
        "chronicles": list(CHRONICLES), "epochs": list(EPOCHS),
        "continuities": list(CONTINUITIES),
        "items": items,
    }


def _continuity_tiles(
    project: StudioProject, args: Mapping[str, Any], axis: int,
) -> StudioProject:
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor, wall = _tile(layer, args, "floor"), _tile(layer, args, "wall")
    seed = args.get("seed")
    if floor == wall or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioError("continuity requires two real tiles and a finite seed")
    pixels = list(layer.data)
    cx, cy = (width - 1) / 2, (height - 1) / 2
    for v in range(height):
        for u in range(width):
            dx, dy = u - cx, v - cy
            r = math.hypot(dx, dy)
            mark = False
            value = floor
            if axis == 0:  # Recall route.
                mark = abs(dx) <= 1 or v == 0 or v == height - 1
            elif axis == 1:  # Convergent crossroads.
                mark = abs(dx - dy) <= 1 or abs(dx + dy) <= 1
            elif axis == 2:  # Paired memory paths.
                mark = u % 6 in (0, 1) or abs(dy) <= 1
            elif axis == 3:  # Neutral faction arcade.
                mark = v % 5 == 0 or abs(dx) <= 1
            elif axis == 4:  # Weather-safe evacuation diagonals.
                mark = (u + seed % 7) % 8 == 0 or abs(dx - dy) <= 1
            elif axis == 5:  # Persistent ruins off central travel.
                mark = (u + 2 * v + seed % 17) % 13 == 0 and abs(dy) > 1
                value = wall
            elif axis == 6:  # Dual circular return paths.
                mark = (abs(r - min(width, height) / 3) <= 1.3
                        or abs(dx) <= 1)
            elif axis == 7:  # Inherited quest stair/side branches.
                mark = v % 4 == 0 or (u + v) % 7 == 0
            elif axis == 8:  # Legacy site with pedestrian access.
                mark = abs(r - min(width, height) / 4) <= 1 or abs(dy) <= 1
            elif axis == 9:  # Reentry loops with stable center.
                mark = (abs(r - min(width, height) / 3) <= 1.3
                        or abs(dx - dy) <= 1)
            if mark:
                pixels[(y0 + v) * layer.width + (x0 + u)] = value
    # The creator must preserve at least one traversable route through the edit.
    mid_x = x0 + width // 2
    for v in range(height):
        pixels[(y0 + v) * layer.width + mid_x] = floor
    return _replace_layer(project, index, replace(layer, data=tuple(pixels)))


def edit_continuity(
    project: StudioProject, operation: str, args: Mapping[str, Any],
    execute: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject],
) -> StudioProject:
    """Compose on the canonical immutable authoring transaction only."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
        or operation not in CONTINUITY_ACTIONS or not isinstance(args, Mapping)
        or not callable(execute)):
        raise StudioError("unknown typed continuity source mutation")
    parent, axis = parent_action(operation)
    cast_before = len(project.placements)
    quests_before = len(project.native_quests)
    updated = execute(project, parent, args)
    updated = _continuity_tiles(updated, args, axis)
    updated = _campaign_page(updated, operation, args, axis)
    updated = _campaign_cast(updated, cast_before, axis)
    return _campaign_quest(updated, quests_before, axis, operation)
