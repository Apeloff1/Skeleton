"""450,000 executable directed original-game authoring productions.

Ten *actual* production directions compose with each of 45,000 existing
source-editing expansion recipes. Executing one performs its original game's
authoring changes, applies a second source tile topology transformation and
adds one separately measured two-signal RPG action page. When the composition
introduced cast/quests, only those newly introduced objects receive a
further source-bound directed pose/optional route.

IDs are resolved arithmetically rather than materializing 450,000 strings.
These are distinct bounded composite workflows, not 450,000 handwritten game
engines, pretrained AI weights or finished games.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject, StudioQuestStage
from .game_frontier_rpg_events import RPGEventAction, RPGEventPage, EnvironmentalTrigger
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_system_expansions import (
    EXPANDED_RECIPE_ACTIONS, EXPANDED_RECIPE_INDEX, _LAYER_EFFECTS,
    describe_expansion, GAMEPLAY_LAYERS,
)

DIRECTORS = (
    "navigation_alternates", "ecology_cycles", "tactical_zones",
    "cinematic_staging", "resource_routes", "faction_reactions",
    "physics_obstacles", "audio_cues", "quest_continuity",
    "player_agency",
)
DIRECTOR_PURPOSES = (
    "Author navigable shortcuts and alternate route corridors",
    "Lay out habitat zones and repeatable ecology observation",
    "Arrange a flanking path and protected tactical cover",
    "Build shot-space sightlines and stage cast blocking",
    "Author source-ground resource collection and service routes",
    "Expose faction-dependent routes and encounter placement",
    "Construct slope-obstacle strips for physical movement trials",
    "Lay out audible travel landmarks and ambient sound stages",
    "Branch authored longform story with independent closure",
    "Author player-choice paths and optional progression scenes",
)
if len(DIRECTORS) != 10 or len(set(DIRECTORS)) != 10:
    raise RuntimeError("ten independently executable game production directors required")


class DirectedActions(Sequence[str]):
    """Virtual, stable arithmetic index over 45,000 × 10 real workflows."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(EXPANDED_RECIPE_ACTIONS) * len(DIRECTORS)

    def __getitem__(self, position):
        if isinstance(position, slice):
            return tuple(self[i] for i in range(*position.indices(len(self))))
        if type(position) is not int:
            raise TypeError("production directory indices must be integers")
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError("directed game production index outside catalog")
        source_idx, director_idx = divmod(position, len(DIRECTORS))
        return (
            "direct_" + EXPANDED_RECIPE_ACTIONS[source_idx].removeprefix("expand_")
            + "____" + DIRECTORS[director_idx]
        )

    def __contains__(self, item: object) -> bool:
        if type(item) is not str or not item.startswith("direct_"):
            return False
        rest = item[len("direct_"):]
        prefix, sep, direction = rest.rpartition("____")
        if not sep or direction not in DIRECTORS:
            return False
        original = "expand_" + prefix
        index = EXPANDED_RECIPE_INDEX.get(original)
        if index is None:
            return False
        return item == self[index * len(DIRECTORS) + DIRECTORS.index(direction)]

    def __iter__(self) -> Iterator[str]:
        for expanded in EXPANDED_RECIPE_ACTIONS:
            stem = "direct_" + expanded.removeprefix("expand_") + "____"
            for director in DIRECTORS:
                yield stem + director


DIRECTED_ACTIONS = DirectedActions()
if len(DIRECTED_ACTIONS) != 450000:
    raise RuntimeError("directed production index must have 450,000 workflows")


def _position(operation: str) -> tuple[int, int]:
    if operation not in DIRECTED_ACTIONS:
        raise StudioError("unrecognized directed original-game production")
    stem, director = operation[len("direct_"):].rsplit("____", 1)
    return EXPANDED_RECIPE_INDEX["expand_" + stem], DIRECTORS.index(director)


def describe_direction(operation: str) -> dict[str, Any]:
    base_index, director_index = _position(operation)
    base_name = EXPANDED_RECIPE_ACTIONS[base_index]
    base = describe_expansion(base_name)
    return {
        **base,
        "operation": operation, "base_operation": base_name,
        "direction": DIRECTORS[director_index],
        "director_index": director_index,
        "source_steps": base["recipe_steps"] + ["director_" + DIRECTORS[director_index]],
        "director_purpose": DIRECTOR_PURPOSES[director_index],
        "actual_project_mutation": True,
        "source_outputs": ["authored_map_layer", "environmental_page", "new_actor_and_quest_when_present"],
    }


