"""Deterministic bounded quest-solving agent for native campaigns.

Unlike superficial reachability, this solver reasons over acquired keys,
opened doors, boss encounter obligations, and arena collectible routes.
It returns an explicit reproducible cell-by-cell abstract action trace.
No claim that native jump/physics or moving combat AI played successfully:
those require compiled-engine controller replay and independent playtest.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from heapq import heappop,heappush
import json
from .dragon_game_blueprints import Campaign,Stage,W,H

MAX_STATES=16000
MAX_ACTIONS=4000
DELTAS=((-1,0,"west"),(1,0,"east"),(0,-1,"north"),(0,1,"south"))

@dataclass(frozen=True)
class AgentAction:
    kind:str
    x:int
    y:int
    notes:str=""

@dataclass(frozen=True)
class StagePlan:
    stage_id:int
    mode:str
    achieved_exit:bool
    abstract_cost:int
    commands:tuple[AgentAction,...]
    visited_states:int
    keys_collected:int
    doors_opened:int
    guardian_encounters:int
    crystals_collected:int
    trace_digest:str
    limitations:tuple[str,...]
    schema:str="skeleton.ai.dragon.abstract_playplan.v1"

@dataclass(frozen=True)
class CampaignPlan:
    campaign_id:str
    all_abstract_routes_found:bool
    stages:tuple[StagePlan,...]
    trace_digest:str
    proof_scope:str="abstract state-space navigation, not runtime gameplay"

def _tiles(stage:Stage)->dict[tuple[int,int],str]:
    if len(stage.terrain)!=H or any(len(row)!=W for row in stage.terrain):
        raise ValueError("invalid native stage for the agent")
    result={(x,y):c for y,row in enumerate(stage.terrain) for x,c in enumerate(row)}
    if result.get(stage.start)!="S" or result.get(stage.goal)!="G":
        raise ValueError("agent spawn and exit mismatch")
    return result

def _weighted_route(tiles:dict,start:tuple[int,int],goal:tuple[int,int],
                    *,keys:int,door_open:bool,boss_alive:bool)->tuple[tuple[AgentAction,...],int]:
    enemies={(x,y) for (x,y),c in tiles.items() if c=="E"}
    # State: x,y,carried_key,ever_had_key,door_open,boss_defeated.
    initial=(start[0],start[1],keys,keys>0,door_open,not boss_alive)
    distance={initial:0}
    parent={}
    heap=[(0,initial)]
    explored=0
    final=None
    while heap and explored<MAX_STATES:
        cost,state=heappop(heap)
        if cost!=distance[state]:continue
        explored+=1
        x,y,key,had_key,opened,boss_done=state
        if (x,y)==goal and (not any(c=="K" for c in tiles.values()) or had_key)\
            and (not boss_alive or boss_done):
            final=state;break
        for dx,dy,direction in DELTAS:
            nx,ny=x+dx,y+dy
            if not 0<=nx<W or not 0<=ny<H:continue
            ch=tiles[(nx,ny)]
            if ch in "#^~":continue
            acquired=key
            ever=had_key
            door=opened
            defeated=boss_done
            action=[AgentAction("move_"+direction,nx,ny)]
            extra=1
            if ch=="D" and not opened:
                if acquired<=0:continue
                acquired-=1;door=True
                extra+=3;action.append(AgentAction("unlock_door",nx,ny))
            if ch=="K" and not ever:
                acquired+=1;ever=True
                action.append(AgentAction("collect_key",nx,ny))
            if ch=="B" and not defeated:
                extra+=12
                defeated=True
                action.append(AgentAction("abstract_guardian_encounter",nx,ny,
                               "Combat victory is assumed, not replay-verified"))
            if ch=="C":
                extra=max(1,extra-1)
                action.append(AgentAction("open_treasure",nx,ny))
            if ch=="N":
                action.append(AgentAction("greet_caretaker",nx,ny))
            pressure=sum(abs(ex-nx)+abs(ey-ny)<=2 for ex,ey in enemies)
            extra+=pressure*3
            next_state=(nx,ny,acquired,ever,door,defeated)
            new=cost+extra
            if new<distance.get(next_state,10**9):
                distance[next_state]=new
                parent[next_state]=(state,tuple(action))
                heappush(heap,(new,next_state))
    if final is None:
        raise ValueError("bounded quest-state search could not reach exit")
    route=[]
    step=final
    while step!=initial:
        prev,actions=parent[step]
        route.extend(reversed(actions))
        step=prev
    route.reverse()
    if len(route)>MAX_ACTIONS:
        raise ValueError("native practice agent exceeded action budget")
    return tuple(route),explored

def plan_stage(stage:Stage,mode:str)->StagePlan:
    if mode not in ("arena","platform","adventure","dungeon","tactics","racer"):
        raise ValueError("unsupported native navigation mode")
    tiles=_tiles(stage)
    commands=[]
    position=stage.start
    explored=0
    crystals=0
    # Arena portals require every original crystal. For other modes crystal
    # routes are optional and the bounded state-space search handles quest keys.
    if mode=="arena":
        remaining={position for position,value in tiles.items() if value=="*"}
        while remaining:
            choices=[]
            for crystal in sorted(remaining):
                try:
                    path,states=_weighted_route(tiles,position,crystal,
                                              keys=0,door_open=False,boss_alive=False)
                except ValueError:
                    continue
                choices.append((len(path),crystal,path,states))
            if not choices:raise ValueError("arena collectible is unreachable")
            _,target,path,states=min(choices,key=lambda x:(x[0],x[1]))
            commands.extend(path)
            commands.append(AgentAction("collect_crystal",target[0],target[1]))
            remaining.remove(target);crystals+=1;position=target
            explored+=states
    encounters=any(c=="B" for c in tiles.values())
    path,states=_weighted_route(tiles,position,stage.goal,
        keys=0,door_open=False,boss_alive=encounters)
    commands.extend(path)
    explored+=states
    commands.append(AgentAction("reach_exit",*stage.goal,
         "Abstract navigation; native collision/physics/combat not certified"))
    if len(commands)>MAX_ACTIONS or explored>MAX_STATES*15:
        raise ValueError("agent abstract plan exceeds bounded budget")
    key_count=sum(action.kind=="collect_key" for action in commands)
    door_count=sum(action.kind=="unlock_door" for action in commands)
    boss_count=sum(action.kind=="abstract_guardian_encounter" for action in commands)
    payload=[[a.kind,a.x,a.y] for a in commands]
    fingerprint=sha256(json.dumps(payload,separators=(",",":")).encode()).hexdigest()
    return StagePlan(stage.stage_id,mode,True,len(commands),tuple(commands),
                     explored,key_count,door_count,boss_count,crystals,
                     fingerprint,(
                         "No platform jump arc, velocity or moving combat simulation",
                         "Guardian encounter is abstract; not an observed defeat",
                         "No controller replay, emulator run or XP awarded",
                     ))

def plan_campaign(campaign:Campaign)->CampaignPlan:
    if not isinstance(campaign,Campaign) or not 1<=len(campaign.stages)<=8:
        raise ValueError("validated bounded native campaign required")
    reports=tuple(plan_stage(s,campaign.mode) for s in campaign.stages)
    checksum=sha256(json.dumps([campaign.id,[r.trace_digest for r in reports]],
                              separators=(",",":")).encode()).hexdigest()
    return CampaignPlan(campaign.id,all(s.achieved_exit for s in reports),
                        reports,checksum)

def agent_report(plan:CampaignPlan)->dict:
    return asdict(plan)
