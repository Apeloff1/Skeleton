"""Procedural *authored* Forge Studio terrain and level tools (operations 101-120).

Every algorithm writes real palette-indexed MapLayer cells, reproducibly from
an explicit seed and bounded region. No external assets, runtime root or model
provider is introduced. 256x256 layers and immutable StudioProject own output.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from heapq import heappush, heappop
from typing import Any, Mapping
import math
import random

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _integer, _replace_layer

PROCEDURAL_ACTIONS = (
    "terrain_height_noise", "terrain_fractal", "terrain_ridge", "terrain_islands",
    "terrain_crater", "terrain_meander_river", "terrain_lake", "terrain_coastline",
    "terrain_talus", "terrain_dunes", "terrain_voronoi", "terrain_contours",
    "terrain_floodplain", "terrain_cave_automata", "terrain_room_dungeon",
    "terrain_depth_maze", "terrain_road_links", "terrain_avoidance_path",
    "terrain_cliff_band", "terrain_biome_mosaic",
)


def _real(a: Mapping[str, Any], name: str, low: float, high: float, default=None) -> float:
    v = a.get(name, default)
    if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
        raise StudioError(f"{name} must be a finite numeric terrain parameter")
    return float(v)


def _seed(a: Mapping[str, Any]) -> int:
    return _integer(a, "seed", 0, 2**63 - 1)


def _tiles(layer, args):
    floor = _tile(layer, args, "floor")
    wall = _tile(layer, args, "wall")
    if floor == wall:
        raise StudioError("procedural floor and wall must differ")
    return floor, wall


def _hash(seed: int, x: int, y: int) -> float:
    z = ((seed ^ (x * 0x9e3779b1) ^ (y * 0x85ebca77)) * 0xc2b2ae3d) & 0xffffffff
    z ^= z >> 16
    z = (z * 0x7feb352d) & 0xffffffff
    z ^= z >> 15
    z = (z * 0x846ca68b) & 0xffffffff
    return ((z ^ (z >> 16)) & 0xffffffff) / 0xffffffff


def _smooth(u: float) -> float:
    return u * u * (3 - 2*u)


def _noise(seed: int, x: float, y: float, scale: float) -> float:
    sx, sy = x / scale, y / scale
    ix, iy = math.floor(sx), math.floor(sy)
    fx, fy = _smooth(sx - ix), _smooth(sy - iy)
    a = _hash(seed, ix, iy) * (1-fx) + _hash(seed, ix+1, iy) * fx
    b = _hash(seed, ix, iy+1) * (1-fx) + _hash(seed, ix+1, iy+1) * fx
    return a * (1-fy) + b*fy


def _fbm(seed: int, x: float, y: float, scale: float, octaves: int) -> float:
    weight, total, divisor = 1.0, 0., 0.
    for i in range(octaves):
        total += weight * _noise(seed+i*991, x, y, max(.5, scale/(2**i)))
        divisor += weight
        weight *= .5
    return total/divisor


def _line(x0: int, y0: int, x1: int, y1: int):
    dx, dy = abs(x1-x0), -abs(y1-y0)
    sx, sy = 1 if x0<x1 else -1, 1 if y0<y1 else -1
    error = dx + dy
    while True:
        yield x0,y0
        if (x0,y0) == (x1,y1):
            break
        e2=2*error
        if e2>=dy:
            error+=dy
            x0+=sx
        if e2<=dx:
            error+=dx
            y0+=sy


def edit_procedural(project: StudioProject, operation: str,
                    args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or operation not in PROCEDURAL_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("invalid procedural Forge authoring operation")
    idx, layer = _layer(project, args)
    x0,y0,w,h=_rectangle(layer,args)
    if w*h > 65536:
        raise StudioError("terrain region exceeds tile budget")
    floor,wall=_tiles(layer,args)
    seed=_seed(args)
    rng=random.Random(seed)
    old=list(layer.data)
    output=list(old)
    points=[(x,y) for y in range(y0,y0+h) for x in range(x0,x0+w)]
    region=set(points)
    def paint(x,y,tile):
        if (x,y) in region:
            output[y*layer.width+x]=tile
    def val(x,y):
        return old[y*layer.width+x]
    scale=_real(args,"scale",.5,256,8)
    threshold=_real(args,"threshold",0,1,.5)
    octaves=_integer(args,"octaves",1,8) if "octaves" in args else 4
    cx=x0+(w-1)/2
    cy=y0+(h-1)/2
    if operation in ("terrain_height_noise","terrain_fractal","terrain_ridge",
                     "terrain_islands","terrain_coastline","terrain_dunes",
                     "terrain_contours","terrain_cliff_band","terrain_biome_mosaic"):
        direction=_real(args,"angle_deg",-360,360,0)*math.pi/180
        co,si=math.cos(direction), math.sin(direction)
        for x,y in points:
            u,v=(x-cx)*co+(y-cy)*si, -(x-cx)*si+(y-cy)*co
            n=_fbm(seed,x,y,scale,octaves)
            if operation=="terrain_height_noise":
                value=_noise(seed,x,y,scale)
            elif operation=="terrain_fractal":
                value=n
            elif operation=="terrain_ridge":
                width=_real(args,"ridge_width",.5,128,3)
                value=math.exp(-.5*(v/width)**2) * (.75+.25*n)
            elif operation=="terrain_islands":
                r=((u/max(1,w/2))**2+(v/max(1,h/2))**2)**.5
                value=max(0.,min(1.,(1-r)*1.4 + (n-.5)*.65))
            elif operation=="terrain_coastline":
                value=(y-y0)/max(1,h-1)+(.5-n)*.45
            elif operation=="terrain_dunes":
                wavelength=_real(args,"wavelength",2,256,10)
                value=.5+.35*math.sin(u*2*math.pi/wavelength+n*2)
            elif operation=="terrain_contours":
                bands=_integer(args,"bands",2,32) if "bands" in args else 5
                value=(math.floor(n*bands)%2)
            elif operation=="terrain_cliff_band":
                band=_real(args,"band_width",.5,128,4)
                value=1. if abs(v-n*3+1.5)<=band else 0.
            else:
                heat=_noise(seed+1,x,y,scale*1.2)
                moisture=_noise(seed+2,x,y,scale*.8)
                value=.4*n+.3*heat+.3*moisture
            paint(x,y,wall if value>=threshold else floor)
    elif operation=="terrain_crater":
        radius=_real(args,"radius",.5,512,max(1,min(w,h)/3))
        rim=_real(args,"rim",.1,32,2)
        for x,y in points:
            d=math.hypot(x-cx,y-cy)+(_noise(seed,x,y,scale)-.5)
            paint(x,y,wall if radius-rim<=d<=radius+rim else floor)
    elif operation in ("terrain_meander_river","terrain_floodplain"):
        width=_real(args,"river_width",.5,64,1.5)
        amplitude=_real(args,"amplitude",0,128,max(1,w/5))
        for x,y in points:
            path=cx+amplitude*math.sin((y-y0)/max(2,h-1)*math.pi*3+seed%13)
            distance=abs(x-path)
            bank=width*(2.2 if operation=="terrain_floodplain" else 1.)
            if distance<=bank:
                paint(x,y,wall if distance<=width else floor)
    elif operation=="terrain_lake":
        rx=_real(args,"radius_x",.5,256,max(1,w/3))
        ry=_real(args,"radius_y",.5,256,max(1,h/3))
        for x,y in points:
            dist=math.hypot((x-cx)/rx,(y-cy)/ry)
            if dist+(_noise(seed,x,y,scale)-.5)*.2<=1:
                paint(x,y,wall)
    elif operation=="terrain_talus":
        iterations=_integer(args,"iterations",1,16) if "iterations" in args else 3
        for x,y in points:
            paint(x,y,wall if val(x,y)==wall else floor)
        for _ in range(iterations):
            prev=output.copy()
            for x,y in points:
                neighbors=sum(prev[ny*layer.width+nx]==wall for nx,ny in
                              ((x-1,y),(x+1,y),(x,y-1),(x,y+1))
                              if (nx,ny) in region)
                if neighbors>=3:
                    paint(x,y,wall)
                elif neighbors<=1:
                    paint(x,y,floor)
    elif operation=="terrain_voronoi":
        count=_integer(args,"sites",2,64) if "sites" in args else 8
        sites=[(rng.randrange(x0,x0+w),rng.randrange(y0,y0+h)) for _ in range(count)]
        for x,y in points:
            nearest=min(range(count),key=lambda i:(x-sites[i][0])**2+(y-sites[i][1])**2)
            paint(x,y,wall if nearest%2 else floor)
    elif operation=="terrain_cave_automata":
        steps=_integer(args,"iterations",1,10) if "iterations" in args else 4
        density=_real(args,"density",0,1,.45)
        for x,y in points:
            paint(x,y,wall if rng.random()<density else floor)
        for _ in range(steps):
            prior=output.copy()
            for x,y in points:
                count=sum((nx,ny) not in region or prior[ny*layer.width+nx]==wall
                          for dy in (-1,0,1) for dx in (-1,0,1)
                          if (dx or dy) for nx,ny in [(x+dx,y+dy)])
                paint(x,y,wall if count>=5 else floor)
    elif operation=="terrain_room_dungeon":
        room_count=_integer(args,"rooms",1,64) if "rooms" in args else 8
        for x,y in points:
            paint(x,y,wall)
        centers=[]
        for _ in range(room_count):
            rw=min(w,max(2,rng.randrange(2,max(3,w//3+1))))
            rh=min(h,max(2,rng.randrange(2,max(3,h//3+1))))
            px=rng.randint(x0,x0+w-rw)
            py=rng.randint(y0,y0+h-rh)
            for y in range(py,py+rh):
                for x in range(px,px+rw):
                    paint(x,y,floor)
            center=(px+rw//2,py+rh//2)
            if centers:
                for x,y in _line(*centers[-1],*center):
                    paint(x,y,floor)
            centers.append(center)
    elif operation=="terrain_depth_maze":
        for x,y in points:
            paint(x,y,wall)
        start=(x0+(1 if w>2 else 0),y0+(1 if h>2 else 0))
        cells=[start]
        visited={start}
        paint(*start,floor)
        while cells:
            x,y=cells[-1]
            choices=[]
            for dx,dy in ((2,0),(-2,0),(0,2),(0,-2)):
                nxt=(x+dx,y+dy)
                if nxt in region and nxt not in visited:
                    choices.append((dx,dy,nxt))
            if not choices:
                cells.pop()
                continue
            dx,dy,nxt=rng.choice(choices)
            paint(x+dx//2,y+dy//2,floor)
            paint(*nxt,floor)
            visited.add(nxt)
            cells.append(nxt)
    elif operation=="terrain_road_links":
        nodes=args.get("nodes")
        if (type(nodes) is not list or not 2<=len(nodes)<=64
                or any(type(p) is not list or len(p)!=2 or
                       any(type(v) is not int for v in p) or tuple(p) not in region
                       for p in nodes)):
            raise StudioError("road network requires in-region integer waypoints")
        radius=_integer(args,"radius",0,8) if "radius" in args else 0
        for start,end in zip(nodes,nodes[1:]):
            for px,py in _line(*start,*end):
                for dy in range(-radius,radius+1):
                    for dx in range(-radius,radius+1):
                        if dx*dx+dy*dy<=radius*radius:
                            paint(px+dx,py+dy,floor)
                paint(px,py,floor)
    elif operation=="terrain_avoidance_path":
        start=(_integer(args,"start_x",x0,x0+w-1),
               _integer(args,"start_y",y0,y0+h-1))
        end=(_integer(args,"end_x",x0,x0+w-1),
             _integer(args,"end_y",y0,y0+h-1))
        if start==end:
            raise StudioError("path requires two distinct map nodes")
        frontier=[(0,0,start)]
        cost={start:0}
        came={}
        while frontier:
            _,spent,node=heappop(frontier)
            if spent!=cost.get(node):
                continue
            if node==end:
                break
            x,y=node
            for nxt in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if nxt not in region:
                    continue
                step=4 if val(*nxt)==wall else 1
                nxt_cost=spent+step
                if nxt_cost<cost.get(nxt,math.inf):
                    cost[nxt]=nxt_cost
                    came[nxt]=node
                    estimate=abs(nxt[0]-end[0])+abs(nxt[1]-end[1])
                    heappush(frontier,(nxt_cost+estimate,nxt_cost,nxt))
        if end not in came:
            raise StudioError("terrain route has no connected map path")
        here=end
        while here!=start:
            paint(*here,floor)
            here=came[here]
        paint(*start,floor)
    else:
        raise StudioError("unimplemented original procedural operation")
    if output==old:
        raise StudioError("procedural recipe did not change any selected map tile")
    return _replace_layer(project,idx,replace(layer,data=tuple(output)))
