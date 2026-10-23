"""Fifteen real formation, world-population and actor-group editing tools.

Operations create and move canonical StudioPlacement records used by the
existing expedition compiler (where every placement becomes an interactable
world waypoint). Selected actor IDs remain stable for native zone bindings.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping
import math
import random

from .game_frontier_studio import StudioError, StudioProject, StudioPlacement
from .game_frontier_studio_map_edit import _name, _integer

POPULATION_ACTIONS = (
    "formation_line", "formation_arc", "formation_ring", "formation_spiral",
    "formation_wedge", "formation_stagger", "formation_jitter_grid",
    "formation_scatter", "formation_poisson", "formation_waypoint_path",
    "formation_perimeter", "actors_translate", "actors_rotate",
    "actors_mirror", "actors_reassign_prefab",
)


def _real(args: Mapping[str, Any], field: str, lo: float=-1e6, hi: float=1e6, default=None) -> float:
    val=args.get(field,default)
    if type(val) not in (float,int) or not math.isfinite(val) or not lo<=val<=hi:
        raise StudioError(field+" must be a bounded finite world coordinate")
    return float(val)


def _origin(args):
    return (_real(args,"x",default=0),_real(args,"y",default=0),_real(args,"z",default=0))


def _prefab(project, args):
    name=_name(args,"prefab_id")
    if name not in {x.prefab_id for x in project.prefabs}:
        raise StudioError("formation requires an actually authored source prefab")
    return name


def _count(args):
    return _integer(args,"count",1,1024)


def _facing(args):
    return _real(args,"facing_deg",-36000,36000,0)%360


def _angles(args):
    return math.radians(_real(args,"angle_deg",-360,360,0))


def _line_points(waypoints, count):
    segments=[]
    total=0.
    for a,b in zip(waypoints,waypoints[1:]):
        length=math.dist(a,b)
        if length<=0:
            continue
        segments.append((a,b,total,total+length))
        total+=length
    if total<=0:
        raise StudioError("path points must have nonzero length")
    positions=[]
    for i in range(count):
        dist=total*(i/max(1,count-1))
        a,b,before,after=next((s for s in segments if dist<=s[3]),segments[-1])
        t=max(0.,min(1.,(dist-before)/(after-before)))
        positions.append(tuple(a[j]*(1-t)+b[j]*t for j in range(3)))
    return positions


def _indices(project,args):
    raw=args.get("indices")
    if (type(raw) is not list or not 1<=len(raw)<=256
            or any(type(i) is not int or not 0<=i<len(project.placements) for i in raw)
            or len(set(raw))!=len(raw)):
        raise StudioError("exact unique placed-actor indices required")
    return raw


def edit_population(project: StudioProject, operation: str,
                    args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or operation not in POPULATION_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unknown source-backed game population operation")
    placements=list(project.placements)
    if operation.startswith("actors_"):
        indices=_indices(project,args)
        cx=_real(args,"pivot_x",default=0)
        cy=_real(args,"pivot_y",default=0)
        if operation=="actors_translate":
            dx,dy,dz=(_real(args,"dx",default=0),
                      _real(args,"dy",default=0),_real(args,"dz",default=0))
            if dx==dy==dz==0:
                raise StudioError("actor move must change a source coordinate")
            for i in indices:
                p=placements[i]
                placements[i]=replace(p,x=p.x+dx,y=p.y+dy,z=p.z+dz)
        elif operation=="actors_rotate":
            angle=_angles(args)
            if angle==0:
                raise StudioError("actor rotation must change angle")
            cs,sn=math.cos(angle),math.sin(angle)
            for i in indices:
                p=placements[i]
                x,y=p.x-cx,p.y-cy
                placements[i]=replace(p,x=cx+x*cs-y*sn,y=cy+x*sn+y*cs,
                                      facing_deg=(p.facing_deg+math.degrees(angle))%360)
        elif operation=="actors_mirror":
            axis=args.get("axis")
            if axis not in ("x","y"):
                raise StudioError("group mirror needs x/y axis")
            for i in indices:
                p=placements[i]
                if axis=="x":
                    placements[i]=replace(p,x=2*cx-p.x,
                                          facing_deg=(180-p.facing_deg)%360)
                else:
                    placements[i]=replace(p,y=2*cy-p.y,
                                          facing_deg=(-p.facing_deg)%360)
        elif operation=="actors_reassign_prefab":
            name=_prefab(project,args)
            for i in indices:
                placements[i]=replace(placements[i],prefab_id=name)
        return replace(project,placements=tuple(placements))
    name=_prefab(project,args)
    count=_count(args)
    x,y,z=_origin(args)
    angle=_angles(args)
    heading=_facing(args)
    spacing=_real(args,"spacing",.1,10000,2)
    radius=_real(args,"radius",.1,10000,max(2,count*spacing/(2*math.pi)))
    rng=random.Random(_integer(args,"seed",0,2**63-1) if "seed" in args else 0)
    points=[]
    if operation=="formation_line":
        points=[(x+i*spacing*math.cos(angle),y+i*spacing*math.sin(angle),z)
                for i in range(count)]
    elif operation=="formation_arc":
        sweep=math.radians(_real(args,"sweep_deg",1,360,180))
        points=[(x+radius*math.cos(angle+sweep*i/max(1,count-1)),
                 y+radius*math.sin(angle+sweep*i/max(1,count-1)),z) for i in range(count)]
    elif operation=="formation_ring":
        points=[(x+radius*math.cos(angle+2*math.pi*i/count),
                 y+radius*math.sin(angle+2*math.pi*i/count),z) for i in range(count)]
    elif operation=="formation_spiral":
        turns=_real(args,"turns",.25,16,2)
        points=[(x+radius*(i+1)/count*math.cos(angle+2*math.pi*turns*i/count),
                 y+radius*(i+1)/count*math.sin(angle+2*math.pi*turns*i/count),z)
                for i in range(count)]
    elif operation=="formation_wedge":
        for i in range(count):
            row=math.floor((math.sqrt(8*i+1)-1)/2)
            index=i-row*(row+1)//2
            forward=row*spacing
            side=(index-row/2)*spacing
            points.append((x+forward*math.cos(angle)-side*math.sin(angle),
                           y+forward*math.sin(angle)+side*math.cos(angle),z))
    elif operation in ("formation_stagger","formation_jitter_grid"):
        columns=_integer(args,"columns",1,128) if "columns" in args else max(1,round(math.sqrt(count)))
        jitter=_real(args,"jitter",0,.49,.25) if operation=="formation_jitter_grid" else 0
        for i in range(count):
            row,col=divmod(i,columns)
            ox=(col+(row%2)*.5 if operation=="formation_stagger" else col)
            ox+=(rng.random()-.5)*jitter
            oy=row+(rng.random()-.5)*jitter
            points.append((x+spacing*(ox*math.cos(angle)-oy*math.sin(angle)),
                           y+spacing*(ox*math.sin(angle)+oy*math.cos(angle)),z))
    elif operation=="formation_scatter":
        for _ in range(count):
            theta=rng.random()*2*math.pi
            rad=radius*math.sqrt(rng.random())
            points.append((x+rad*math.cos(theta),y+rad*math.sin(theta),z))
    elif operation=="formation_poisson":
        separation=_real(args,"min_distance",.05,radius*2,spacing*.6)
        for _ in range(count):
            for _attempt in range(1000):
                theta=rng.random()*2*math.pi
                dist=radius*math.sqrt(rng.random())
                proposal=(x+dist*math.cos(theta),y+dist*math.sin(theta),z)
                if all(math.dist(proposal,p)>=separation for p in points):
                    points.append(proposal)
                    break
            else:
                raise StudioError("insufficient space for separated actor placement")
    elif operation=="formation_waypoint_path":
        raw=args.get("waypoints")
        if (type(raw) is not list or not 2<=len(raw)<=128 or
                any(type(row) is not list or len(row)!=3 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6
                        for v in row) for row in raw)):
            raise StudioError("formation waypoint path requires valid authored XYZ")
        points=_line_points(raw,count)
    elif operation=="formation_perimeter":
        width=_real(args,"width",.1,1e5)
        height=_real(args,"height",.1,1e5)
        corners=[[x,y,z],[x+width,y,z],[x+width,y+height,z],
                 [x,y+height,z],[x,y,z]]
        points=_line_points(corners,count+1)[:-1]
    else:
        raise StudioError("unknown actor formation recipe")
    if len(placements)+len(points)>100000:
        raise StudioError("placed-actor budget exhausted")
    authored=tuple(StudioPlacement(name,*p,facing_deg=heading) for p in points)
    return replace(project,placements=tuple(placements)+authored)
