"""45,000,000 executable original-game worldline authoring compositions.

Every worldline executes one exact existing final-production workflow, adds a
second independently source-painted map feature, records a real two-observation
gameplay page, and may revise *only newly produced* actors and native quest
stages. All project changes remain immutable until the parent authorized CAS
transaction commits. 45M refers to composed workflows, not separate engines.

The catalog is fully virtual and requires no 45M command-string allocation.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject, StudioQuestStage
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction, RPGEventPage
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_final_production import (
    FINAL_PRODUCTION_ACTIONS, FINISHES,
)
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

WORLDLINES = (
    "river_network", "city_circulation", "wilderness_ecology",
    "tactical_encounters", "subterranean_routes", "sky_navigation",
    "social_reputation", "environmental_pressure",
    "narrative_consequence", "cinematic_blocking",
)
WORLDLINE_OBJECTIVES = (
    "Survey alternate river crossings and return paths",
    "Provide connected civic lanes, markets and street waypoints",
    "Guide natural habitats and wildlife passage through cover",
    "Find viable tactical approaches without blocking all escapes",
    "Open a safe alternate passage through tunnels and shafts",
    "Navigate aerial corridors using measured updrafts",
    "Reconcile existing social relations before final dialogue",
    "Preserve safe travel paths under rising climate hazards",
    "Resolve an authored plot choice without erasing canon",
    "Stage actors and scene lines for camera continuity",
)
# Each line is two independently measured canonical signals followed by an
# allowed proposal-only game action. Effects are NOT applied by this editor.
WORLDLINE_EFFECTS = (
    ("tide_height_m", "above", 1., "water_depth_m", "above", .5,
     "inspect_instrument", "ui", "chart", "river_crossing"),
    ("npc_reputation", "above", 10., "quest_progress", "above", .1,
     "open_shop", "character", "market", "city_route"),
    ("humidity", "above", .55, "soil_wetness", "above", .3,
     "trigger_foliage_fx", "environment", "habitat", "corridor"),
    ("native_contact_count", "above", 0., "party_morale", "below", .85,
     "start_combat", "character", "encounter", "defensible_route"),
    ("fog_visibility_m", "below", 160., "altitude_m", "below", 50.,
     "inspect_instrument", "ui", "map", "cavern_route"),
    ("updraft_mps", "above", 2., "sky_island_height_m", "above", 120.,
     "apply_gameplay_effect", "character", "traveler", "sky_lift"),
    ("npc_reputation", "above", 20., "party_morale", "above", .5,
     "set_faction_reputation", "character", "allies", "trust"),
    ("wind_mps", "above", 12., "rain_mm_h", "above", 4.,
     "weather_transition", "environment", "world", "storm_front"),
    ("quest_progress", "at_least", .7, "npc_reputation", "above", 5.,
     "advance_quest", "quest", "chapter", "choice"),
    ("daylight", "below", .4, "sound_occlusion", "above", .45,
     "change_camera", "cinematic", "scene", "night_blocking"),
)
if len(WORLDLINES) != 10 or len(set(WORLDLINES)) != 10 or len(WORLDLINE_EFFECTS) != 10:
    raise RuntimeError("worldline compiler requires ten distinct production variants")


class WorldlineActions(Sequence[str]):
    """Stable virtual rank/unrank: 4.5M final source recipes × 10 worldlines."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(FINAL_PRODUCTION_ACTIONS) * len(WORLDLINES)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("worldline index must be integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("worldline index outside virtual production catalog")
        parent, axis = divmod(index, len(WORLDLINES))
        return ("worldline_" + FINAL_PRODUCTION_ACTIONS[parent].removeprefix("complete_")
                + "______" + WORLDLINES[axis])

    def __contains__(self, value: object) -> bool:
        if type(value) is not str or not value.startswith("worldline_"):
            return False
        stem, separator, axis = value[len("worldline_"):].rpartition("______")
        return bool(separator and axis in WORLDLINES and
                    "complete_" + stem in FINAL_PRODUCTION_ACTIONS)

    def __iter__(self) -> Iterator[str]:
        for base in FINAL_PRODUCTION_ACTIONS:
            stem = "worldline_" + base.removeprefix("complete_") + "______"
            for axis in WORLDLINES:
                yield stem + axis


WORLDLINE_ACTIONS = WorldlineActions()
if len(WORLDLINE_ACTIONS) != 45_000_000:
    raise RuntimeError("45 million composed worldline operations required")


def _parent(operation: str) -> tuple[str, int]:
    if operation not in WORLDLINE_ACTIONS:
        raise StudioError("unknown or forged original-world production")
    stem, axis = operation[len("worldline_"):].rsplit("______", 1)
    return "complete_" + stem, WORLDLINES.index(axis)


def describe_worldline(operation: str) -> dict[str, Any]:
    from .game_frontier_studio_final_production import describe_final_action
    base, index = _parent(operation)
    return {
        **describe_final_action(base),
        "operation": operation,
        "base_operation": base,
        "worldline": WORLDLINES[index],
        "worldline_index": index,
        "worldline_objective": WORLDLINE_OBJECTIVES[index],
        "actual_project_mutation": True,
        "production_outputs": ["real_tile_cells", "observed_rpg_event_page",
                               "new_cast_if_present", "new_quest_if_present"],
    }


