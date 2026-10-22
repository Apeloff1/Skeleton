"""Long-form Saga production with ten actual original-game continuity transforms.

Each saga operation executes its exact registered epoch authoring operation,
adds distinct map topology and observation-gated RPG events, and refines only
cast/quest records created by that transaction. Existing canon survives.
The 4.5T identifiers represent source compositions, not independent games.
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
from .game_frontier_studio_campaign_production import CAMPAIGNS, _page
from .game_frontier_studio_epoch_production import (
    EPOCH_ACTIONS, EPOCHS, describe_epoch,
)
from .game_frontier_studio_chronicle_production import CHRONICLES
from .game_frontier_studio_phase_production import PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

SAGAS = (
    "homecoming", "faction_concord", "buried_history", "skyward_migration",
    "oceanic_reckoning", "citadel_reconstruction", "wildlife_pact",
    "betrayal_aftermath", "starfall_observatory", "branching_epilogue",
)
OBJECTIVES = (
    "Reconnect the protagonist's old home with two navigable arrival paths",
    "Join divided settlements with a negotiated neutral crossing",
    "Expose an archaeological circuit while preserving earlier routes",
    "Build a branching sky-island migration network and return channel",
    "Connect a tide-affected coastline to a sheltered inland crossing",
    "Rebuild the citadel streets while keeping an evacuation alternative",
    "Restore ecological corridors without erasing existing settlements",
    "Create two independent routes to confront a betrayal",
    "Connect observatory rings with traversable celestial sightlines",
    "Build a replay-stable epilogue hub with three distinct approaches",
)
# Independently evaluated sensor predicates, then one proposal-only action.
# These are native-owned observation names, not invented data or applied effects.
SIGNALS = (
    ("quest_progress", "above", .3, "npc_reputation", "above", 0.,
     "show_dialogue", "character", "saga_homecoming", "welcome"),
    ("npc_reputation", "above", 15., "party_morale", "above", .4,
     "set_faction_reputation", "character", "concord", "negotiated"),
    ("erosion", "above", .2, "building_integrity", "below", .8,
     "inspect_instrument", "ui", "ancient_site", "survey"),
    ("updraft_mps", "above", 2., "sky_island_height_m", "above", 110.,
     "world_portal", "navigation", "sky_crossing", "reopened"),
    ("tide_height_m", "above", .4, "water_depth_m", "above", 1.,
     "change_tide", "environment", "harbor", "passage"),
    ("building_integrity", "below", .85, "quest_progress", "above", .45,
     "set_flag", "world", "citadel_rebuilt", "candidate"),
    ("humidity", "above", .55, "soil_wetness", "above", .35,
     "trigger_foliage_fx", "environment", "wildlife_corridor", "regrowth"),
    ("npc_reputation", "below", 0., "party_morale", "below", .35,
     "show_dialogue", "character", "betrayal", "reckoning"),
    ("solar_height", "below", 5., "moon_phase", "above", .6,
     "change_camera", "cinematic", "observatory", "starfall"),
    ("quest_progress", "at_least", .9, "npc_reputation", "above", 25.,
     "advance_quest", "quest", "saga_epilogue", "choice"),
)
if len(SAGAS) != 10 or len(set(SAGAS)) != 10 or len(SIGNALS) != 10:
    raise RuntimeError("saga axis registry requires ten distinct authored scenarios")


class SagaActions(Sequence[str]):
    """4.5T exactly reversible IDs with O(1) index/membership memory."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(EPOCH_ACTIONS) * len(SAGAS)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("saga index must be an integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("saga source index outside registered catalogue")
        parent, axis = divmod(index, 10)
        return ("saga_" + EPOCH_ACTIONS[parent].removeprefix("epoch_")
                + "___________" + SAGAS[axis])

    def __contains__(self, operation: object) -> bool:
        if type(operation) is not str or not operation.startswith("saga_"):
            return False
        stem, delim, axis = operation[len("saga_"):].rpartition("___________")
        return bool(delim and axis in SAGAS and "epoch_" + stem in EPOCH_ACTIONS)

    def __iter__(self):
        for parent in EPOCH_ACTIONS:
            prefix = "saga_" + parent.removeprefix("epoch_") + "___________"
            for saga in SAGAS:
                yield prefix + saga


