"""Measured multi-route Sokoban exploration, independent search objectives.

A game is not one proof string. This engine independently searches for
short-walk, push-efficient, low-risk and route-diverse winning traces, and
classifies structural versus navigation-only variety. All traces are checked
against the actual original-grid rules. Search limits are explicit; an
unfound route is unknown, NOT proof that alternatives cannot exist.

Only data-derived geometry/branch estimates are produced. No assertion of
fun, player psychology, completion rates or objective game quality is made
without consenting playtest observations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from functools import lru_cache
from heapq import heappop,heappush
from itertools import permutations
from math import log2
from typing import Literal
import json

SCHEMA="skeleton.ai.dragon.original_multiroute.v1"
MAX_ALTERNATIVES=8
MAX_EXPANSIONS=120000
MAX_STEPS=400
ORDER=((-1,0,"a"),(1,0,"d"),(0,-1,"w"),(0,1,"s"))

@dataclass(frozen=True)
class Route:
    path:str
    path_sha256:str
    solver:str
    moves:int
    pushes:int
    turns:int
    visited_cells:int
    choice_points:int
    push_signature:tuple[tuple[int,int],...]
    walked_cells:tuple[int,...]
    risky_pushes:int
    deadlock_pushes:int
    variation:str

@dataclass(frozen=True)
class RoutePortfolio:
    schema:str
    routes:tuple[Route,...]
    solvers_attempted:tuple[str,...]
    solvers_succeeded:tuple[str,...]
    structurally_distinct:int
    navigationally_distinct:int
    examined_states:int
    exhaustive_alternatives:bool
    difficulty_estimate:int
    fairness_flags:tuple[str,...]
    claim:str

def _grid(rows):
    from .dragon_native_puzzle import _parse,WIDTH,HEIGHT
    player,crates,goals,walls=_parse(rows)
    return WIDTH,HEIGHT,player,crates,goals,walls

def _advance(state,action,width,height,walls):
    player,crates=state
    dx,dy,key=action
    x,y=player%width,player//width
    nx,ny=x+dx,y+dy
    if not (0<=nx<width and 0<=ny<height):
        return None
    cell=ny*width+nx
    if cell in walls:return None
    pushed=None
    if cell in crates:
        bx,by=nx+dx,ny+dy
        if not(0<=bx<width and 0<=by<height):return None
        ahead=by*width+bx
        if ahead in walls or ahead in crates:return None
        next_crates=tuple(sorted(ahead if old==cell else old for old in crates))
        pushed=(cell,ahead)
    else:
        next_crates=crates
    return (cell,next_crates),pushed

def _corner_deadlocks(width,height,walls,goals):
    corners=set()
    for cell in range(width*height):
        if cell in walls or cell in goals:continue
        x,y=cell%width,cell//width
        horizontal=(x==0 or x==width-1 or cell-1 in walls or cell+1 in walls)
        vertical=(y==0 or y==height-1 or cell-width in walls or cell+width in walls)
        if horizontal and vertical:corners.add(cell)
    return corners

def _assignment(crates,goals,width):
    # Admissible minimum pushes/steps ignoring walls and blockers.
    distances=[]
    for order in permutations(sorted(goals)):
        score=sum(abs(a%width-b%width)+abs(a//width-b//width)
                  for a,b in zip(crates,order))
        distances.append(score)
    return min(distances) if distances else 0

def _search(rows,*,mode,expansion_cap:int,avoid_edges=frozenset()):
    width,height,player,crates,goals,walls=_grid(rows)
    start=(player,crates)
    corners=_corner_deadlocks(width,height,walls,goals)
    # For non-push-first objectives use weighted nonnegative costs.
    # All edges have cost >=1; shortest objective uses admissible A*.
    heap=[]
    sequence=0
    if mode=="push_first":
        heappush(heap,(0,0,sequence,start))
        costs={start:(0,0)}
    else:
        heappush(heap,(_assignment(crates,goals,width) if mode=="astar" else 0,
                       0,sequence,start))
        costs={start:0}
    parents={start:None}
    expanded=0
    done=None
    while heap and expanded<expansion_cap and len(costs)<MAX_EXPANSIONS:
        priority,secondary,_,state=heappop(heap)
        best=costs[state]
        if mode=="push_first":
            if (priority,secondary)!=best:continue
        elif secondary!=best:
            continue
        expanded+=1
        if set(state[1])==goals:
            done=state
            break
        for direction in ORDER:
            moved=_advance(state,direction,width,height,walls)
            if moved is None:continue
            next_state,push=moved
            # Push into a fixed non-goal corner can never be recovered.
            if push and push[1] in corners:continue
            if mode=="push_first":
                next_cost=(best[0]+int(push is not None),best[1]+1)
            else:
                extra=1
                if mode=="risk_averse" and push:
                    cell=push[1]
                    near=sum((cell+delta in walls) for delta in (-width,width,-1,1))
                    extra+=near*2
                if mode=="route_diverse" and (state,direction[2]) in avoid_edges:
                    extra+=7
                next_cost=best+extra
            if next_cost>=costs.get(next_state,(MAX_EXPANSIONS,MAX_EXPANSIONS)
                                    if mode=="push_first" else MAX_EXPANSIONS*20):
                continue
            costs[next_state]=next_cost
            parents[next_state]=(state,direction[2])
            sequence+=1
            if mode=="push_first":
                heappush(heap,(next_cost[0],next_cost[1],sequence,next_state))
            else:
                heuristic=(_assignment(next_state[1],goals,width)
                           if mode=="astar" else 0)
                heappush(heap,(next_cost+heuristic,next_cost,sequence,next_state))
    if done is None:
        return None,expanded
    moves=[]
    while done!=start:
        previous,key=parents[done]
        moves.append(key)
        done=previous
    result="".join(reversed(moves))
    if not result or len(result)>MAX_STEPS:return None,expanded
    return result,expanded

def _walk(rows,path,*,solver,variation):
    width,height,player,crates,goals,walls=_grid(rows)
    if not isinstance(path,str) or not 1<=len(path)<=MAX_STEPS or set(path)-set("wasd"):
        raise ValueError("candidate route must be 1..400 original game moves")
    state=(player,crates)
    footprint={player}
    pushes=[]
    explored=0
    risky=0
    deadlocked=0
    prev=None
    turns=0
    edges=[]
    corners=_corner_deadlocks(width,height,walls,goals)
    for key in path:
        available=[a for a in ORDER if _advance(state,a,width,height,walls) is not None]
        if len(available)>1:explored+=1
        option=next(x for x in ORDER if x[2]==key)
        result=_advance(state,option,width,height,walls)
        if result is None:raise ValueError("claimed winning route contains an invalid move")
        newer,push=result
        edges.append((state,key))
        if push:
            pushes.append(push)
            deadlocked+=push[1] in corners
            risky+=any(push[1]+d in walls for d in (-width,width,-1,1))
        if prev is not None and prev!=key:turns+=1
        prev=key
        state=newer
        footprint.add(state[0])
    if set(state[1])!=goals:
        raise ValueError("claimed route did not complete every original game goal")
    return Route(path,sha256(path.encode("ascii")).hexdigest(),solver,
                 len(path),len(pushes),turns,len(footprint),explored,
                 tuple(pushes),tuple(sorted(footprint)),risky,deadlocked,
                 variation),frozenset(edges)

@lru_cache(maxsize=128)
def analyse_routes(rows:tuple[str,...],*,max_routes:int=6,
                   expansion_cap:int=20000)->RoutePortfolio:
    """Bounded multi-solver route portfolio, refusing unverifiable alternatives.

    This is evidence about one authored *level*, not a claim the full game
    story branches. Campaign-level routes require the companion DAG adapter.
    """
    if not isinstance(rows,tuple) or len(rows)!=10 or any(
            not isinstance(row,str) or len(row)!=12 for row in rows):
        raise ValueError("route analysis needs an immutable bounded original map")
    if type(max_routes) is not int or not 1<=max_routes<=MAX_ALTERNATIVES:
        raise ValueError("original route portfolio size must be 1..8")
    if type(expansion_cap) is not int or not 500<=expansion_cap<=MAX_EXPANSIONS:
        raise ValueError("original route search budget must be 500..120000")
    from .dragon_native_puzzle import solve_grid
    baseline,seen=solve_grid(rows)
    winner,first_edges=_walk(rows,baseline,solver="exact_bfs",
                             variation="baseline_optimal")
    routes=[winner]
    paths={baseline}
    push_signatures={winner.push_signature}
    footprints={winner.walked_cells}
    attempted=["exact_bfs"]
    succeeded=["exact_bfs"]
    explored=seen
    objectives=("astar","push_first","risk_averse","route_diverse",
                "route_diverse","route_diverse")
    for index,objective in enumerate(objectives):
        if len(routes)>=max_routes:break
        attempted.append(objective+f"_{index}" if objective=="route_diverse" else objective)
        penalized=(first_edges if index<4 else
                    frozenset((before,key) for route in routes
                              for before,key in _walk(
                                  rows,route.path,solver=route.solver,
                                  variation=route.variation,
                              )[1]))
        candidate,expanded=_search(rows,mode=objective,
                                   expansion_cap=expansion_cap,
                                   avoid_edges=penalized)
        explored+=expanded
        if candidate is None or candidate in paths or len(candidate)>min(
            MAX_STEPS, max(len(baseline)+16, len(baseline)*2)):
            continue
        route,_=_walk(rows,candidate,solver=objective,variation="candidate")
        if route.deadlock_pushes:continue
        if route.push_signature not in push_signatures:
            kind="distinct_push_strategy"
        elif route.walked_cells not in footprints:
            kind="distinct_navigation"
        else:
            # Merely shuffling identical steps does not establish a genuinely
            # alternative game route, so it is excluded from portfolio.
            continue
        route=Route(**{**asdict(route),"variation":kind})
        routes.append(route)
        succeeded.append(objective+f"_{index}" if objective=="route_diverse" else objective)
        paths.add(candidate)
        push_signatures.add(route.push_signature)
        footprints.add(route.walked_cells)
    structural=len(push_signatures)
    navigation=len(footprints)
    difficulty=min(100,round(
        12*log2(1+max(1,seen))+
        min(len(baseline),100)/5+
        min(winner.pushes,20)*2+
        min(winner.risky_pushes,12)*2
    ))
    flags=[]
    if winner.risky_pushes>=3:flags.append("tight_crate_corridors")
    if structural==1 and navigation==1:flags.append("single_measured_strategy")
    if winner.choice_points==0:flags.append("no_local_route_choices")
    return RoutePortfolio(
        SCHEMA,tuple(routes),tuple(attempted),tuple(succeeded),
        structural,navigation,explored,False,difficulty,tuple(flags),
        "bounded candidate routes from independent objectives; enjoyable/frustrating "
        "experience NOT measured; missing alternatives are unknown, not impossible",
    )

def route_report(result:RoutePortfolio)->dict:
    """Publish the same JSON-compatible evidence for direct and HTTP callers.

    dataclasses.asdict preserves tuple containers, but verify_route_report
    intentionally validates the public transport contract as JSON arrays.
    Normalize once at the publisher boundary, never weaken the verifier.
    """
    if not isinstance(result,RoutePortfolio):
        raise ValueError("route report requires a verified portfolio")
    return json.loads(json.dumps(asdict(result),sort_keys=True,
                                 separators=(",",":"),allow_nan=False))

def verify_route_report(rows:tuple[str,...],document:dict)->dict:
    """Recompute live grid physics and independent search evidence."""
    if not isinstance(document,dict) or document.get("schema")!=SCHEMA:
        raise ValueError("unknown original multipath report")
    routes=document.get("routes")
    if not isinstance(routes,list) or not 1<=len(routes)<=MAX_ALTERNATIVES:
        raise ValueError("route report has no bounded winning candidates")
    seen=set()
    pushes=set()
    footprints=set()
    for row in routes:
        if not isinstance(row,dict):
            raise ValueError("invalid route evidence entry")
        parsed,_=_walk(rows,row.get("path"),solver=row.get("solver","replay"),
                       variation=row.get("variation","replay"))
        for field in ("path_sha256","moves","pushes","turns","visited_cells",
                      "choice_points","risky_pushes","deadlock_pushes"):
            if row.get(field)!=getattr(parsed,field):
                raise ValueError("reported original game path physics mismatched")
        if row.get("path") in seen:
            raise ValueError("duplicate source routes cannot count as new choices")
        seen.add(row["path"])
        pushes.add(parsed.push_signature)
        footprints.add(parsed.walked_cells)
    if (document.get("structurally_distinct")!=len(pushes) or
            document.get("navigationally_distinct")!=len(footprints) or
            document.get("exhaustive_alternatives") is not False):
        raise ValueError("original route diversity claim is not reproducible")
    return {
        "schema":SCHEMA,"status":"original_routes_replayed",
        "routes":len(routes),"structural":len(pushes),
        "navigation":len(footprints),"claim":"all paths replay, route search not exhaustive",
    }