def search_worldlines(*, query: str = "", domain: str = "",
                      system_layer: str = "", director: str = "",
                      finish: str = "", worldline: str = "",
                      offset: int = 0, limit: int = 32) -> dict[str, Any]:
    """Rank/unrank exact filters in O(page-size), not O(45 million names).

    Substring requests must choose at least domain, director and worldline:
    exhaustive arbitrary full-text scans over 45M names are disallowed.
    """
    if (type(query) is not str or len(query) > 96 or
        type(domain) is not str or len(domain) > 32 or
        type(system_layer) is not str or len(system_layer) > 32 or
        type(director) is not str or len(director) > 40 or
        type(finish) is not str or len(finish) > 40 or
        type(worldline) is not str or len(worldline) > 40 or
        domain and domain not in {d for d,_,_ in _DOMAINS} or
        system_layer and system_layer not in GAMEPLAY_LAYERS or
        director and director not in DIRECTORS or
        finish and finish not in FINISHES or
        worldline and worldline not in WORLDLINES or
        type(offset) is not int or not 0 <= offset <= len(WORLDLINE_ACTIONS) or
        type(limit) is not int or not 1 <= limit <= 64):
        raise StudioError("invalid bounded fifty-million-tool query")
    query=query.strip().lower()
    if query and not (domain and director and worldline):
        raise StudioError("text search requires domain, director and worldline filters")
    dindices=tuple(i for i,x in enumerate(_DOMAINS) if not domain or x[0]==domain)
    sindices=tuple(i for i,x in enumerate(GAMEPLAY_LAYERS)
                   if not system_layer or x==system_layer)
    rindices=tuple(i for i,x in enumerate(DIRECTORS) if not director or x==director)
    findices=tuple(i for i,x in enumerate(FINISHES) if not finish or x==finish)
    windices=tuple(i for i,x in enumerate(WORLDLINES) if not worldline or x==worldline)
    stride=len(sindices)*len(rindices)*len(findices)*len(windices)
    per_domain=450*stride
    eligible=len(dindices)*per_domain
    results=[]
    if not query:
        for rank in range(offset,min(eligible,offset+limit)):
            d,local=divmod(rank,per_domain)
            recipe,local=divmod(local,stride)
            system,local=divmod(local,len(rindices)*len(findices)*len(windices))
            director_idx,local=divmod(local,len(findices)*len(windices))
            fin_idx,line_idx=divmod(local,len(windices))
            source_idx=((((dindices[d]*450+recipe)*10+sindices[system])*10
                         +rindices[director_idx])*10+findices[fin_idx])
            results.append(describe_worldline(
                WORLDLINE_ACTIONS[source_idx*10+windices[line_idx]]))
        matched=eligible
    else:
        # Narrowed keyword search never allocates all matching names.
        matched=0
        for d in dindices:
            for recipe in range(450):
                for system in sindices:
                    for director_idx in rindices:
                        for fin in findices:
                            base_idx=((((d*450+recipe)*10+system)*10
                                       +director_idx)*10+fin)
                            for line in windices:
                                name=WORLDLINE_ACTIONS[base_idx*10+line]
                                if query not in name:
                                    continue
                                if offset <= matched < offset+limit:
                                    results.append(describe_worldline(name))
                                matched+=1
    return {
        "schema": "skeleton.forge.production_recipe_search.v1",
        "total_catalog": len(WORLDLINE_ACTIONS),
        "matched": matched, "offset": offset, "limit": limit,
        "next_offset": offset+limit if offset+limit < matched else None,
        "domains": [d for d,_,_ in _DOMAINS],
        "styles": list(TREATMENTS), "system_layers": list(GAMEPLAY_LAYERS),
        "directors": list(DIRECTORS), "finishes": list(FINISHES),
        "worldlines": list(WORLDLINES), "items": results,
    }


def _paint(project: StudioProject, args: Mapping[str, Any], axis: int) -> StudioProject:
    index, layer = _layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor,wall=_tile(layer,args,"floor"),_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("worldline needs distinct real floor/wall source indices")
    seed=args.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2**63-1:
        raise StudioError("worldline requires bounded reproducible integer seed")
    tiles=list(layer.data)
    cx,cy=x0+(w-1)/2,y0+(h-1)/2
    for y in range(y0,y0+h):
        for x in range(x0,x0+w):
            dx,dy=x-cx,y-cy
            radius=math.hypot(dx,dy)
            if axis==0:
                active=abs(dy - 2*math.sin(dx*.27+seed%9)) <= 1
                tile=floor
            elif axis==1:
                active=(x-x0)%4==0 or (y-y0)%4==0
                tile=floor
            elif axis==2:
                active=(x*11+y*7+seed%13)%19<4
                tile=wall
            elif axis==3:
                active=abs(radius-min(w,h)/3) < 1
                tile=wall
            elif axis==4:
                active=abs(dx+dy)<=1 or abs(dx-dy)<=1
                tile=floor
            elif axis==5:
                active=abs(radius-min(w,h)/4)<=1.2 or abs(dx)<=.5
                tile=floor
            elif axis==6:
                active=(x+y+seed%7)%6<=1
                tile=floor
            elif axis==7:
                active=abs(dy+math.sin(dx*.5)*3)<=1
                tile=floor
            elif axis==8:
                active=(x*17+y*3+seed%11)%23<5
                tile=wall
            else:
                active=abs(dx-2*math.sin(dy*.4))<=1
                tile=floor
            if active:
                tiles[y*layer.width+x]=tile
    return _replace_layer(project,index,replace(layer,data=tuple(tiles)))