SAGA_ACTIONS = SagaActions()
if len(SAGA_ACTIONS) != 4_500_000_000_000:
    raise RuntimeError("saga action count must be exactly 4.5 trillion")


def parent_action(operation: str) -> tuple[str, int]:
    if operation not in SAGA_ACTIONS:
        raise StudioError("unrecognized or forged saga source producer")
    stem, _, axis = operation[len("saga_"):].rpartition("___________")
    return "epoch_" + stem, SAGAS.index(axis)


def describe_saga(operation: str) -> dict[str, Any]:
    parent, axis = parent_action(operation)
    return {
        **describe_epoch(parent), "operation": operation,
        "base_operation": parent, "saga": SAGAS[axis], "saga_index": axis,
        "saga_objective": OBJECTIVES[axis],
        "actual_project_mutation": True,
        "source_outputs": ["saga_topology_cells", "observed_story_event_page",
                           "new_only_cast_staging", "new_only_quest_branch"],
    }


def search_sagas(*, domain: str = "", system_layer: str = "",
                 director: str = "", finish: str = "",
                 worldline: str = "", phase: str = "",
                 campaign: str = "", chronicle: str = "",
                 epoch: str = "", saga: str = "",
                 offset: int = 0, limit: int = 32) -> dict[str, Any]:
    """Exact filtered search via arithmetic mixed-radix rank/unrank."""
    values = (domain, system_layer, director, finish, worldline,
              phase, campaign, chronicle, epoch, saga)
    catalogues = (tuple(row[0] for row in _DOMAINS), GAMEPLAY_LAYERS,
                  DIRECTORS, FINISHES, WORLDLINES, PHASES,
                  CAMPAIGNS, CHRONICLES, EPOCHS, SAGAS)
    if (any(type(v) is not str or len(v) > 40 or (v and v not in names)
            for v, names in zip(values, catalogues))
            or type(offset) is not int or not 0 <= offset <= len(SAGA_ACTIONS)
            or type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded saga source search")
    selected = tuple(tuple(i for i, value in enumerate(names)
                           if not constraint or value == constraint)
                     for constraint, names in zip(values, catalogues))
    domains, *dimensions = selected
    stride = math.prod(len(group) for group in dimensions)
    matched = len(domains) * 450 * stride
    rows = []
    for rank in range(offset, min(offset + limit, matched)):
        d, remainder = divmod(rank, 450 * stride)
        recipe, remainder = divmod(remainder, stride)
        coordinates = [0] * len(dimensions)
        for j in range(len(dimensions) - 1, -1, -1):
            remainder, coordinates[j] = divmod(remainder, len(dimensions[j]))
        absolute = domains[d] * 450 + recipe
        for choices, coordinate in zip(dimensions, coordinates):
            absolute = absolute * 10 + choices[coordinate]
        rows.append(describe_saga(SAGA_ACTIONS[absolute]))
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(SAGA_ACTIONS), "matched": matched,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < matched else None,
        "domains": list(catalogues[0]), "styles": list(TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS),
        "directors": list(DIRECTORS), "finishes": list(FINISHES),
        "worldlines": list(WORLDLINES), "phases": list(PHASES),
        "campaigns": list(CAMPAIGNS), "chronicles": list(CHRONICLES),
        "epochs": list(EPOCHS), "sagas": list(SAGAS), "items": rows,
    }


