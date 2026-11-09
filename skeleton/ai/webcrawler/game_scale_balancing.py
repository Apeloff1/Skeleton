"""Playable level balancing and automated simulation: capabilities 061–070.

These operations model actual geometry and controller parameters. Results are
designer-facing predictions, never misrepresented as empirical player tests.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from math import sqrt
import random

from .game_knowledge_design import (
    GameBlueprint, find_level_route, analyze_level_playability,
    estimate_jump_reach,
)

@dataclass(frozen=True)
class PlayBalance:
    route_tiles:int
    estimated_seconds:float
    predicted_deaths:float
    collectibles:int
    engagement:float
    missing_reachability:tuple[tuple[int,int],...]
    recommendations:tuple[str,...]

# 061 Compute route length and controller-based estimated completion time.
def estimate_level_clear_time(blueprint:GameBlueprint,*,detour_factor:float=1.3)->float:
    route=find_level_route(blueprint.grid)
    if len(route)<2:return float("inf")
    if not 1<=detour_factor<=5:raise ValueError("invalid detour factor")
    speed=blueprint.physics_dict()["move_speed"]
    return round(((len(route)-1)/max(.01,speed))*detour_factor,3)

# 062 Measure inaccessible pickups and story exits using world topology.
def analyze_collectible_reachability(blueprint:GameBlueprint
                                     )->tuple[tuple[int,int],...]:
    path=find_level_route(blueprint.grid)
    if not path:return ()
    from .game_scale_npc_ai import navigation_reachable
    reachable=navigation_reachable(blueprint.grid,path[0])
    return tuple((x,y) for y,row in enumerate(blueprint.grid) for x,t in enumerate(row)
                 if t in ("C","G") and (x,y) not in reachable)

# 063 Score danger frequency per tile of mandatory route.
def compute_route_risk(blueprint:GameBlueprint,*,hazard_radius:int=2)->float:
    route=find_level_route(blueprint.grid)
    if not route:return 1.
    if not 1<=hazard_radius<=8:raise ValueError("invalid hazard radius")
    dangers=[(x,y) for y,row in enumerate(blueprint.grid)
             for x,t in enumerate(row) if t in ("^","E")]
    count=sum(any(abs(x-a)+abs(y-b)<=hazard_radius
                  for a,b in dangers) for x,y in route)
    return round(count/len(route),5)

# 064 Compute pickup placement fairness by route coverage.
def evaluate_reward_distribution(blueprint:GameBlueprint)->float:
    route=find_level_route(blueprint.grid)
    coins=[(x,y) for y,row in enumerate(blueprint.grid) for x,t in enumerate(row) if t=="C"]
    if not coins:return 0.
    if not route:return 0.
    offsets=[min(abs(px-x)+abs(py-y) for px,py in route) for x,y in coins]
    return round(sum(1/(1+d) for d in offsets)/len(coins),5)

# 065 Estimate required jump travel from gaps between solid platforms.
def analyze_jump_gap_requirements(blueprint:GameBlueprint)->tuple[int,...]:
    grid=blueprint.grid;gaps=[]
    for y in range(len(grid)-1):
        current=0
        for x in range(len(grid[0])):
            surface=grid[y][x] not in ("#","^") and grid[y+1][x]=="#"
            if not surface:current+=1
            elif current:
                if x-current>0:gaps.append(current)
                current=0
    return tuple(sorted(gaps))

# 066 Predict playability from route, jump reach and obstacles.
def evaluate_game_balance(blueprint:GameBlueprint)->PlayBalance:
    route=find_level_route(blueprint.grid)
    missing=analyze_collectible_reachability(blueprint)
    duration=estimate_level_clear_time(blueprint)
    danger=compute_route_risk(blueprint)
    balance=analyze_level_playability(blueprint)
    drops=max(0.,len(route)-1)*danger/15
    engagement=min(1.,.35+.25*evaluate_reward_distribution(blueprint)
                   +.25*balance.estimated_difficulty
                   +.15*min(1.,len(route)/40))
    recommendations=[]
    if missing:recommendations.append("move unreachable collectibles onto navigable terrain")
    if danger>.35:recommendations.append("reduce repeated danger on main route")
    if balance.collectibles==0:recommendations.append("add optional collectibles")
    if duration<8:recommendations.append("extend the core level")
    return PlayBalance(len(route),duration,round(drops,4),
                       balance.collectibles,round(engagement,4),
                       missing,tuple(recommendations))

# 067 Calibrate player movement to a desired traversal duration.
def tune_player_speed(blueprint:GameBlueprint,*,target_seconds:float
                      )->GameBlueprint:
    if not 3<=target_seconds<=3600:raise ValueError("invalid traversal target")
    path=find_level_route(blueprint.grid)
    if len(path)<2:raise ValueError("nontraversable scene")
    ideal=max(1.5,min(14.,(len(path)-1)*1.3/target_seconds))
    physics=blueprint.physics_dict();physics["move_speed"]=round(ideal,3)
    return replace(blueprint,physics=tuple(sorted(physics.items())))

# 068 Tune jump arc for chosen platform height.
def tune_jump_physics(blueprint:GameBlueprint,*,target_apex:float,
                      flight_range:float=6.)->GameBlueprint:
    if not 1<=target_apex<=20 or not 1<=flight_range<=40:
        raise ValueError("invalid jump design target")
    params=blueprint.physics_dict()
    gravity=params["gravity"]
    params["jump_speed"]=round(sqrt(2*gravity*target_apex),4)
    # v horizontal * airborne duration
    airtime=2*params["jump_speed"]/gravity
    params["move_speed"]=round(max(1.,min(15.,flight_range/airtime)),4)
    return replace(blueprint,physics=tuple(sorted(params.items())))

# 069 Simulate repeated seeded player reaction latency and predict misses.
def simulate_input_latency(blueprint:GameBlueprint,*,seed:int=0,
                           runs:int=500,latency_ms:float=80.
                           )->tuple[float,float]:
    if not 1<=runs<=10000 or not 0<=latency_ms<=300:
        raise ValueError("invalid input simulation")
    rng=random.Random(seed)
    reach,apex=estimate_jump_reach(
        speed=blueprint.physics_dict()["move_speed"],
        jump_speed=blueprint.physics_dict()["jump_speed"],
        gravity=blueprint.physics_dict()["gravity"],
    )
    time_window=reach/max(.1,blueprint.physics_dict()["move_speed"])
    failed=0;latencies=[]
    for _ in range(runs):
        observed=max(0.,rng.gauss(latency_ms,latency_ms*.25))/1000
        latencies.append(observed)
        if observed>=time_window*.5:failed+=1
    return round(failed/runs,5),round(sum(latencies)/runs,5)

# 070 Generate stronger seed candidates, selecting actual measured playability.
def optimize_level_variants(blueprint:GameBlueprint,*,attempts:int=24,
                            seed:int=0)->GameBlueprint:
    if not 2<=attempts<=1000:raise ValueError("invalid design search")
    from .game_knowledge_design import design_level_geometry,populate_game_level
    candidates=[]
    for i in range(attempts):
        tiles=design_level_geometry(blueprint.width,blueprint.height,
                                    seed=seed+i,genre=blueprint.genre)
        candidate=populate_game_level(replace(blueprint,grid=tiles,seed=seed+i),
                                       pickups=8,enemies=3)
        balance=evaluate_game_balance(candidate)
        fitness=(balance.engagement-.4*min(1.,balance.predicted_deaths)
                 -.1*bool(balance.missing_reachability))
        candidates.append((fitness,-len(balance.recommendations),
                           -i,candidate))
    return max(candidates,key=lambda x:x[:3])[3]
