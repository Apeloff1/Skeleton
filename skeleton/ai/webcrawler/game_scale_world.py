"""Procedural worlds and traversable level authoring: capabilities 001-010.

Operations are real grid transformations backed by a path solver, intended for
the existing GameBlueprint/HTML5/Godot compiler. The generator preserves a
walkable primary corridor and uses only tiles the runtime understands.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, replace
from hashlib import sha256
from math import hypot
import json
import random

from .game_knowledge_design import GameBlueprint, find_level_route

@dataclass(frozen=True)
class Room:
    left: int
    top: int
    width: int
    height: int
    kind: str = "standard"

@dataclass(frozen=True)
class WorldRegion:
    name: str
    rooms: tuple[Room,...]
    connections: tuple[tuple[int,int],...]
    spawn: tuple[int,int]
    exit: tuple[int,int]
    tiles: tuple[str,...]

def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _replace_grid(blueprint: GameBlueprint, grid: list[list[str]]) -> GameBlueprint:
    rendered=tuple("".join(r) for r in grid)
    if not find_level_route(rendered):
        raise ValueError("modification disconnected the critical route")
    return replace(blueprint,grid=rendered,fingerprint=_digest([
        blueprint.fingerprint,rendered,blueprint.seed,
    ]))

# 001 Build a connected original room graph.
def generate_room_graph(count: int, *, seed: int, max_degree: int = 3
                        ) -> tuple[tuple[int,int],...]:
    if not 2<=count<=128 or not 1<=max_degree<=8:
        raise ValueError("invalid room graph bounds")
    rng=random.Random(seed)
    parents=list(range(count))
    degree=[0]*count
    edges=[]
    for child in range(1,count):
        available=[p for p in range(child) if degree[p]<max_degree]
        if not available:
            raise ValueError("room degree cap prevents connected world")
        p=rng.choice(available)
        degree[p]+=1;degree[child]+=1;edges.append((p,child))
    return tuple(edges)

# 002 Add meaningful navigation loops without duplicate edges.
def create_shortcuts(edges: tuple[tuple[int,int],...], count: int, *,
                     seed: int, extra: int = 2) -> tuple[tuple[int,int],...]:
    if not 2<=count<=128 or not 0<=extra<=count*2:
        raise ValueError("invalid loop budget")
    existing={tuple(sorted(e)) for e in edges}
    rng=random.Random(seed)
    candidates=[(a,b) for a in range(count) for b in range(a+2,count)
                if (a,b) not in existing]
    rng.shuffle(candidates)
    return tuple(sorted(existing|set(candidates[:extra])))

# 003 Spatially pack a bounded sequence of room rectangles.
def pack_world_rooms(count: int, *, seed: int, columns: int = 4,
                     width: int = 12, height: int = 8) -> tuple[Room,...]:
    if not 1<=count<=100 or not 1<=columns<=12 or not 6<=width<=32 or not 5<=height<=24:
        raise ValueError("invalid room packing")
    rng=random.Random(seed)
    rooms=[]
    for i in range(count):
        left=(i%columns)*(width+3)
        top=(i//columns)*(height+3)
        rw=width-rng.randrange(0,3)
        rh=height-rng.randrange(0,2)
        rooms.append(Room(left,top,rw,rh))
    return tuple(rooms)

# 004 Carve solid world into actual open rooms.
def carve_world_rooms(rooms: tuple[Room,...], *, width: int, height: int
                      ) -> tuple[str,...]:
    if not 8<=width<=512 or not 8<=height<=512 or width*height>100000:
        raise ValueError("invalid world canvas")
    rows=[["#"]*width for _ in range(height)]
    for room in rooms:
        if room.left<1 or room.top<1 or room.left+room.width>=width or room.top+room.height>=height:
            raise ValueError("room outside canvas")
        for y in range(room.top,room.top+room.height):
            for x in range(room.left,room.left+room.width):
                rows[y][x]="."
    return tuple("".join(r) for r in rows)

# 005 Connect all chosen rooms by fully carved L-shaped corridors.
def connect_world_corridors(tiles: tuple[str,...], rooms: tuple[Room,...],
                            edges: tuple[tuple[int,int],...], *,
                            width: int = 2) -> tuple[str,...]:
    if not 1<=width<=4:
        raise ValueError("invalid corridor width")
    grid=[list(row) for row in tiles]
    h=len(grid);w=len(grid[0])
    def carve(x,y):
        for j in range(width):
            for i in range(width):
                xx,yy=x+i,y+j
                if 0<xx<w-1 and 0<yy<h-1: grid[yy][xx]="."
    for a,b in edges:
        if not (0<=a<len(rooms) and 0<=b<len(rooms)):
            raise ValueError("invalid room edge")
        lhs,rhs=rooms[a],rooms[b]
        x,y=lhs.left+lhs.width//2,lhs.top+lhs.height//2
        tx,ty=rhs.left+rhs.width//2,rhs.top+rhs.height//2
        while x!=tx:
            carve(x,y);x+=1 if tx>x else -1
        while y!=ty:
            carve(x,y);y+=1 if ty>y else -1
        carve(x,y)
    return tuple("".join(row) for row in grid)

# 006 Choose the furthest reachable exit to extend meaningful exploration.
def choose_distant_exit(tiles: tuple[str,...], start: tuple[int,int]
                        ) -> tuple[int,int]:
    h=len(tiles);w=len(tiles[0])
    if not(0<=start[0]<w and 0<=start[1]<h) or tiles[start[1]][start[0]]=="#":
        raise ValueError("invalid entry")
    q=deque([start]);steps={start:0}
    while q:
        x,y=q.popleft()
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=nx<w and 0<=ny<h and tiles[ny][nx]!="#" and (nx,ny) not in steps:
                steps[(nx,ny)]=steps[(x,y)]+1;q.append((nx,ny))
    return max(steps,key=lambda p:(steps[p],-p[1],p[0]))

# 007 Place difficulty-scaled hazards away from critical route.
def distribute_world_hazards(blueprint: GameBlueprint, *, count: int,
                             seed: int) -> GameBlueprint:
    if not 0<=count<=100:
        raise ValueError("invalid hazard count")
    grid=[list(r) for r in blueprint.grid]
    critical=set(find_level_route(blueprint.grid))
    locations=[(x,y) for y,row in enumerate(grid) for x,t in enumerate(row)
               if t=="." and (x,y) not in critical and
               y>1 and y<blueprint.height-1 and
               grid[y+1][x]=="#"]
    random.Random(seed).shuffle(locations)
    for x,y in locations[:count]: grid[y][x]="^"
    return _replace_grid(blueprint,grid)

# 008 Place optional collectibles off the shortest critical route.
def distribute_world_secrets(blueprint: GameBlueprint, *, count: int,
                             seed: int) -> GameBlueprint:
    if not 0<=count<=100:
        raise ValueError("invalid secret budget")
    grid=[list(r) for r in blueprint.grid]
    critical=set(find_level_route(blueprint.grid))
    spots=[(x,y) for y,row in enumerate(grid) for x,t in enumerate(row)
           if t=="." and (x,y) not in critical and y<blueprint.height-1]
    rng=random.Random(seed);rng.shuffle(spots)
    for x,y in spots[:count]: grid[y][x]="C"
    return _replace_grid(blueprint,grid)

# 009 Place safe checkpoint sites at meaningful route intervals.
def select_world_checkpoints(tiles: tuple[str,...], *,
                             spacing: int = 14) -> tuple[tuple[int,int],...]:
    if not 4<=spacing<=256:
        raise ValueError("invalid checkpoint spacing")
    route=find_level_route(tiles)
    return tuple(route[i] for i in range(spacing,len(route)-1,spacing))

# 010 Assemble a genuinely navigable multi-room world from all stages.
def generate_world_region(name: str, *, rooms: int, seed: int,
                          columns: int = 4) -> WorldRegion:
    if not isinstance(name,str) or not 1<=len(name)<=80:
        raise ValueError("invalid region name")
    geometry=pack_world_rooms(rooms,seed=seed,columns=columns)
    edges=create_shortcuts(generate_room_graph(rooms,seed=seed),
                           rooms,seed=seed+1,extra=max(1,rooms//4))
    width=max(r.left+r.width for r in geometry)+3
    height=max(r.top+r.height for r in geometry)+3
    # Room packer can place the first room at 0; add a 1-tile border.
    moved=tuple(replace(r,left=r.left+1,top=r.top+1) for r in geometry)
    width+=1;height+=1
    carved=carve_world_rooms(moved,width=width,height=height)
    linked=connect_world_corridors(carved,moved,edges)
    start=(moved[0].left+2,moved[0].top+2)
    exit=choose_distant_exit(linked,start)
    rows=[list(x) for x in linked]
    rows[start[1]][start[0]]="P";rows[exit[1]][exit[0]]="G"
    return WorldRegion(name,moved,edges,start,exit,
                       tuple("".join(r) for r in rows))


def world_region_to_blueprint(
    region: WorldRegion, *, title: str, seed: int,
    pickups: int = 12, enemies: int = 5,
) -> GameBlueprint:
    """Turn the connected room graph into a fully playable exploration map.

    Unlike the platformer generator this geometry is navigated on both
    horizontal and vertical axes. Wall tiles block movement; collectibles
    and enemies are placed only in reachable original rooms/corridors.
    """
    from .game_scale_npc_ai import navigation_reachable

    if not isinstance(region,WorldRegion) or not isinstance(title,str) or not title:
        raise ValueError("invalid explorable world source")
    if not 0<=pickups<=100 or not 0<=enemies<=40:
        raise ValueError("invalid world encounter budget")
    tiles=region.tiles
    height,width=len(tiles),len(tiles[0]) if tiles else 0
    if not 16<=width<=128 or not 10<=height<=64 or width*height>4096:
        raise ValueError("world exceeds playable map renderer capacity")
    if any(len(row)!=width for row in tiles):
        raise ValueError("inconsistent world dimensions")
    if not find_level_route(tiles):
        raise ValueError("world lacks connected exit")
    reachable=navigation_reachable(tiles,region.spawn)
    route=set(find_level_route(tiles))
    spawn=region.spawn
    rng=random.Random(seed+149)
    optional=[
        (x,y) for x,y in reachable
        if tiles[y][x]=="." and (x,y) not in route and
        abs(spawn[0]-x)+abs(spawn[1]-y)>4
    ]
    rng.shuffle(optional)
    if len(optional)<pickups+enemies:
        # Main corridor can host encounters too, but never overwrite spawn
        # or goal and never put every pickup behind an inaccessible wall.
        extra=[
            (x,y) for x,y in reachable
            if tiles[y][x]=="." and (x,y) not in optional and
            abs(spawn[0]-x)+abs(spawn[1]-y)>4
        ]
        rng.shuffle(extra)
        optional.extend(extra)
    rows=[list(row) for row in tiles]
    for x,y in optional[:pickups]:
        rows[y][x]="C"
    for x,y in optional[pickups:pickups+enemies]:
        rows[y][x]="E"
    ready=tuple("".join(row) for row in rows)
    if not find_level_route(ready):
        raise RuntimeError("world placement disrupted player route")
    physics=tuple(sorted({
        "move_speed":5.0,
        "jump_speed":15.0,
        "gravity":25.0,
        "acceleration":30.0,
        "friction":28.0,
        "enemy_speed":1.4,
        "max_lives":4.0,
    }.items()))
    evidence=tuple(
        f"original-world:{region.name}:room-{i}"
        for i in range(len(region.rooms))
    )
    digest=_digest({
        "schema":"skeleton.original.exploration_world.v1",
        "region":region.name,
        "grid":ready,
        "physics":physics,
        "rooms":[(r.left,r.top,r.width,r.height,r.kind) for r in region.rooms],
        "connections":region.connections,
        "seed":seed,
    })
    return GameBlueprint(
        title,"exploration","web",
        ("movement","collision","camera","collectible","enemy_ai",
         "checkpoint","puzzle"),
        width,height,ready,physics,evidence,seed,digest,
    )
