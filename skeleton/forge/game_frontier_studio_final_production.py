"""4,500,000 executable final-production passes over the original Forge Studio.

Each of ten distinct, fixed engine passes *executes* one already validated
directed game-production recipe, alters bounded canonical tile geometry, and
appends a real deterministic environmental gameplay event. Newly authored cast
and story may gain a specific playable transformation; earlier saved characters
and quests are never silently changed.

This is a virtual indexed catalog of composite workflows, not 4.5 million
standalone authored engines, model weights or independently finished games.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
import math
from typing import Any

from .game_frontier_studio import StudioError, StudioProject, StudioQuestStage
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction, RPGEventPage
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_directed_production import (
    DIRECTED_ACTIONS, DIRECTORS, describe_direction,
)
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

# Each production finish is distinct: it constructs a separate authored
# map-layer topology, generates a page with its own sensors/response, and
# gives a newly produced cast/quest its own optional playable treatment.
FINISHES = (
    "route_optimization", "settlement_life", "environmental_fidelity",
    "character_staging", "combat_readiness", "resource_balance",
    "cinematic_continuity", "vertical_routes", "ecosystem_restore",
    "alternate_endings",
)
FINISH_OBJECTIVES = (
    "Find the safer navigable alternative and mark a return route",
    "Meet the inhabitants at the central living-world gathering",
    "Read the evolving environmental hazard before advancing",
    "Assemble the independent cast in the required scene positions",
    "Choose a protected approach to the next combat encounter",
    "Secure the supplies and restore trade access across the region",
    "Align the final chapter's camera and scene transitions",
    "Reach the upper crossing with a verified skyward route",
    "Restore the crossing without disturbing the migrating creatures",
    "Choose another reachable ending without erasing existing canon",
)
# Canonical source signals and proposal-only gameplay actions. Importantly,
# these pages are evaluated from *observed* gameplay, not made-up conditions.
FINISH_EFFECTS = (
    ("compass_heading_deg","at_least",90., "fog_visibility_m","below",220.,
     "inspect_instrument","ui","navigator","alternate_route"),
    ("party_morale","above",.5, "npc_reputation","above",15.,
     "set_npc_emotion","character","villagers","welcoming"),
    ("wind_mps","above",11., "rain_mm_h","above",2.,
     "weather_transition","environment","world","heavy_weather"),
    ("daylight","below",.4, "sound_occlusion","above",.55,
     "change_camera","cinematic","scene","low_light"),
    ("native_contact_count","above",0., "party_morale","below",.7,
     "start_combat","character","encounter","cover"),
    ("npc_reputation","above",20., "quest_progress","above",.2,
     "open_shop","character","merchant","supply"),
    ("music_intensity","above",.5, "daylight","below",.8,
     "play_cutscene","cinematic","chapter","transition"),
    ("updraft_mps","above",3., "sky_island_height_m","above",140.,
     "apply_gameplay_effect","character","traveler","altitude_lift"),
    ("humidity","above",.62, "ground_ice_fraction","below",.3,
     "trigger_foliage_fx","environment","habitat","regrowth"),
    ("quest_progress","at_least",.8, "npc_reputation","above",5.,
     "advance_quest","quest","active","alternative_end"),
)
if len(FINISHES) != 10 or len(FINISH_EFFECTS) != 10 or len(set(FINISHES)) != 10:
    raise RuntimeError("final production passes must have ten executable owners")


class FinalProductionActions(Sequence[str]):
    """Arithmetic 450,000 directed actions × ten source-finishing strategies."""
    __slots__ = ()

    def __len__(self) -> int:
        return len(DIRECTED_ACTIONS) * len(FINISHES)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("production command index must be an integer")
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError("game production index is outside the registered catalog")
        owner, treatment = divmod(index, len(FINISHES))
        return ("complete_" + DIRECTED_ACTIONS[owner].removeprefix("direct_")
                + "_____" + FINISHES[treatment])

    def __contains__(self, candidate: object) -> bool:
        if type(candidate) is not str or not candidate.startswith("complete_"):
            return False
        stem, sep, finish = candidate[len("complete_"):].rpartition("_____")
        if not sep or finish not in FINISHES:
            return False
        return "direct_" + stem in DIRECTED_ACTIONS

    def __iter__(self):
        for source in DIRECTED_ACTIONS:
            prefix="complete_"+source.removeprefix("direct_")+"_____"
            for name in FINISHES:
                yield prefix+name


FINAL_PRODUCTION_ACTIONS = FinalProductionActions()
if len(FINAL_PRODUCTION_ACTIONS) != 4_500_000:
    raise RuntimeError("production completion catalog must contain 4.5M exact workflows")


def _owner(action: str) -> tuple[str,int]:
    if action not in FINAL_PRODUCTION_ACTIONS:
        raise StudioError("unknown or unauthorized final-game production")
    stem, name = action[len("complete_"):].rsplit("_____",1)
    return "direct_"+stem, FINISHES.index(name)


def describe_final_action(action: str) -> dict[str,Any]:
    source, k = _owner(action)
    return {
        **describe_direction(source),
        "operation":action,
        "base_operation":source,
        "finish":FINISHES[k],
        "finish_index":k,
        "finish_objective":FINISH_OBJECTIVES[k],
        "actual_project_mutation":True,
        "production_outputs":["map_cells","rpg_page","new_cast_if_present","new_quest_if_present"],
    }


def search_final_actions(*, query: str="", domain: str="", system_layer: str="",
                         director: str="", finish: str="",
                         offset: int=0, limit: int=32) -> dict[str,Any]:
    """Indexed browse without enumerating 4.5M names; filtered text search bounded."""
    if (type(query) is not str or len(query)>96 or
        type(domain) is not str or len(domain)>32 or
        type(system_layer) is not str or len(system_layer)>32 or
        type(director) is not str or len(director)>40 or
        type(finish) is not str or len(finish)>40 or
        domain and domain not in {d for d,_,_ in _DOMAINS} or
        system_layer and system_layer not in GAMEPLAY_LAYERS or
        director and director not in DIRECTORS or
        finish and finish not in FINISHES or
        type(offset) is not int or not 0<=offset<=len(FINAL_PRODUCTION_ACTIONS) or
        type(limit) is not int or not 1<=limit<=64):
        raise StudioError("invalid indexed five-million-operation producer query")
    q=query.strip().lower()
    domains=tuple(i for i,d in enumerate(_DOMAINS) if not domain or d[0]==domain)
    systems=tuple(i for i,s in enumerate(GAMEPLAY_LAYERS) if not system_layer or s==system_layer)
    directors=tuple(i for i,s in enumerate(DIRECTORS) if not director or s==director)
    finishes=tuple(i for i,s in enumerate(FINISHES) if not finish or s==finish)
    # Without full-text filtering, every page resolves at O(page-size), not
    # O(catalog-size). Rank order preserves exact virtual source ordering.
    block_size=450*9*len(systems)*len(directors)*len(finishes)
    total=len(domains)*block_size
    output=[]
    if not q:
        for position in range(offset,min(total,offset+limit)):
            d,remaining=divmod(position,block_size)
            archetype,remaining=divmod(remaining,
                9*len(systems)*len(directors)*len(finishes))
            treatment,remaining=divmod(remaining,
                len(systems)*len(directors)*len(finishes))
            system,remaining=divmod(remaining,len(directors)*len(finishes))
            director_idx,finish_idx=divmod(remaining,len(finishes))
            source_recipe_idx=domains[d]*450+archetype*9+treatment
            source_idx=(source_recipe_idx*10+systems[system])*10+directors[director_idx]
            action_index=source_idx*10+finishes[finish_idx]
            output.append(describe_final_action(FINAL_PRODUCTION_ACTIONS[action_index]))
        count=total
    else:
        # Expose the full-text option explicitly without serializing millions
        # of metadata records. It visits eligible exact filtered combinations.
        count=0
        for d in domains:
            for archetype in range(50):
                for treatment in range(9):
                    source_recipe_idx=d*450+(archetype*9+treatment)
                    for system in systems:
                        for director_idx in directors:
                            source_idx=(source_recipe_idx*10+system)*10+director_idx
                            action_prefix=("complete_"
                                + DIRECTED_ACTIONS[source_idx].removeprefix("direct_")+"_____")
                            for finish_idx in finishes:
                                name=action_prefix+FINISHES[finish_idx]
                                if q not in name:
                                    continue
                                if offset<=count<offset+limit:
                                    output.append(describe_final_action(name))
                                count+=1
    return {
        "schema":"skeleton.forge.production_recipe_search.v1",
        "total_catalog":len(FINAL_PRODUCTION_ACTIONS),
        "matched":count,"offset":offset,"limit":limit,
        "next_offset":offset+limit if offset+limit<count else None,
        "domains":[d for d,_,_ in _DOMAINS],
        "styles":list(TREATMENTS),
        "system_layers":list(GAMEPLAY_LAYERS),
        "directors":list(DIRECTORS),
        "finishes":list(FINISHES),
        "items":output,
    }


def _finish_topology(project:StudioProject,args:Mapping[str,Any],kind:int)->StudioProject:
    index,layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor,wall=_tile(layer,args,"floor"),_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("world finishing requires distinct actual tile palette indexes")
    seed=args.get("seed")
    if type(seed) is not int or not 0<=seed<=2**63-1:
        raise StudioError("world finishing requires a finite deterministic integer seed")
    cx,cy=x0+(w-1)/2,y0+(h-1)/2
    tiles=list(layer.data)
    for y in range(y0,y0+h):
        for x in range(x0,x0+w):
            dx,dy=x-cx,y-cy
            r=math.hypot(dx,dy)
            if kind==0:
                altered=abs(dy-math.sin(dx*.36+seed%11)*2)<=1.2
                index_value=floor
            elif kind==1:
                altered=(x+y+seed%7)%5<=1
                index_value=floor
            elif kind==2:
                altered=(x*11+y*7+seed%13)%17<=3
                index_value=wall
            elif kind==3:
                altered=abs(dx*2+dy)<=1 or (x+y)%6==0
                index_value=floor
            elif kind==4:
                altered=abs(r-min(w,h)/3)<=1.1
                index_value=wall
            elif kind==5:
                altered=(x-x0)%4==0 or (y-y0)%4==0
                index_value=floor
            elif kind==6:
                altered=abs(dy-math.sin(dx*.7)*2)<=1
                index_value=floor
            elif kind==7:
                altered=abs(r-min(w,h)/3)<=1.2 or abs(dx)<=.5
                index_value=floor
            elif kind==8:
                altered=(x*17+y*3+seed%9)%19<=4
                index_value=wall
            else:
                altered=abs(dx+dy)<=1 or abs(dx-dy)<=1
                index_value=floor
            if altered:
                tiles[y*layer.width+x]=index_value
    return _replace_layer(project,index,replace(layer,data=tuple(tiles)))


def _finish_page(project:StudioProject,action:str,args:Mapping[str,Any],kind:int)->StudioProject:
    instance=args.get("instance_id","a")
    if (type(instance) is not str or not 1<=len(instance)<=16 or
        not instance[0].isalpha() or
        any(not(x.isalnum() or x=="_") for x in instance)):
        raise StudioError("final-scene instance identity must be bounded and stable")
    page_id="finish_"+sha256(action.encode("utf-8")).hexdigest()[:28]+"_"+instance
    if page_id in {e.event_id for e in project.events}|{p.page_id for p in project.environmental_pages}:
        raise StudioError("final-scene page already belongs to this project")
    signal1,comp1,v1,signal2,comp2,v2,k,channel,target,value=FINISH_EFFECTS[kind]
    page=RPGEventPage(page_id,30+kind,
        (EnvironmentalTrigger(signal1,comp1,v1),
         EnvironmentalTrigger(signal2,comp2,v2)),
        (RPGEventAction(k,channel,target,value),),cooldown_ms=1000*(kind+1))
    return replace(project,environmental_pages=project.environmental_pages+(page,))


def _finish_cast(project:StudioProject,prior:int,kind:int)->StudioProject:
    if len(project.placements)<=prior:
        return project
    actors=list(project.placements)
    number=len(actors)-prior
    for idx in range(prior,len(actors)):
        actor=actors[idx]
        step=idx-prior
        angle=step*math.tau/max(1,number)
        if kind==0: actors[idx]=replace(actor,facing_deg=(actor.facing_deg+60)%360)
        elif kind==1: actors[idx]=replace(actor,x=actor.x+2*math.cos(angle),y=actor.y+2*math.sin(angle))
        elif kind==2: actors[idx]=replace(actor,z=actor.z+step*.4)
        elif kind==3: actors[idx]=replace(actor,x=actor.x+step*1.1)
        elif kind==4: actors[idx]=replace(actor,facing_deg=(actor.facing_deg+180)%360)
        elif kind==5: actors[idx]=replace(actor,y=actor.y+step*1.3)
        elif kind==6: actors[idx]=replace(actor,facing_deg=(step*90)%360)
        elif kind==7: actors[idx]=replace(actor,z=actor.z+5+step*.5)
        elif kind==8: actors[idx]=replace(actor,x=actor.x+step*.6,y=actor.y-step*.4)
        else: actors[idx]=replace(actor,y=actor.y+math.sin(angle)*3)
    return replace(project,placements=tuple(actors))


def _finish_story(project:StudioProject,prior:int,kind:int,action:str)->StudioProject:
    if len(project.native_quests)<=prior:
        return project
    quests=list(project.native_quests)
    suffix=sha256(action.encode("utf-8")).hexdigest()[:12]
    for i in range(prior,len(quests)):
        quest=quests[i]
        root=quest.stages[0]
        terminal=next((s.stage_id for s in reversed(quest.stages) if not s.next_stage_ids),None)
        if terminal is None or len(root.next_stage_ids)>=32:
            raise StudioError("quest finishing needs an accessible ending and branch capacity")
        scene_id=quest.quest_id+"_fin_"+suffix
        if len(scene_id)>128 or scene_id in {s.stage_id for s in quest.stages}:
            raise StudioError("final quest stage source identity collision")
        stage=StudioQuestStage(scene_id,FINISH_OBJECTIVES[kind],(terminal,))
        quests[i]=replace(quest,stages=(
            replace(root,next_stage_ids=root.next_stage_ids+(scene_id,)),
            *quest.stages[1:],stage))
    return replace(project,native_quests=tuple(quests))


def edit_final_production(
    project:StudioProject,action:str,args:Mapping[str,Any],
    perform:Callable[[StudioProject,str,Mapping[str,Any]],StudioProject],
)->StudioProject:
    """Execute exact trusted directed producer plus further real game edits."""
    if (not isinstance(project,StudioProject) or
        type(action) is not str or action not in FINAL_PRODUCTION_ACTIONS or
        not isinstance(args,Mapping) or not callable(perform)):
        raise StudioError("unknown final original-game production workflow")
    parent,finish=_owner(action)
    original_actor_count=len(project.placements)
    original_quest_count=len(project.native_quests)
    candidate=perform(project,parent,args)
    candidate=_finish_topology(candidate,args,finish)
    candidate=_finish_page(candidate,action,args,finish)
    candidate=_finish_cast(candidate,original_actor_count,finish)
    candidate=_finish_story(candidate,original_quest_count,finish,action)
    return candidate
