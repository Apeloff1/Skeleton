"""Two independent exact-action planners for original *moving* maze worlds.

The maze itself can change every move. Static BFS is insufficient when a
door is closed now but will open after a wait or another passage. These
solvers search actual (x, y, rotating-door phase, resources) states, execute
real engine actions, and independently replay the proposed path.

BFS minimizes the number of turns to a *chosen local objective*. A* uses
Manhattan distance to prioritize the same search and verifies the same
admissible local movement contract. This is not a claim that an open-ended
world has an obligatory final goal, or proof of all possible future play.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from heapq import heappop,heappush
from itertools import count
from hashlib import sha256
import json

from .dragon_living_world import (
    LivingWorld,LivingState,initial_state,validate_world,
    validate_state,options,take_action,replay,DIRS,_sha,
)

SCHEMA="skeleton.ai.dragon.temporal_maze_solver.v1"
MAX_EXPANSIONS=10_000
MAX_HORIZON=72
MAX_RADIUS=4

@dataclass(frozen=True)
class DynamicMazeProof:
    schema:str
    solver:str
    world_fingerprint:str
    start_digest:str
    start_position:tuple[int,int,int]
    goal_position:tuple[int,int,int]
    reachable_in_bound:bool
    steps:tuple[str,...]
    actual_turns:int
    waiting_turns:int
    movement_turns:int
    expanded:int
    truncated:bool
    first_phase:int
    end_phase:int
    replay_digest:str
    ending_is_required:bool
    claim:str


def _validate(world:LivingWorld,state:LivingState,goal:tuple[int,int,int],
              budget:int,horizon:int):
    validate_world(world);validate_state(world,state)
    if not world.shifting_routes:
        raise ValueError("temporal maze solvers require a real changing maze")
    if (not isinstance(goal,tuple) or len(goal)!=3 or
            any(type(x) is not int or abs(x)>1_000_000 for x in goal) or
            not 0<=goal[0]<world.realms):
        raise ValueError("temporal maze goal must be a concrete world position")
    if goal[0]!=state.realm:
        raise ValueError("local rotating-maze search cannot invent a realm portal")
    if type(budget) is not int or not 100<=budget<=MAX_EXPANSIONS:
        raise ValueError("temporal maze search exceeds bounded node budget")
    if type(horizon) is not int or not 1<=horizon<=MAX_HORIZON:
        raise ValueError("temporal maze horizon outside bounded exact replay")


def _geometry(state:LivingState)->tuple[int,int,int,int]:
    return state.x,state.y,state.turn%8,state.energy


def _distance(state:LivingState,goal:tuple[int,int,int])->int:
    return abs(state.x-goal[1])+abs(state.y-goal[2])


def solve(world:LivingWorld,goal:tuple[int,int,int], *,
          starting_state:LivingState|None=None,
          method:str="astar",budget:int=4500,horizon:int=32,
)->DynamicMazeProof:
    if method not in ("bfs","astar"):
        raise ValueError("only actual temporal BFS and A-star are implemented")
    start=initial_state(world) if starting_state is None else starting_state
    _validate(world,start,goal,budget,horizon)
    # Search only actual movement and safe recovery/wait operations, not
    # all world-building/economy/endings as fictional teleport shortcuts.
    prioritized=count()
    heap=[]
    heappush(heap,(
        _distance(start,goal) if method=="astar" else 0,
        0,next(prioritized),start,(),
    ))
    seen={}
    expanded=0
    found=None
    truncated=False
    while heap:
        _,distance,_,node,path=heappop(heap)
        key=_geometry(node)
        if key in seen and seen[key]<=distance:continue
        seen[key]=distance
        expanded+=1
        if (node.realm,node.x,node.y)==goal:
            found=(node,path)
            break
        if expanded>=budget:
            truncated=True
            break
        if distance>=horizon:
            continue
        legal={
            choice["name"]:choice for choice in options(world,node)
            if choice["available"]
        }
        suggestions=[name for name,_,_ in DIRS]+["wait","rest"]
        for action in suggestions:
            if action not in legal:continue
            after=take_action(world,node,action)
            if not after.alive:continue
            age=distance+1
            after_key=_geometry(after)
            if after_key in seen and seen[after_key]<=age:
                continue
            heuristic=_distance(after,goal) if method=="astar" else 0
            heappush(heap,(
                age+heuristic,age,next(prioritized),
                after,path+(action,),
            ))
    if found:
        end,path=found
        independently=replay(world,path,starting_state=start)
        if (independently!=end or
                (end.realm,end.x,end.y)!=goal):
            raise ValueError("changing maze solver invented a non-replayable traversal")
    else:
        path=()
        end=start
    return DynamicMazeProof(
        schema=SCHEMA,solver=method,
        world_fingerprint=world.world_fingerprint,
        start_digest=start.history_digest,
        start_position=(start.realm,start.x,start.y),
        goal_position=goal,
        reachable_in_bound=found is not None,
        steps=path,actual_turns=len(path),
        waiting_turns=sum(x in ("wait","rest") for x in path),
        movement_turns=sum(x in {name for name,_,_ in DIRS} for x in path),
        expanded=expanded,truncated=truncated,
        first_phase=start.turn%8,end_phase=end.turn%8,
        replay_digest=end.history_digest,
        ending_is_required=world.lifecycle=="mandatory_completion",
        claim="exact mutable game-state planning toward optional waypoint, "
              "not whole-universe completion or physical world simulation",
    )


def compare_solvers(world:LivingWorld,goal:tuple[int,int,int], *,
                    starting_state:LivingState|None=None,
                    budget:int=5000,horizon:int=24)->dict:
    first=solve(world,goal,starting_state=starting_state,
                method="bfs",budget=budget,horizon=horizon)
    second=solve(world,goal,starting_state=starting_state,
                 method="astar",budget=budget,horizon=horizon)
    # Both solvers use unit action cost; if both fully found a solution
    # their turn count must agree. A* only uses admissible Manhattan.
    if first.reachable_in_bound and second.reachable_in_bound and (
            first.actual_turns!=second.actual_turns):
        raise ValueError("independent temporal maze planners disagree on shortest action count")
    return {
        "schema":SCHEMA,
        "independent_solvers":["time_expanded_bfs","admissible_temporal_astar"],
        "bfs":asdict(first),"astar":asdict(second),
        "both_confirmed":first.reachable_in_bound and second.reachable_in_bound,
        "same_optimal_turn_count":first.reachable_in_bound and
            second.reachable_in_bound and first.actual_turns==second.actual_turns,
        "world_goal_required":world.includes_goal,
        "scope":"optional player-selected local destination in a changing graph",
    }


def changing_doors(world:LivingWorld, *,realm:int=0,x:int=0,y:int=0,
                   radius:int=2)->dict:
    """Actually enumerate local directed door availability over all 8 phases."""
    validate_world(world)
    if not world.shifting_routes:
        raise ValueError("original dynamic door map requires mutable labyrinth rule")
    if type(realm) is not int or not 0<=realm<world.realms:
        raise ValueError("original world layer outside visible realms")
    if type(x) is not int or abs(x)>1_000_000-MAX_RADIUS or (
        type(y) is not int or abs(y)>1_000_000-MAX_RADIUS):
        raise ValueError("original local maze observation outside coordinate limits")
    if type(radius) is not int or not 1<=radius<=MAX_RADIUS:
        raise ValueError("maze phase projection grid exceeds 9 by 9")
    phases=[]
    for phase in range(8):
        links=[]
        for row in range(y-radius,y+radius+1):
            for column in range(x-radius,x+radius+1):
                visitor=replace(initial_state(world),realm=realm,
                                x=column,y=row,turn=phase)
                gates=tuple(
                    option["name"] for option in options(world,visitor)
                    if option["available"] and
                    option["name"] in ("north","east","south","west")
                )
                if not gates:
                    raise ValueError("original rotating maze has a structurally trapped room")
                links.append({"at":[column,row],"open":gates})
        phases.append({
            "phase":phase,"links":links,
            "fingerprint":_sha(links),
        })
    count=len({frame["fingerprint"] for frame in phases})
    if count<2:
        raise ValueError("allegedly dynamic maze has a static route topology")
    return {
        "schema":SCHEMA,"world_fingerprint":world.world_fingerprint,
        "center":[realm,x,y],"radius":radius,
        "phases":phases,"distinct_topologies":count,
        "total_projected_directed_nodes":len(phases)*(2*radius+1)**2,
        "claims":"measured actual shifting openings, no static maze painted as dynamic",
    }


def verify_proof(world:LivingWorld,proof:DynamicMazeProof, *,
                 starting_state:LivingState|None=None)->dict:
    if not isinstance(proof,DynamicMazeProof) or proof.schema!=SCHEMA:
        raise ValueError("changing maze route does not have native typed evidence")
    if proof.world_fingerprint!=world.world_fingerprint:
        raise ValueError("changing maze route detached from original source")
    original=solve(
        world,proof.goal_position,starting_state=starting_state,
        method=proof.solver,budget=max(100,min(MAX_EXPANSIONS,proof.expanded+100)),
        horizon=max(1,min(MAX_HORIZON,proof.actual_turns+3)),
    )
    if original.reachable_in_bound!=proof.reachable_in_bound or (
            proof.reachable_in_bound and original.steps!=proof.steps):
        raise ValueError("changing-world route differs on independent source replay")
    if proof.reachable_in_bound:
        start=initial_state(world) if starting_state is None else starting_state
        verified=replay(world,proof.steps,starting_state=start)
        if verified.history_digest!=proof.replay_digest:
            raise ValueError("dynamic-wall route gameplay receipt forged")
    return {"schema":SCHEMA,"verified":True,
            "played_turns":proof.actual_turns,"ending_required":proof.ending_is_required}