def _saga_topology(project: StudioProject, args: Mapping[str, Any],
                   axis: int) -> StudioProject:
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor, wall = _tile(layer, args, "floor"), _tile(layer, args, "wall")
    seed = args.get("seed")
    if floor == wall or type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise StudioError("saga needs distinct tiles and bounded replay seed")
    cells = list(layer.data)
    cx, cy = (width - 1) / 2, (height - 1) / 2
    radius = max(1.0, min(width, height) / 3)
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            u, v = x - x0, y - y0
            dx, dy = u - cx, v - cy
            r = math.hypot(dx, dy)
            if axis == 0:
                chosen = u in (0, width - 1) or abs(dy) <= 1 or abs(dx - dy) <= 1
            elif axis == 1:
                chosen = abs(dx) <= 1 or abs(dy) <= 1 or (u + v) % 7 == 0
            elif axis == 2:
                chosen = abs(r - radius) <= 1.5 or abs(dx + dy) <= 1
            elif axis == 3:
                chosen = (u + seed % 5) % 6 == 0 or abs(dy - 2 * math.sin(dx / 3)) < 1.4
            elif axis == 4:
                chosen = v % 4 == 0 or abs(dx) <= 1
            elif axis == 5:
                chosen = u % 5 in (0, 1) or v % 5 in (0, 1)
            elif axis == 6:
                chosen = abs(dy - 2 * math.cos(dx / 3)) < 1.4 or u % 7 == 0
            elif axis == 7:
                chosen = abs(dx - dy) <= 1 or abs(dx + dy) <= 1 or v == 0
            elif axis == 8:
                chosen = abs(r - radius) <= 1.4 or abs(dx) <= 1
            else:
                chosen = abs(dx) <= 1 or abs(dy) <= 1 or abs(r - radius) <= 1.4
            if chosen:
                cells[y * layer.width + x] = floor
            elif axis in (2, 5, 8) and (u * 7 + v * 11 + seed) % 29 == 0:
                cells[y * layer.width + x] = wall
    return _replace_layer(project, index, replace(layer, data=tuple(cells)))


def _saga_page(project: StudioProject, operation: str,
               args: Mapping[str, Any], axis: int) -> StudioProject:
    proposal = _page(project, operation, args, axis)
    original = proposal.environmental_pages[-1]
    event = SIGNALS[axis]
    amended = replace(
        original,
        conditions=(EnvironmentalTrigger(*event[:3]),
                    EnvironmentalTrigger(*event[3:6])),
        actions=(RPGEventAction(*event[6:]),),
    )
    return replace(proposal, environmental_pages=(
        *proposal.environmental_pages[:-1], amended,
    ))


def _stage_new_cast(project: StudioProject, first: int, axis: int) -> StudioProject:
    if len(project.placements) <= first:
        return project
    cast = list(project.placements)
    for i in range(first, len(cast)):
        actor = cast[i]
        ordinal = i - first
        bearing = (actor.facing_deg + axis * 36 + ordinal * 9) % 360
        offset = (axis + 1) * .2 + ordinal * .15
        cast[i] = replace(actor, x=actor.x + offset,
                          y=actor.y + math.sin(axis + ordinal) * offset,
                          facing_deg=bearing)
    return replace(project, placements=tuple(cast))


def _branch_new_quests(project: StudioProject, first: int,
                       axis: int, operation: str) -> StudioProject:
    if len(project.native_quests) <= first:
        return project
    quests = list(project.native_quests)
    postfix = sha256(operation.encode("utf8")).hexdigest()[:12]
    for i in range(first, len(quests)):
        quest = quests[i]
        root = quest.stages[0]
        terminal = next((s.stage_id for s in reversed(quest.stages)
                         if not s.next_stage_ids), None)
        if terminal is None or len(root.next_stage_ids) >= 32:
            raise StudioError("saga quest has no reachable terminal or free branch")
        stage_id = quest.quest_id + "_saga_" + postfix
        if len(stage_id) > 128 or stage_id in {s.stage_id for s in quest.stages}:
            raise StudioError("saga quest stage collides with existing canon")
        stage = StudioQuestStage(stage_id, OBJECTIVES[axis], (terminal,))
        quests[i] = replace(quest, stages=(
            replace(root, next_stage_ids=root.next_stage_ids + (stage_id,)),
            *quest.stages[1:], stage,
        ))
    return replace(project, native_quests=tuple(quests))


def edit_saga(project: StudioProject, operation: str,
              args: Mapping[str, Any],
              execute: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject]
              ) -> StudioProject:
    """A pure project transaction; host-owned CAS is the only persistence path."""
    if (not isinstance(project, StudioProject) or type(operation) is not str
            or operation not in SAGA_ACTIONS or not isinstance(args, Mapping)
            or not callable(execute)):
        raise StudioError("unknown original saga source operation")
    parent, axis = parent_action(operation)
    initial_cast = len(project.placements)
    initial_quests = len(project.native_quests)
    candidate = execute(project, parent, args)
    candidate = _saga_topology(candidate, args, axis)
    candidate = _saga_page(candidate, operation, args, axis)
    candidate = _stage_new_cast(candidate, initial_cast, axis)
    return _branch_new_quests(candidate, initial_quests, axis, operation)
