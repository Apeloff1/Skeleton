"""4.5B registered campaign compositions with ten real source edits per axis family.

Each campaign step executes its exact phase-owned real game producer, adds a
deterministic layer edit, one independent observed RPG page, and refines only
the newly authored cast/quest graph. These are 4.5 billion *combinations* of
canonical production tools, not independent engines or finished games.

The virtual catalog never allocates billions of strings.
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
from .game_frontier_studio_phase_production import PHASE_ACTIONS, PHASES
from .game_frontier_studio_worldline_production import WORLDLINES
from .game_frontier_studio_final_production import FINISHES
from .game_frontier_studio_directed_production import DIRECTORS
from .game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from .game_frontier_studio_production_recipes import _DOMAINS, TREATMENTS

CAMPAIGNS = (
    "chapter_crossroads", "civic_worlds", "open_ocean_routes",
    "sky_island_circuit", "underground_transit", "faction_frontiers",
    "siege_campaigns", "ecological_chains", "cinematic_sequences",
    "epilogue_variants",
)
OBJECTIVES = (
    "Compare two traversable plot approaches without losing the original route",
    "Stage a living market district with civilian encounters",
    "Connect an oceanic crossing to an inland return path",
    "Survey the aerial network and preserve reachable landing routes",
    "Traverse a tunnel junction with a distinct emergency exit",
    "Open an alliance route while preserving opposed faction choices",
    "Cross a guarded perimeter with a noncombat escape alternative",
    "Protect migrating creatures through a seasonal habitat crossing",
    "Stage the original chapter reveal with verified framing and timing",
    "Close one new alternative ending while preserving prior canon",
)
EFFECTS = (
    ("quest_progress","above",.25,"npc_reputation","above",5.,
     "advance_quest","quest","campaign","crossroads"),
    ("party_morale","above",.4,"npc_reputation","above",10.,
     "set_npc_emotion","character","civic_cast","welcome"),
    ("tide_height_m","above",.5,"water_depth_m","above",1.,
     "inspect_instrument","ui","navigator","ocean_crossing"),
    ("updraft_mps","above",2.,"sky_island_height_m","above",110.,
     "apply_gameplay_effect","character","traveler","sky_passage"),
    ("fog_visibility_m","below",170.,"altitude_m","below",50.,
     "inspect_instrument","ui","map","tunnel_route"),
    ("npc_reputation","above",20.,"party_morale","above",.5,
     "set_faction_reputation","character","alliances","route"),
    ("native_contact_count","above",0.,"party_morale","below",.75,
     "start_combat","character","encounter","siege"),
    ("humidity","above",.55,"soil_wetness","above",.3,
     "trigger_foliage_fx","environment","habitat","restoration"),
    ("music_intensity","above",.5,"daylight","below",.7,
     "play_cutscene","cinematic","campaign_scene","reveal"),
    ("quest_progress","at_least",.9,"npc_reputation","above",5.,
     "advance_quest","quest","campaign","epilogue"),
)
if len(CAMPAIGNS)!=10 or len(EFFECTS)!=10 or len(set(CAMPAIGNS))!=10:
    raise RuntimeError("campaign authoring requires ten unique producer implementations")


class CampaignActions(Sequence[str]):
    __slots__=()
    def __len__(self):
        return len(PHASE_ACTIONS)*len(CAMPAIGNS)
    def __getitem__(self,index):
        if isinstance(index,slice):
            return tuple(self[i] for i in range(*index.indices(len(self))))
        if type(index) is not int:
            raise TypeError("game campaign catalog indexes must be integer")
        if index<0:
            index+=len(self)
        if not 0<=index<len(self):
            raise IndexError("campaign operation outside registered catalog")
        owner,axis=divmod(index,10)
        return "campaign_"+PHASE_ACTIONS[owner].removeprefix("phase_")+"________"+CAMPAIGNS[axis]
    def __contains__(self,value:object)->bool:
        if type(value) is not str or not value.startswith("campaign_"):
            return False
        stem,sep,axis=value[9:].rpartition("________")
        return bool(sep and axis in CAMPAIGNS and "phase_"+stem in PHASE_ACTIONS)
    def __iter__(self):
        for parent in PHASE_ACTIONS:
            stem="campaign_"+parent.removeprefix("phase_")+"________"
            for axis in CAMPAIGNS:
                yield stem+axis


CAMPAIGN_ACTIONS=CampaignActions()
if len(CAMPAIGN_ACTIONS)!=4_500_000_000:
    raise RuntimeError("campaign registry must expose 4.5 billion exact compositions")


def parent_action(operation:str)->tuple[str,int]:
    if operation not in CAMPAIGN_ACTIONS:
        raise StudioError("unknown campaign authoring identity")
    stem,axis=operation[9:].rsplit("________",1)
    return "phase_"+stem,CAMPAIGNS.index(axis)


def describe_campaign(operation:str)->dict[str,Any]:
    from .game_frontier_studio_phase_production import describe_phase
    parent,axis=parent_action(operation)
    return {**describe_phase(parent),"operation":operation,
            "base_operation":parent,"campaign":CAMPAIGNS[axis],
            "campaign_index":axis,"campaign_objective":OBJECTIVES[axis],
            "actual_project_mutation":True,
            "source_outputs":["real_map_cells","sensor_gameplay_page",
                              "new_actors_when_present","new_quests_when_present"]}


def search_campaigns(*,domain:str="",system_layer:str="",director:str="",
                     finish:str="",worldline:str="",phase:str="",campaign:str="",
                     offset:int=0,limit:int=32)->dict[str,Any]:
    """O(page) categorical discovery; deliberately no billions-scale text scan."""
    strings=(domain,system_layer,director,finish,worldline,phase,campaign)
    catalogs=(tuple(r[0] for r in _DOMAINS),GAMEPLAY_LAYERS,DIRECTORS,
              FINISHES,WORLDLINES,PHASES,CAMPAIGNS)
    if (any(type(v) is not str or len(v)>40 or (v and v not in catalog)
            for v,catalog in zip(strings,catalogs)) or
        type(offset) is not int or not 0<=offset<=len(CAMPAIGN_ACTIONS) or
        type(limit) is not int or not 1<=limit<=64):
        raise StudioError("invalid bounded game campaign search")
    selected=tuple(tuple(i for i,item in enumerate(catalog)
                         if not val or val==item)
                   for val,catalog in zip(strings,catalogs))
    ds,ss,rs,fs,ws,ps,cs=selected
    dims=(len(ss),len(rs),len(fs),len(ws),len(ps),len(cs))
    stride=1
    for n in dims:
        stride*=n
    per_domain=450*stride
    matched=len(ds)*per_domain
    out=[]
    for k in range(offset,min(matched,offset+limit)):
        d,rem=divmod(k,per_domain)
        recipe,rem=divmod(rem,stride)
        indexes=[0]*len(dims)
        for i in range(len(dims)-1,-1,-1):
            rem,indexes[i]=divmod(rem,dims[i])
        source=ds[d]*450+recipe
        for selected_index,allowed in zip(indexes,(ss,rs,fs,ws,ps,cs)):
            source=source*10+allowed[selected_index]
        out.append(describe_campaign(CAMPAIGN_ACTIONS[source]))
    return {"schema":"skeleton.forge.production_recipe_search.v1",
            "total_catalog":len(CAMPAIGN_ACTIONS),"matched":matched,
            "offset":offset,"limit":limit,
            "next_offset":offset+limit if offset+limit<matched else None,
            "domains":list(catalogs[0]),"styles":list(TREATMENTS),
            "system_layers":list(GAMEPLAY_LAYERS),"directors":list(DIRECTORS),
            "finishes":list(FINISHES),"worldlines":list(WORLDLINES),
            "phases":list(PHASES),"campaigns":list(CAMPAIGNS),"items":out}


def _paint(project:StudioProject,args:Mapping[str,Any],axis:int)->StudioProject:
    index,layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor=_tile(layer,args,"floor")
    wall=_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("campaign requires distinct source palette indices")
    seed=args.get("seed")
    if type(seed) is not int or not 0<=seed<=2**63-1:
        raise StudioError("campaign needs bounded reproducible integer seed")
    cx,cy=x0+(w-1)/2,y0+(h-1)/2
    tiles=list(layer.data)
    for y in range(y0,y0+h):
        for x in range(x0,x0+w):
            u,v=x-cx,y-cy
            r=math.hypot(u,v)
            if axis==0: chosen,tile=abs(u-v)<=1 or abs(u+v)<=1,floor
            elif axis==1: chosen,tile=((x-x0)%4==0 or (y-y0)%4==0),floor
            elif axis==2: chosen,tile=abs(v-math.sin(u*.31+seed%7)*2)<=1,floor
            elif axis==3: chosen,tile=abs(r-min(w,h)/3)<=1 or abs(v)<=.5,floor
            elif axis==4: chosen,tile=(x*11+y*3+seed%13)%19<4,wall
            elif axis==5: chosen,tile=abs(u)<=1 or (x+y+seed%7)%8==0,floor
            elif axis==6: chosen,tile=abs(r-min(w,h)/3)<=1.4,wall
            elif axis==7: chosen,tile=(x*17+y*7+seed%11)%23<5,wall
            elif axis==8: chosen,tile=abs(v-2*math.sin(u*.5))<=1,floor
            else: chosen,tile=abs(u+v)<=1 or abs(u-v)<=1,floor
            if chosen:
                tiles[y*layer.width+x]=tile
    return _replace_layer(project,index,replace(layer,data=tuple(tiles)))


def _page(project:StudioProject,operation:str,args:Mapping[str,Any],axis:int)->StudioProject:
    instance=args.get("instance_id","a")
    if (type(instance) is not str or not 1<=len(instance)<=16 or
        not instance[0].isalpha() or
        any(not (c.isalnum() or c=="_") for c in instance)):
        raise StudioError("campaign source identity is malformed")
    key="campaign_"+sha256(operation.encode("utf8")).hexdigest()[:24]+"_"+instance
    if key in {p.page_id for p in project.environmental_pages}|{
        e.event_id for e in project.events}:
        raise StudioError("duplicate campaign event id")
    sig=EFFECTS[axis]
    page=RPGEventPage(key,61+axis,
        (EnvironmentalTrigger(sig[0],sig[1],sig[2]),
         EnvironmentalTrigger(sig[3],sig[4],sig[5])),
        (RPGEventAction(*sig[6:]),),cooldown_ms=1000*(axis+1))
    return replace(project,environmental_pages=project.environmental_pages+(page,))


def _cast(project:StudioProject,original_count:int,axis:int)->StudioProject:
    if len(project.placements)<=original_count:
        return project
    cast=list(project.placements)
    for i in range(original_count,len(cast)):
        actor=cast[i]
        n=i-original_count
        if axis==0: cast[i]=replace(actor,x=actor.x+n*.5)
        elif axis==1: cast[i]=replace(actor,y=actor.y+n*.6)
        elif axis==2: cast[i]=replace(actor,facing_deg=(actor.facing_deg+45)%360)
        elif axis==3: cast[i]=replace(actor,z=actor.z+3+n*.4)
        elif axis==4: cast[i]=replace(actor,z=actor.z-n*.3)
        elif axis==5: cast[i]=replace(actor,facing_deg=(actor.facing_deg+90)%360)
        elif axis==6: cast[i]=replace(actor,x=actor.x+n*.9)
        elif axis==7: cast[i]=replace(actor,y=actor.y+math.sin(n)*2)
        elif axis==8: cast[i]=replace(actor,facing_deg=(n*60)%360)
        else: cast[i]=replace(actor,x=actor.x+n*.5,y=actor.y+n*.5)
    return replace(project,placements=tuple(cast))


def _quest(project:StudioProject,original_count:int,axis:int,operation:str)->StudioProject:
    if len(project.native_quests)<=original_count:
        return project
    quests=list(project.native_quests)
    postfix=sha256(operation.encode("utf8")).hexdigest()[:12]
    for i in range(original_count,len(quests)):
        q=quests[i]
        root=q.stages[0]
        terminal=next((s.stage_id for s in reversed(q.stages) if not s.next_stage_ids),None)
        if terminal is None or len(root.next_stage_ids)>=32:
            raise StudioError("campaign chapter lacks an independent reachable ending")
        stage_id=q.quest_id+"_camp_"+postfix
        if len(stage_id)>128 or stage_id in {s.stage_id for s in q.stages}:
            raise StudioError("campaign quest stage identity collision")
        stage=StudioQuestStage(stage_id,OBJECTIVES[axis],(terminal,))
        quests[i]=replace(q,stages=(
            replace(root,next_stage_ids=root.next_stage_ids+(stage_id,)),
            *q.stages[1:],stage))
    return replace(project,native_quests=tuple(quests))


def edit_campaign(project:StudioProject,operation:str,args:Mapping[str,Any],
                  execute:Callable[[StudioProject,str,Mapping[str,Any]],StudioProject]
                  )->StudioProject:
    if (not isinstance(project,StudioProject) or type(operation) is not str
        or operation not in CAMPAIGN_ACTIONS or not isinstance(args,Mapping)
        or not callable(execute)):
        raise StudioError("unrecognized campaign source operation")
    parent,axis=parent_action(operation)
    ncast,nquests=len(project.placements),len(project.native_quests)
    candidate=execute(project,parent,args)
    candidate=_paint(candidate,args,axis)
    candidate=_page(candidate,operation,args,axis)
    candidate=_cast(candidate,ncast,axis)
    return _quest(candidate,nquests,axis,operation)