def search_directions(*, query: str = "", domain: str = "",
                      system_layer: str = "", director: str = "",
                      offset: int = 0, limit: int = 32) -> dict[str, Any]:
    """Paginate without allocating the half-million-operation catalog.

    For exact-match domain/system/director filters only relevant archetypes
    are generated; query filtering checks at most 450,000 small names.
    """
    from .game_frontier_studio_production_recipes import _DOMAINS
    if (type(query) is not str or len(query) > 96 or
            type(domain) is not str or len(domain) > 32 or
            type(system_layer) is not str or len(system_layer) > 32 or
            type(director) is not str or len(director) > 40 or
            (domain and domain not in {d for d, _, _ in _DOMAINS}) or
            (system_layer and system_layer not in GAMEPLAY_LAYERS) or
            (director and director not in DIRECTORS) or
            type(offset) is not int or not 0 <= offset <= len(DIRECTED_ACTIONS) or
            type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded directed production search")
    query = query.strip().lower()
    wanted_directors = (director,) if director else DIRECTORS
    count = 0
    page: list[dict[str, Any]] = []
    for parent in EXPANDED_RECIPE_ACTIONS:
        if domain and not parent.startswith("expand_" + domain + "_"):
            continue
        if system_layer and not parent.endswith("___" + system_layer):
            continue
        stem = "direct_" + parent.removeprefix("expand_") + "____"
        for direction in wanted_directors:
            name = stem + direction
            if query and query not in name:
                continue
            if offset <= count < offset + limit:
                page.append(describe_direction(name))
            count += 1
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": 450000, "matched": count,
        "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < count else None,
        "domains": [d for d, _, _ in _DOMAINS],
        "styles": list(__import__(
            "skeleton.forge.game_frontier_studio_production_recipes",
            fromlist=["TREATMENTS"]).TREATMENTS),
        "system_layers": list(GAMEPLAY_LAYERS), "directors": list(DIRECTORS),
        "items": page,
    }


def _direct_tiles(project: StudioProject, args: Mapping[str, Any],
                  direction: int) -> StudioProject:
    index, layer = _layer(project, args)
    x0, y0, width, height = _rectangle(layer, args)
    floor = _tile(layer, args, "floor")
    wall = _tile(layer, args, "wall")
    if floor == wall:
        raise StudioError("director construction requires distinct authored tiles")
    seed = args.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2**63-1:
        raise StudioError("director requires canonical deterministic source seed")
    data = list(layer.data)
    center_x = x0 + width // 2
    center_y = y0 + height // 2
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            xx, yy = x - x0, y - y0
            u = x - center_x
            v = y - center_y
            mark = False
            tile = floor
            if direction == 0:
                mark = abs(v - 2*math.sin(u/3)) <= 1 or abs(v+u) <= 1
            elif direction == 1:
                mark = (xx*7 + yy*13 + seed % 11) % 17 <= 3
                tile = wall
            elif direction == 2:
                mark = (xx in (1, width-2) or yy in (1, height-2))
                tile = wall
            elif direction == 3:
                mark = (abs(u)==1 or abs(v)==1) and abs(u)<=width//3 and abs(v)<=height//3
            elif direction == 4:
                mark = xx % 4 == 0 or yy % 4 == 0
            elif direction == 5:
                mark = (xx*5+yy*3+seed%5) % 11 <= 2
                tile = wall
            elif direction == 6:
                mark = abs(u) <= 1 or (yy*yy+xx*3)%13 == 0
                tile = wall if abs(u)>1 else floor
            elif direction == 7:
                mark = abs(math.hypot(u,v)-min(width,height)/4) < 1.25
            elif direction == 8:
                mark = abs(v+math.sin(u)*2) <= 1
            else:
                mark = abs(u-v)<=1 or abs(u+v)<=1
            if mark:
                data[y*layer.width+x] = tile
    return _replace_layer(project,index,replace(layer,data=tuple(data)))


