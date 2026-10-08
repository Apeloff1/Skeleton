"""Bounded adversarial campaign-selection loop for native game generation.

This is STATIC stage/layout analysis, NOT a gameplay playtest, learned model,
AI inference, hardware emulator, or acceptance pass. Run many independently
seeded campaigns, score the resulting 2D geometry against explicit measurable
quality dimensions, and choose a diverse, safer cohort candidate. All metrics
can be recomputed from the source campaign. No caller-supplied rewards or XP.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass,asdict
from hashlib import sha256
from heapq import heappush,heappop
import json

from .dragon_game_blueprints import Campaign, Stage, design_campaign, W, H

@dataclass(frozen=True)
class StageAnalysis:
    stage: int
    walkable_tiles: int
    reachable_tiles: int
    shortest_route: int
    weighted_risk_route: int
    dead_ends: int
    reachable_pickups: int
    enemy_proximity: int
    blocked_ratio: float
    reachability_ratio: float
    route_detour: float
    quality: float
    issues: tuple[str,...]

@dataclass(frozen=True)
class CampaignAnalysis:
    candidate_id: str
    style: str
    seed: int
    static_quality: float
    diversity_score: float
    stage_scores: tuple[StageAnalysis,...]
    issues: tuple[str,...]
    verdict: str = "static_layout_review_only"
    schema: str = "skeleton.ai.dragon.campaign_analysis.v1"

@dataclass(frozen=True)
class SelectionEvidence:
    chosen: Campaign
    selected: CampaignAnalysis
    compared: tuple[tuple[str,float,str],...]
    rejected: tuple[tuple[str,str],...]
    budget: int
    selection_digest: str
    schema: str = "skeleton.ai.dragon.campaign_selection.v1"

def _pos(stage:Stage,symbol:str)->tuple[tuple[int,int],...]:
    return tuple((x,y) for y,row in enumerate(stage.terrain)
                 for x,c in enumerate(row) if c==symbol)

def _neighbors(x:int,y:int):
    yield x-1,y
    yield x+1,y
    yield x,y-1
    yield x,y+1

def _floor(stage:Stage,x:int,y:int)->bool:
    return 0<=x<W and 0<=y<H and stage.terrain[y][x] not in "#^~"

def _distance_field(stage:Stage,start:tuple[int,int])->dict[tuple[int,int],int]:
    q=deque([start])
    result={start:0}
    while q:
        x,y=q.popleft()
        for nx,ny in _neighbors(x,y):
            if (nx,ny) not in result and _floor(stage,nx,ny):
                result[(nx,ny)]=result[(x,y)]+1
                q.append((nx,ny))
    return result

def _weighted_path(stage:Stage,enemies:set[tuple[int,int]],
                   start:tuple[int,int],goal:tuple[int,int])->int:
    """Dijkstra avoids opponent proximity, rather than only shortest geometry."""
    queue=[(0,start)]
    best={start:0}
    while queue:
        cost,node=heappop(queue)
        if cost!=best[node]:continue
        if node==goal:return cost
        x,y=node
        for nx,ny in _neighbors(x,y):
            if not _floor(stage,nx,ny):continue
            exposure=0
            for ex,ey in enemies:
                distance=abs(nx-ex)+abs(ny-ey)
                if distance<=1:exposure+=8
                elif distance<=3:exposure+=3
            tile=stage.terrain[ny][nx]
            # In platform modes '=' may be a pass-through ledge, never a lethal
            # tile; static review cannot verify the real jump arc.
            hazard=2 if tile=='=' else 0
            alt=cost+1+exposure+hazard
            if alt<best.get((nx,ny),1<<60):
                best[(nx,ny)]=alt
                heappush(queue,(alt,(nx,ny)))
    return -1

def analyze_stage(stage:Stage)->StageAnalysis:
    if len(stage.terrain)!=H or any(len(row)!=W for row in stage.terrain):
        raise ValueError("untrusted stage grid dimensions")
    start,goal=stage.start,stage.goal
    if start not in _pos(stage,"S") or goal not in _pos(stage,"G"):
        raise ValueError("stage spawn and exit must match the source terrain")
    tiles=sum(1 for row in stage.terrain for c in row if c not in "#^~")
    reachable=_distance_field(stage,start)
    enemies=set(_pos(stage,"E"))
    pickups=set(_pos(stage,"*"))
    enemy_near=sum(1 for ex,ey in enemies if abs(ex-start[0])+abs(ey-start[1])<=4)
    route=reachable.get(goal,-1)
    risk=_weighted_path(stage,enemies,start,goal)
    dead=sum(1 for x,y in reachable if sum(
        (nx,ny) in reachable for nx,ny in _neighbors(x,y))<=1)
    coverage=len(reachable)/max(1,tiles)
    detour=route/max(1,abs(start[0]-goal[0])+abs(start[1]-goal[1])) if route>=0 else 0
    pickup_access=len(pickups.intersection(reachable))
    issues=[]
    if route<0:issues.append("spawn_to_exit_unreachable")
    if risk<0:issues.append("no_threat_adjusted_path")
    if coverage<.60:issues.append("low_exploration_coverage")
    if pickup_access<len(pickups):issues.append("inaccessible_pickups")
    if enemy_near>1:issues.append("high_spawn_enemy_pressure")
    if route>0 and detour>3.5:issues.append("excessive_detour")
    # These are objective heuristics, NOT calibrated probabilities.
    route_quality=min(1.0,route/35) if route>=0 else 0
    coverage_quality=min(1.0,coverage/.85)
    pickup_quality=pickup_access/max(1,len(pickups))
    risk_quality=min(1.0,max(0,risk-route)/max(1,route))
    variety=min(1.0,1-abs(2.0-detour)/5) if route>=0 else 0
    penalty=.09*len(issues)
    quality=round(max(0,min(1,
        .27*coverage_quality+.24*route_quality+.24*pickup_quality+
        .15*risk_quality+.10*variety-penalty)),5)
    return StageAnalysis(stage.stage_id,tiles,len(reachable),route,risk,dead,
                         pickup_access,enemy_near,
                         round(1-tiles/(W*H),5),round(coverage,5),
                         round(detour,5),quality,tuple(issues))

def evaluate_campaign(campaign:Campaign)->CampaignAnalysis:
    if not campaign.stages or len(campaign.stages)>8:
        raise ValueError("untrusted campaign stage count")
    reports=tuple(analyze_stage(stage) for stage in campaign.stages)
    signatures={stage.checksum for stage in campaign.stages}
    diversity=len(signatures)/len(campaign.stages)
    all_issues=tuple(sorted({issue for report in reports for issue in report.issues}))
    quality=round(sum(r.quality for r in reports)/len(reports)*.85
                  + diversity*.15,5)
    return CampaignAnalysis(campaign.id,campaign.style,campaign.seed,
                            quality,round(diversity,5),reports,all_issues)

def choose_campaign(*,style:str,seed:int,stages:int=4,
                    palette:str="vga_dusk",budget:int=8)->SelectionEvidence:
    if isinstance(budget,bool) or not isinstance(budget,int) or not 1<=budget<=24:
        raise ValueError("native game candidate budget must be 1..24")
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("campaign optimizer seed must be uint32")
    compared=[]
    rejected=[]
    valid=[]
    for i in range(budget):
        current=(seed+i*0x9E3779B9)&0xffffffff
        candidate=design_campaign(style=style,seed=current,
                                  stages=stages,palette=palette)
        metrics=evaluate_campaign(candidate)
        compared.append((candidate.id,metrics.static_quality,
                         ";".join(metrics.issues)))
        if "spawn_to_exit_unreachable" in metrics.issues or \
           "inaccessible_pickups" in metrics.issues:
            rejected.append((candidate.id,"layout accessibility invariant"))
        else:
            valid.append((metrics.static_quality,metrics.diversity_score,
                          -i,candidate.id,candidate,metrics))
    if not valid:
        raise ValueError("all original native game layouts failed static invariants")
    chosen=max(valid,key=lambda item:item[:4])
    payload={
        "chosen_id":chosen[4].id,"budget":budget,
        "compared":compared,"rejected":rejected,
        "criteria":"bounded static grid review; not gameplay verified",
    }
    checksum=sha256(json.dumps(payload,sort_keys=True,
                              separators=(",",":")).encode()).hexdigest()
    return SelectionEvidence(chosen[4],chosen[5],tuple(compared),
                             tuple(rejected),budget,checksum)

def selection_report(result:SelectionEvidence)->dict:
    return {
        "schema":result.schema,"selected":asdict(result.selected),
        "candidate_budget":result.budget,
        "compared":[{"id":x[0],"static_quality":x[1],
                     "static_issues":x[2]} for x in result.compared],
        "rejected":[{"id":x[0],"reason":x[1]} for x in result.rejected],
        "selection_digest":result.selection_digest,
        "boundaries":{
            "emulator_executed":False,"hardware_tested":False,
            "proof_scope":"static tile reachability, pickups, and risk only",
            "xp_awarded":False,
        },
    }
