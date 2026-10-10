"""Spatial NPC intelligence: capabilities 011-020.

Algorithms operate on actual generated tile worlds, not natural-language NPC
plans. Bounded 4-way movement with explicit obstacles and deterministic ties.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from heapq import heappop, heappush
from math import hypot, inf

Point=tuple[int,int]
Grid=tuple[str,...]
_MOVES=((0,-1),(-1,0),(1,0),(0,1))

@dataclass(frozen=True)
class AgentIntent:
    action: str
    next_position: Point
    target: Point | None
    urgency: float

def _ok(grid: Grid, p: Point) -> bool:
    x,y=p
    return 0<=y<len(grid) and 0<=x<len(grid[0]) and grid[y][x]!="#"

def _neighbors(grid: Grid, p: Point):
    x,y=p
    for dx,dy in _MOVES:
        nxt=x+dx,y+dy
        if _ok(grid,nxt): yield nxt

# 011 Accessible navigation flood for enemy perception and placement.
def navigation_reachable(grid: Grid, start: Point, *, limit: int = 50000
                         ) -> frozenset[Point]:
    if not _ok(grid,start) or not 1<=limit<=100000:
        raise ValueError("invalid navigation origin")
    q=deque([start]);seen={start}
    while q:
        for next_point in _neighbors(grid,q.popleft()):
            if next_point not in seen:
                if len(seen)>=limit: raise ValueError("navigation node budget exceeded")
                seen.add(next_point);q.append(next_point)
    return frozenset(seen)

# 012 A* grid path for chasing NPCs and companion agents.
def npc_astar(grid: Grid, start: Point, goal: Point, *,
              max_nodes: int = 20000) -> tuple[Point,...]:
    if not _ok(grid,start) or not _ok(grid,goal) or not 1<=max_nodes<=100000:
        return ()
    frontier=[(0,0,start)]
    costs={start:0};parent={start:None};seq=0
    while frontier:
        _,cost,pos=heappop(frontier)
        if cost!=costs[pos]:continue
        if pos==goal:
            path=[]
            while pos is not None:
                path.append(pos);pos=parent[pos]
            return tuple(reversed(path))
        if len(costs)>max_nodes:raise ValueError("path search budget exceeded")
        for nxt in _neighbors(grid,pos):
            trial=cost+1
            if trial<costs.get(nxt,inf):
                costs[nxt]=trial;parent[nxt]=pos;seq+=1
                heappush(frontier,(trial+abs(goal[0]-nxt[0])+abs(goal[1]-nxt[1]),
                                   trial,nxt))
    return ()

# 013 Weighted Dijkstra avoids traps and makes hazard-aware pursuit.
def npc_dijkstra(grid: Grid, start: Point, *,
                 hazard_penalty: float = 5., max_nodes: int = 30000
                 ) -> dict[Point,float]:
    if not _ok(grid,start) or not 0<=hazard_penalty<=100:
        raise ValueError("invalid path cost")
    frontier=[(0.,start)];distance={start:0.}
    while frontier:
        cost,pos=heappop(frontier)
        if cost>distance[pos]:continue
        if len(distance)>max_nodes:raise ValueError("path cost budget exceeded")
        for nxt in _neighbors(grid,pos):
            ncost=cost+1+(hazard_penalty if grid[nxt[1]][nxt[0]]=="^" else 0)
            if ncost<distance.get(nxt,inf):
                distance[nxt]=ncost;heappush(frontier,(ncost,nxt))
    return distance

# 014 Deterministic Bresenham vision blocked by world geometry.
def npc_line_of_sight(grid: Grid, start: Point, end: Point) -> bool:
    if not _ok(grid,start) or not _ok(grid,end):return False
    x0,y0=start;x1,y1=end
    dx=abs(x1-x0);dy=-abs(y1-y0)
    sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1
    error=dx+dy
    while True:
        if not _ok(grid,(x0,y0)):return False
        if (x0,y0)==end:return True
        e2=2*error
        if e2>=dy:error+=dy;x0+=sx
        if e2<=dx:error+=dx;y0+=sy

# 015 Cover selection based on occlusion from a threat.
def npc_find_cover(grid: Grid, actor: Point, threat: Point, *,
                   radius: int = 12) -> Point | None:
    if not 1<=radius<=60 or not _ok(grid,actor):
        raise ValueError("invalid cover search")
    reachable=navigation_reachable(grid,actor)
    options=[p for p in reachable
             if abs(p[0]-actor[0])+abs(p[1]-actor[1])<=radius
             and not npc_line_of_sight(grid,p,threat)]
    return min(options,key=lambda p:(
        abs(p[0]-actor[0])+abs(p[1]-actor[1]),-abs(p[0]-threat[0]),p,
    )) if options else None

# 016 Patrol between actual reachable waypoints.
def npc_patrol_route(grid: Grid, waypoints: tuple[Point,...], *,
                     max_path: int = 30000) -> tuple[Point,...]:
    if len(waypoints)<2 or len(waypoints)>64:
        raise ValueError("patrol requires bounded waypoints")
    result=[]
    for a,b in zip(waypoints,waypoints[1:]+waypoints[:1]):
        path=npc_astar(grid,a,b,max_nodes=max_path)
        if not path: raise ValueError("disconnected patrol route")
        result.extend(path if not result else path[1:])
    return tuple(result)

# 017 Chase target across actual reachable terrain with detection radius.
def npc_chase(grid: Grid, actor: Point, target: Point, *,
              sight_radius: int = 12) -> AgentIntent:
    if not 1<=sight_radius<=100:
        raise ValueError("invalid chase sensing")
    delta=abs(actor[0]-target[0])+abs(actor[1]-target[1])
    if delta>sight_radius:
        return AgentIntent("idle",actor,None,0.)
    route=npc_astar(grid,actor,target)
    if len(route)<2:return AgentIntent("idle",actor,target,0.)
    return AgentIntent("chase",route[1],target,round(1/(1+delta/4),5))

# 018 Evade threats while minimizing hazards and dead ends.
def npc_flee(grid: Grid, actor: Point, threat: Point, *,
             radius: int = 6) -> AgentIntent:
    if not _ok(grid,actor) or not 1<=radius<=30:
        raise ValueError("invalid flee state")
    reachable=navigation_reachable(grid,actor)
    choices=[p for p in reachable if abs(p[0]-actor[0])+abs(p[1]-actor[1])<=radius]
    scored=sorted(choices,key=lambda p:(
        -(abs(p[0]-threat[0])+abs(p[1]-threat[1])),
        grid[p[1]][p[0]]=="^",
        abs(p[0]-actor[0])+abs(p[1]-actor[1]),p,
    ))
    goal=scored[0] if scored else actor
    route=npc_astar(grid,actor,goal)
    return AgentIntent("flee",route[1] if len(route)>1 else actor,
                       threat,1.)

# 019 Separation steering keeps multiple NPCs from occupying one tile.
def npc_separation(actor: Point, others: tuple[Point,...], *,
                   radius: int = 3) -> tuple[float,float]:
    if not 1<=radius<=30 or len(others)>1000:
        raise ValueError("invalid steering group")
    fx=fy=0.
    for x,y in others:
        dx,dy=actor[0]-x,actor[1]-y
        d=hypot(dx,dy)
        if 0<d<=radius:
            fx+=dx/(d*d);fy+=dy/(d*d)
    magnitude=hypot(fx,fy)
    return (round(fx/magnitude,5),round(fy/magnitude,5)) if magnitude else (0.,0.)

# 020 Utility-driven enemy action from health, visibility, distance and cover.
def npc_choose_action(grid: Grid, actor: Point, player: Point, *,
                      health_ratio: float, aggression: float = .7,
                      retreat_threshold: float = .25) -> AgentIntent:
    if not 0<=health_ratio<=1 or not 0<=aggression<=1:
        raise ValueError("invalid AI state")
    dist=abs(actor[0]-player[0])+abs(actor[1]-player[1])
    visible=npc_line_of_sight(grid,actor,player)
    if health_ratio<retreat_threshold:
        hide=npc_find_cover(grid,actor,player,radius=10)
        if hide:
            path=npc_astar(grid,actor,hide)
            return AgentIntent("take_cover",path[1] if len(path)>1 else actor,hide,1.)
        return npc_flee(grid,actor,player)
    if dist<=1 and visible:
        return AgentIntent("attack",actor,player,round(aggression,5))
    if visible and dist<15 and aggression>=.3:
        return npc_chase(grid,actor,player,sight_radius=15)
    return AgentIntent("patrol",actor,None,0.)