def _page(project: StudioProject, operation: str, args: Mapping[str, Any], axis: int) -> StudioProject:
    instance=args.get("instance_id","a")
    if (type(instance) is not str or not 1 <= len(instance) <= 16
        or not instance[0].isalpha()
        or any(not (c.isalnum() or c=="_") for c in instance)):
        raise StudioError("worldline instance ID must be bounded and stable")
    page_id="worldline_"+sha256(operation.encode("utf-8")).hexdigest()[:24]+"_"+instance
    if page_id in {x.page_id for x in project.environmental_pages} | {
        x.event_id for x in project.events
    }:
        raise StudioError("worldline page source collision")
    v=WORLDLINE_EFFECTS[axis]
    entry=RPGEventPage(page_id,41+axis,
        (EnvironmentalTrigger(v[0],v[1],v[2]),
         EnvironmentalTrigger(v[3],v[4],v[5])),
        (RPGEventAction(*v[6:]),),cooldown_ms=1000*(axis+1))
    return replace(project,environmental_pages=project.environmental_pages+(entry,))


def _actors(project: StudioProject, prior: int, axis: int) -> StudioProject:
    if len(project.placements)<=prior:
        return project
    actors=list(project.placements)
    count=len(actors)-prior
    for i in range(prior,len(actors)):
        p=actors[i]
        t=i-prior
        theta=t*math.tau/max(1,count)
        if axis==0: actors[i]=replace(p,x=p.x+t*1.2)
        elif axis==1: actors[i]=replace(p,x=p.x+math.cos(theta)*3,y=p.y+math.sin(theta)*3)
        elif axis==2: actors[i]=replace(p,y=p.y+t*.7)
        elif axis==3: actors[i]=replace(p,facing_deg=(p.facing_deg+90)%360)
        elif axis==4: actors[i]=replace(p,z=p.z-t*.25)
        elif axis==5: actors[i]=replace(p,z=p.z+3+t*.6)
        elif axis==6: actors[i]=replace(p,facing_deg=(p.facing_deg+180)%360)
        elif axis==7: actors[i]=replace(p,x=p.x+math.sin(theta)*2)
        elif axis==8: actors[i]=replace(p,x=p.x+t*.5,y=p.y-t*.4)
        else: actors[i]=replace(p,facing_deg=(t*45)%360)
    return replace(project,placements=tuple(actors))


def _quest(project: StudioProject, before: int, axis: int, operation: str) -> StudioProject:
    if len(project.native_quests)<=before:
        return project
    quests=list(project.native_quests)
    postfix=sha256(operation.encode("utf-8")).hexdigest()[:12]
    for i in range(before,len(quests)):
        q=quests[i]
        entry=q.stages[0]
        terminal=next((s.stage_id for s in reversed(q.stages) if not s.next_stage_ids),None)
        if terminal is None or len(entry.next_stage_ids)>=32:
            raise StudioError("worldline plot lacks valid reachable terminal or branch capacity")
        new_id=q.quest_id+"_wl_"+postfix
        if len(new_id)>128 or new_id in {s.stage_id for s in q.stages}:
            raise StudioError("worldline plot-stage ID collision")
        stage=StudioQuestStage(new_id,WORLDLINE_OBJECTIVES[axis],(terminal,))
        quests[i]=replace(q,stages=(
            replace(entry,next_stage_ids=entry.next_stage_ids+(new_id,)),
            *q.stages[1:],stage))
    return replace(project,native_quests=tuple(quests))


def edit_worldline(
    project: StudioProject, operation: str, args: Mapping[str, Any],
    perform: Callable[[StudioProject,str,Mapping[str,Any]],StudioProject],
) -> StudioProject:
    """One authorized atomic world creation transaction; no new store."""
    if (not isinstance(project,StudioProject) or type(operation) is not str
        or operation not in WORLDLINE_ACTIONS or
        not isinstance(args,Mapping) or not callable(perform)):
        raise StudioError("unknown original-world production operation")
    parent,axis=_parent(operation)
    actors_before=len(project.placements)
    quests_before=len(project.native_quests)
    made=perform(project,parent,args)
    made=_paint(made,args,axis)
    made=_page(made,operation,args,axis)
    made=_actors(made,actors_before,axis)
    made=_quest(made,quests_before,axis,operation)
    return made
