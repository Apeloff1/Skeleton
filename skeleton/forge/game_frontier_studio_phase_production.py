"""450,000,000 executable phased-game production compositions.

A phase executes one exact existing worldline authoring workflow, creates its
own deterministic gameplay MapLayer topology, appends an independent measured
RPG event action proposal, and refines only actor/quest records produced in
this transaction. No new project store, dynamic command execution or provider.
The operation count measures *compositions*, not independent game engines.
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
from .game_frontier_studio_worldline_production import WORLDLINE_ACTIONS, WORLDLINES
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_final_production import FINISHES

PHASES = (
    "dawn_routes", "winter_crossings", "storm_shelters",
    "market_cycles", "siege_fronts", "night_patrols",
    "habitat_migrations", "sky_transits", "faction_turns",
    "ending_convergence",
)
PHASE_OBJECTIVES = (
    "Reach the first-lit road without blocking the inhabited district",
    "Traverse a thawing winter crossing with an alternative route",
    "Find a shelter and receive observed incoming storm conditions",
    "Reach a populated marketplace by a connected supply street",
    "Choose a defensible approach while retaining an escape corridor",
    "Avoid the nightly sentry lines while keeping civilian routes open",
    "Follow an independent safe wildlife migration corridor",
    "Reach the next elevated island using surveyed skyward guidance",
    "Resolve competing loyalties without rewriting existing characters",
    "Conclude a reachable alternative chapter without losing earlier endings",
)
PHASE_EFFECTS = (
    ("solar_height","above",5., "fog_visibility_m","below",350.,
     "inspect_instrument","ui","navigator","morning_route"),
    ("temperature_c","below",2., "ground_ice_fraction","above",.25,
     "change_light","environment","winter_crossing","thaw"),
    ("wind_mps","above",12., "rain_mm_h","above",4.,
     "weather_transition","environment","storm_front","shelter"),
    ("npc_reputation","above",10., "quest_progress","above",.2,
     "open_shop","character","merchant","market_cycle"),
    ("native_contact_count","above",0., "party_morale","below",.65,
     "start_combat","character","encounter","siege_phase"),
    ("daylight","below",.25, "sound_occlusion","above",.5,
     "set_flag","world","hidden_route","night_patrol"),
    ("humidity","above",.58, "soil_wetness","above",.33,
     "trigger_foliage_fx","environment","habitat","migration"),
    ("updraft_mps","above",3., "sky_island_height_m","above",140.,
     "apply_gameplay_effect","character","traveler","sky_route"),
    ("npc_reputation","above",20., "party_morale","above",.4,
     "set_faction_reputation","character","alliances","turn"),
    ("quest_progress","at_least",.8, "npc_reputation","above",5.,
     "advance_quest","quest","original_chapter","ending"),
)
if len(PHASES)!=10 or len(set(PHASES))!=10 or len(PHASE_EFFECTS)!=10:
    raise RuntimeError("phased production needs ten original source transforms")


class PhaseActions(Sequence[str]):
    """Virtual index over 45M worldlines × ten spatial/gameplay phases."""
    __slots__=()
    def __len__(self):
        return len(WORLDLINE_ACTIONS)*len(PHASES)
    def __getitem__(self,index):
        if isinstance(index,slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("phase catalog index must be integer")
        if index<0: index+=len(self)
        if not 0<=index<len(self):
            raise IndexError("phase game authoring identity outside catalog")
        parent,phase=divmod(index,len(PHASES))
        return "phase_"+WORLDLINE_ACTIONS[parent].removeprefix("worldline_")+"_______"+PHASES[phase]
    def __contains__(self,name:object)->bool:
        if type(name) is not str or not name.startswith("phase_"):
            return False
        stem,mark,phase=name[6:].rpartition("_______")
        return bool(mark and phase in PHASES and "worldline_"+stem in WORLDLINE_ACTIONS)
    def __iter__(self):
        for base in WORLDLINE_ACTIONS:
            stem="phase_"+base.removeprefix("worldline_")+"_______"
            for phase in PHASES:
                yield stem+phase


PHASE_ACTIONS=PhaseActions()
if len(PHASE_ACTIONS)!=450_000_000:
    raise RuntimeError("450M original game phase contracts required")


def _parent(name:str)->tuple[str,int]:
    if name not in PHASE_ACTIONS:
        raise StudioError("unknown or unauthorized game production phase")
    stem,phase=name[6:].rsplit("_______",1)
    return "worldline_"+stem,PHASES.index(phase)


def describe_phase(name:str)->dict[str,Any]:
    from .game_frontier_studio_worldline_production import describe_worldline
    base,index=_parent(name)
    return {**describe_worldline(base),
            "operation":name,"base_operation":base,
            "phase":PHASES[index],"phase_index":index,
            "phase_objective":PHASE_OBJECTIVES[index],
            "actual_project_mutation":True,
            "production_outputs":["map_cells","observed_rpg_page","new_cast_and_quest_if_present"]}


def search_phases(*,query:str="",domain:str="",system_layer:str="",
                  director:str="",finish:str="",worldline:str="",phase:str="",
                  offset:int=0,limit:int=32)->dict[str,Any]:
    """O(page-size) unfiltered/category search, no 450M-name scan.

    Text search is deliberately restricted to one exact domain/director/
    worldline/phase and remains bounded in memory.
    """
    if (type(query) is not str or len(query)>96 or
        type(domain) is not str or len(domain)>32 or
        type(system_layer) is not str or len(system_layer)>32 or
        type(director) is not str or len(director)>40 or
        type(finish) is not str or len(finish)>40 or
        type(worldline) is not str or len(worldline)>40 or
        type(phase) is not str or len(phase)>40 or
        (domain and domain not in {r[0] for r in _DOMAINS}) or
        (system_layer and system_layer not in GAMEPLAY_LAYERS) or
        (director and director not in DIRECTORS) or
        (finish and finish not in FINISHES) or
        (worldline and worldline not in WORLDLINES) or
        (phase and phase not in PHASES) or
        type(offset) is not int or not 0<=offset<=len(PHASE_ACTIONS) or
        type(limit) is not int or not 1<=limit<=64):
        raise StudioError("invalid bounded 500M original-game production search")
    q=query.strip().lower()
    if q and not (domain and director and worldline and phase):
        raise StudioError("full-text source search requires domain, director, worldline and phase")
    ds=tuple(i for i,r in enumerate(_DOMAINS) if not domain or r[0]==domain)
    ss=tuple(i for i,r in enumerate(GAMEPLAY_LAYERS) if not system_layer or r==system_layer)
    rs=tuple(i for i,r in enumerate(DIRECTORS) if not director or r==director)
    fs=tuple(i for i,r in enumerate(FINISHES) if not finish or r==finish)
    ws=tuple(i for i,r in enumerate(WORLDLINES) if not worldline or r==worldline)
    ps=tuple(i for i,r in enumerate(PHASES) if not phase or r==phase)
    per_recipe=len(ss)*len(rs)*len(fs)*len(ws)*len(ps)
    per_domain=450*per_recipe
    count=len(ds)*per_domain
    items=[]
    if not q:
        for rank in range(offset,min(count,offset+limit)):
            d,part=divmod(rank,per_domain)
            recipe,part=divmod(part,per_recipe)
            system,part=divmod(part,len(rs)*len(fs)*len(ws)*len(ps))
            director_idx,part=divmod(part,len(fs)*len(ws)*len(ps))
            finish_idx,part=divmod(part,len(ws)*len(ps))
            worldline_idx,phase_idx=divmod(part,len(ps))
            action_idx=((((((ds[d]*450+recipe)*10+ss[system])*10+
                           rs[director_idx])*10+fs[finish_idx])*10+
                           ws[worldline_idx])*10+ps[phase_idx])
            items.append(describe_phase(PHASE_ACTIONS[action_idx]))
        matched=count
    else:
        # Narrowed search scans only a defined category and builds page items.
        matched=0
        for d in ds:
            for recipe in range(450):
                for system in ss:
                    for director_idx in rs:
                        for finish_idx in fs:
                            for worldline_idx in ws:
                                for phase_idx in ps:
                                    rank=((((((d*450+recipe)*10+system)*10+director_idx)
                                             *10+finish_idx)*10+worldline_idx)*10+phase_idx)
                                    operation=PHASE_ACTIONS[rank]
                                    if q not in operation: continue
                                    if offset<=matched<offset+limit:
                                        items.append(describe_phase(operation))
                                    matched+=1
    return {
        "schema":"skeleton.forge.production_recipe_search.v1",
        "total_catalog":len(PHASE_ACTIONS),"matched":matched,
        "offset":offset,"limit":limit,
        "next_offset":offset+limit if offset+limit<matched else None,
        "domains":[r[0] for r in _DOMAINS],"styles":list(TREATMENTS),
        "system_layers":list(GAMEPLAY_LAYERS),"directors":list(DIRECTORS),
        "finishes":list(FINISHES),"worldlines":list(WORLDLINES),
        "phases":list(PHASES),"items":items,
    }


def _paint_phase(project:StudioProject,args:Mapping[str,Any],axis:int)->StudioProject:
    layer_i,layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor=_tile(layer,args,"floor")
    wall=_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("phased world construction needs distinct palette tiles")
    seed=args.get("seed")
    if type(seed) is not int or not 0<=seed<=2**63-1:
        raise StudioError("phased geometry requires deterministic valid seed")
    tiles=list(layer.data)
    cx,cy=x0+(w-1)/2,y0+(h-1)/2
    for y in range(y0,y0+h):
        for x in range(x0,x0+w):
            dx,dy=x-cx,y-cy
            r=math.hypot(dx,dy)
            if axis==0:
                painted=abs(dy-2*math.sin(dx*.3+seed%5))<=1
                tile=floor
            elif axis==1:
                painted=(x+y+seed%7)%6<=1
                tile=wall
            elif axis==2:
                painted=abs(dx)<=1 or abs(r-min(w,h)/4)<1
                tile=floor
            elif axis==3:
                painted=(x-x0)%5==0 or (y-y0)%5==0
                tile=floor
            elif axis==4:
                painted=abs(r-min(w,h)/3)<1.2
                tile=wall
            elif axis==5:
                painted=abs(dx+dy)<=1 or (x*3+y*7)%11==0
                tile=wall if abs(dx+dy)>1 else floor
            elif axis==6:
                painted=(x*11+y*13+seed%9)%19<4
                tile=wall
            elif axis==7:
                painted=abs(r-min(w,h)/3)<=1 or abs(dy)<=.5
                tile=floor
            elif axis==8:
                painted=(x*5+y*3+seed%7)%13<3
                tile=floor
            else:
                painted=abs(dx-dy)<=1 or abs(dx+dy)<=1
                tile=floor
            if painted:
                tiles[y*layer.width+x]=tile
    return _replace_layer(project,layer_i,replace(layer,data=tuple(tiles)))


def _event(project:StudioProject,name:str,args:Mapping[str,Any],axis:int)->StudioProject:
    instance=args.get("instance_id","a")
    if (type(instance) is not str or not 1<=len(instance)<=16
        or not instance[0].isalpha()
        or any(not (c.isalnum() or c=="_") for c in instance)):
        raise StudioError("phased scene needs valid stable instance identity")
    page_id="phase_"+sha256(name.encode("utf8")).hexdigest()[:24]+"_"+instance
    if page_id in {p.page_id for p in project.environmental_pages}|{
        e.event_id for e in project.events}:
        raise StudioError("phased scene already exists")
    e=PHASE_EFFECTS[axis]
    page=RPGEventPage(page_id,51+axis,
        (EnvironmentalTrigger(e[0],e[1],e[2]),
         EnvironmentalTrigger(e[3],e[4],e[5])),
        (RPGEventAction(*e[6:]),),cooldown_ms=1000*(axis+1))
    return replace(project,environmental_pages=project.environmental_pages+(page,))


def _cast(project:StudioProject,prior:int,axis:int)->StudioProject:
    if len(project.placements)<=prior: return project
    actors=list(project.placements)
    for i in range(prior,len(actors)):
        p=actors[i]
        n=i-prior
        if axis==0: actors[i]=replace(p,facing_deg=(p.facing_deg+90)%360)
        elif axis==1: actors[i]=replace(p,z=p.z+n*.25)
        elif axis==2: actors[i]=replace(p,x=p.x+n*.65)
        elif axis==3: actors[i]=replace(p,y=p.y+n*1.2)
        elif axis==4: actors[i]=replace(p,facing_deg=(p.facing_deg+180)%360)
        elif axis==5: actors[i]=replace(p,y=p.y-n*.5)
        elif axis==6: actors[i]=replace(p,x=p.x+math.sin(n)*1.5)
        elif axis==7: actors[i]=replace(p,z=p.z+2+n*.5)
        elif axis==8: actors[i]=replace(p,facing_deg=(n*45)%360)
        else: actors[i]=replace(p,x=p.x+n*.4,y=p.y+n*.4)
    return replace(project,placements=tuple(actors))


def _story(project:StudioProject,prior:int,axis:int,name:str)->StudioProject:
    if len(project.native_quests)<=prior: return project
    quests=list(project.native_quests)
    suffix=sha256(name.encode("utf8")).hexdigest()[:12]
    for i in range(prior,len(quests)):
        quest=quests[i]
        root=quest.stages[0]
        terminal=next((s.stage_id for s in reversed(quest.stages)
                       if not s.next_stage_ids),None)
        if terminal is None or len(root.next_stage_ids)>=32:
            raise StudioError("phased quest has no reachable terminal or branch capacity")
        stage_id=quest.quest_id+"_ph_"+suffix
        if len(stage_id)>128 or stage_id in {s.stage_id for s in quest.stages}:
            raise StudioError("phase quest stage identity collision")
        stage=StudioQuestStage(stage_id,PHASE_OBJECTIVES[axis],(terminal,))
        quests[i]=replace(quest,stages=(
            replace(root,next_stage_ids=root.next_stage_ids+(stage_id,)),
            *quest.stages[1:],stage))
    return replace(project,native_quests=tuple(quests))


def edit_phase(project:StudioProject,name:str,args:Mapping[str,Any],
               execute:Callable[[StudioProject,str,Mapping[str,Any]],StudioProject]
              )->StudioProject:
    if (not isinstance(project,StudioProject) or type(name) is not str
        or name not in PHASE_ACTIONS or not isinstance(args,Mapping)
        or not callable(execute)):
        raise StudioError("unsupported phased original-game production")
    base,index=_parent(name)
    cast_count=len(project.placements)
    quest_count=len(project.native_quests)
    result=execute(project,base,args)
    result=_paint_phase(result,args,index)
    result=_event(result,name,args,index)
    result=_cast(result,cast_count,index)
    result=_story(result,quest_count,index,name)
    return result