def _director_page(project: StudioProject, operation: str, args: Mapping[str, Any],
                   direction: int) -> StudioProject:
    instance = args.get("instance_id","a")
    if (type(instance) is not str or not 1 <= len(instance) <= 16
            or not instance[0].isalpha()
            or any(not (ch.isalnum() or ch=="_") for ch in instance)):
        raise StudioError("director instance must have a stable bounded ID")
    digest=sha256(operation.encode("utf-8")).hexdigest()[:24]
    page_id=f"director_{digest}_{instance}"
    if page_id in {e.event_id for e in project.events} | {
        p.page_id for p in project.environmental_pages
    }:
        raise StudioError("director source event identity already in use")
    # These are existing supported source sensors and typed game action
    # proposals, recombined in ten different gameplay-specific pairs.
    first=_LAYER_EFFECTS[direction]
    second=_LAYER_EFFECTS[(direction+3)%len(_LAYER_EFFECTS)]
    response=_LAYER_EFFECTS[(direction+6)%len(_LAYER_EFFECTS)]
    event = RPGEventPage(
        page_id, direction + 21,
        (
            EnvironmentalTrigger(first[0], first[1], first[2]),
            EnvironmentalTrigger(second[3], second[4], second[5]),
        ),
        (RPGEventAction(*response[6:10]),),
        cooldown_ms=1000*(direction+1),
    )
    return replace(project,environmental_pages=project.environmental_pages+(event,))


def _director_cast(project: StudioProject, prior_count: int,
                   direction: int) -> StudioProject:
    if len(project.placements) <= prior_count:
        return project
    actors=list(project.placements)
    for index in range(prior_count,len(actors)):
        actor=actors[index]
        ordinal=index-prior_count
        theta=(ordinal+1)*math.tau/max(1,len(actors)-prior_count)
        if direction == 0:
            actors[index]=replace(actor,facing_deg=(actor.facing_deg+45)%360)
        elif direction == 1:
            actors[index]=replace(actor,x=actor.x+2*math.cos(theta),
                                  y=actor.y+2*math.sin(theta))
        elif direction == 2:
            actors[index]=replace(actor,x=actor.x+ordinal*2,y=actor.y-ordinal)
        elif direction == 3:
            actors[index]=replace(actor,facing_deg=(theta*180/math.pi)%360)
        elif direction == 4:
            actors[index]=replace(actor,x=actor.x+ordinal*.5)
        elif direction == 5:
            actors[index]=replace(actor,y=actor.y+(ordinal%3)*3)
        elif direction == 6:
            actors[index]=replace(actor,z=actor.z+ordinal*.75)
        elif direction == 7:
            actors[index]=replace(actor,facing_deg=(actor.facing_deg+180)%360)
        elif direction == 8:
            actors[index]=replace(actor,x=actor.x+math.sin(theta)*3)
        else:
            actors[index]=replace(actor,y=actor.y+ordinal*.7)
    return replace(project,placements=tuple(actors))


def _director_quests(project: StudioProject, prior_count: int,
                     direction: int, operation: str) -> StudioProject:
    if len(project.native_quests)<=prior_count:
        return project
    quests=list(project.native_quests)
    suffix=sha256(operation.encode("utf-8")).hexdigest()[:12]
    for index in range(prior_count,len(quests)):
        q=quests[index]
        source=q.stages[0]
        last=next((stage for stage in reversed(q.stages) if not stage.next_stage_ids),None)
        if last is None or len(source.next_stage_ids)>=32:
            raise StudioError("directed quest cannot attach an authorized side route")
        stage_id=q.quest_id+"_dir_"+suffix
        if len(stage_id)>128 or stage_id in {s.stage_id for s in q.stages}:
            raise StudioError("directed quest scene identity cannot be reused")
        attached=StudioQuestStage(
            stage_id,DIRECTOR_PURPOSES[direction],(last.stage_id,))
        quests[index]=replace(q,stages=(
            replace(source,next_stage_ids=source.next_stage_ids+(stage_id,)),
            *q.stages[1:],attached))
    return replace(project,native_quests=tuple(quests))


def edit_direction(
    project: StudioProject, operation: str, args: Mapping[str, Any],
    perform: Callable[[StudioProject, str, Mapping[str, Any]], StudioProject],
) -> StudioProject:
    """Execute an exact prior source recipe then add real gameplay direction."""
    if (not isinstance(project,StudioProject) or type(operation) is not str
            or operation not in DIRECTED_ACTIONS
            or not isinstance(args,Mapping) or not callable(perform)):
        raise StudioError("unknown or unauthorized game production direction")
    recipe_index, direction=_position(operation)
    actor_count=len(project.placements)
    quest_count=len(project.native_quests)
    # The original 45k source transformation preserves all security,
    # project identity and immutable transactional invariants.
    produced=perform(project,EXPANDED_RECIPE_ACTIONS[recipe_index],args)
    produced=_direct_tiles(produced,args,direction)
    produced=_director_page(produced,operation,args,direction)
    produced=_director_cast(produced,actor_count,direction)
    produced=_director_quests(produced,quest_count,direction,operation)
    return produced
