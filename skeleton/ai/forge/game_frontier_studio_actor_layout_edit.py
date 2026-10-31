"""Twenty-five world-placement manipulation tools (176–200).

Operate on real StudioPlacement poses without changing indexed identity of
existing actors (used by live native force fields and gameplay volumes).
"""
from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
from typing import Any
import math
import random

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_studio_map_edit import _integer, _name
from .game_frontier_studio_population_edit import _real
from .game_frontier_studio_tile_navigation import _traversable

ACTOR_LAYOUT_ACTIONS = (
    "actors_snap_grid", "actors_snap_ground", "actors_quantize_facing",
    "actors_face_point", "actors_face_actor", "actors_align_x",
    "actors_align_y", "actors_even_spacing", "actors_radial_expand",
    "actors_radial_contract", "actors_scale_cloud", "actors_shift_altitude",
    "actors_seeded_jitter", "actors_separate_overlap", "actors_snap_terrain",
    "actors_clamp_bounds", "actors_swap_poses", "actors_copy_facing",
    "actors_center_group", "actors_wave_offsets", "actors_staircase",
    "actors_terrain_walk", "actors_depth_rank", "actors_random_facing",
    "actors_clone_selected",
)


def _selected(project: StudioProject, args):
    indices=args.get("indices")
    if (type(indices) is not list or not 1<=len(indices)<=256 or
            any(type(i) is not int or not 0<=i<len(project.placements) for i in indices)
            or len(set(indices))!=len(indices)):
        raise StudioError("group layout requires unique existing actor indices")
    return indices


def _changed(original, updated):
    if not math.isfinite(updated.x) or not math.isfinite(updated.y) or not math.isfinite(updated.z):
        raise StudioError("actor transform must remain finite")
    return updated


def edit_actor_layout(project: StudioProject, operation: str,
                      args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or operation not in ACTOR_LAYOUT_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unsupported native actor pose/layout action")
    indices=_selected(project,args)
    actors=list(project.placements)
    positions={i:(actors[i].x,actors[i].y,actors[i].z) for i in indices}
    cx=sum(actors[i].x for i in indices)/len(indices)
    cy=sum(actors[i].y for i in indices)/len(indices)
    cz=sum(actors[i].z for i in indices)/len(indices)
    if operation=="actors_snap_grid":
        step=_real(args,"step",.001,10000,1)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,x=round(p.x/step)*step,y=round(p.y/step)*step)
    elif operation=="actors_snap_ground":
        z=_real(args,"ground_z",-1e6,1e6,0)
        for i in indices:
            actors[i]=replace(actors[i],z=z)
    elif operation=="actors_quantize_facing":
        step=_real(args,"degrees",1,180,45)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,facing_deg=round(p.facing_deg/step)*step%360)
    elif operation in ("actors_face_point","actors_face_actor"):
        if operation=="actors_face_actor":
            target=_integer(args,"target_index",0,len(actors)-1)
            px,py=actors[target].x,actors[target].y
        else:
            px=_real(args,"target_x")
            py=_real(args,"target_y")
        for i in indices:
            p=actors[i]
            if abs(px-p.x)+abs(py-p.y)>1e-9:
                actors[i]=replace(p,facing_deg=math.degrees(math.atan2(py-p.y,px-p.x))%360)
    elif operation in ("actors_align_x","actors_align_y"):
        axis="x" if operation.endswith("_x") else "y"
        value=_real(args,"value")
        for i in indices:
            actors[i]=replace(actors[i],**{axis:value})
    elif operation=="actors_even_spacing":
        if len(indices)<2:
            raise StudioError("spacing needs at least two actors")
        axis=args.get("axis","x")
        if axis not in ("x","y","z"):
            raise StudioError("spacing axis must be x y or z")
        sorted_ids=sorted(indices,key=lambda i:(getattr(actors[i],axis),i))
        start=getattr(actors[sorted_ids[0]],axis)
        end=getattr(actors[sorted_ids[-1]],axis)
        if start==end:
            end=start+_real(args,"distance",.01,10000,2)*(len(indices)-1)
        for k,i in enumerate(sorted_ids):
            actors[i]=replace(actors[i],**{axis:start+(end-start)*k/(len(indices)-1)})
    elif operation in ("actors_radial_expand","actors_radial_contract"):
        distance=_real(args,"distance",.01,1e5,2)
        sign=1 if operation.endswith("expand") else -1
        for k,i in enumerate(indices):
            p=actors[i]
            dx,dy=p.x-cx,p.y-cy
            norm=math.hypot(dx,dy)
            if norm==0:
                angle=k*2*math.pi/len(indices)
                dx,dy=math.cos(angle),math.sin(angle)
                norm=1
            amount=max(0,norm+sign*distance)
            actors[i]=replace(p,x=cx+dx/norm*amount,y=cy+dy/norm*amount)
    elif operation=="actors_scale_cloud":
        factor=_real(args,"factor",.01,100,1.5)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,x=cx+(p.x-cx)*factor,y=cy+(p.y-cy)*factor,
                              z=cz+(p.z-cz)*factor)
    elif operation=="actors_shift_altitude":
        delta=_real(args,"dz",-.999999e6,.999999e6,3)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,z=p.z+delta)
    elif operation=="actors_seeded_jitter":
        rng=random.Random(_integer(args,"seed",0,2**63-1))
        amplitude=_real(args,"amplitude",.001,10000,1)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,x=p.x+rng.uniform(-amplitude,amplitude),
                              y=p.y+rng.uniform(-amplitude,amplitude))
    elif operation=="actors_separate_overlap":
        radius=_real(args,"minimum_distance",.1,10000,2)
        for _ in range(40):
            moved=False
            for k,i in enumerate(indices):
                for j in indices[k+1:]:
                    a,b=actors[i],actors[j]
                    dx,dy=b.x-a.x,b.y-a.y
                    norm=math.hypot(dx,dy)
                    if norm>=radius:
                        continue
                    if norm<1e-9:
                        angle=(i*37+j*13)*math.pi/180
                        dx,dy=math.cos(angle),math.sin(angle)
                        norm=1
                    step=(radius-norm)*.5
                    ux,uy=dx/norm,dy/norm
                    actors[i]=replace(a,x=a.x-ux*step,y=a.y-uy*step)
                    actors[j]=replace(b,x=b.x+ux*step,y=b.y+uy*step)
                    moved=True
            if not moved:
                break
    elif operation=="actors_snap_terrain":
        layer_id=_name(args,"layer")
        layer=next((l for l in project.layers if l.layer_id==layer_id),None)
        if layer is None:
            raise StudioError("actor terrain binding needs real map layer")
        if not any(v>=0 for v in layer.data):
            raise StudioError("cannot snap to wholly erased world")
        valid={(x,y) for y in range(layer.height) for x in range(layer.width)
               if _traversable(layer,x,y)}
        for i in indices:
            p=actors[i]
            x,y=min(valid,key=lambda v:((p.x-v[0])**2+(p.y-v[1])**2,v))
            actors[i]=replace(p,x=float(x),y=float(y),z=float(layer.elevation_m))
    elif operation=="actors_clamp_bounds":
        min_x=_real(args,"min_x")
        max_x=_real(args,"max_x")
        min_y=_real(args,"min_y")
        max_y=_real(args,"max_y")
        if min_x>=max_x or min_y>=max_y:
            raise StudioError("valid nonempty 3D authored world bounds required")
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,x=max(min_x,min(max_x,p.x)),y=max(min_y,min(max_y,p.y)))
    elif operation=="actors_swap_poses":
        if len(indices)!=2:
            raise StudioError("pose swap requires two distinct actor indices")
        i,j=indices
        a,b=actors[i],actors[j]
        actors[i]=replace(a,x=b.x,y=b.y,z=b.z,facing_deg=b.facing_deg)
        actors[j]=replace(b,x=a.x,y=a.y,z=a.z,facing_deg=a.facing_deg)
    elif operation=="actors_copy_facing":
        source=_integer(args,"source_index",0,len(actors)-1)
        bearing=actors[source].facing_deg
        for i in indices:
            actors[i]=replace(actors[i],facing_deg=bearing)
    elif operation=="actors_center_group":
        x=_real(args,"x")
        y=_real(args,"y")
        z=_real(args,"z",-1e6,1e6,cz)
        for i in indices:
            p=actors[i]
            actors[i]=replace(p,x=p.x+x-cx,y=p.y+y-cy,z=p.z+z-cz)
    elif operation=="actors_wave_offsets":
        amplitude=_real(args,"amplitude",.001,1e5,2)
        period=_real(args,"period",.1,1000,3)
        sorted_ids=sorted(indices)
        for k,i in enumerate(sorted_ids):
            p=actors[i]
            actors[i]=replace(p,y=p.y+amplitude*math.sin(2*math.pi*k/period))
    elif operation=="actors_staircase":
        delta=_real(args,"step",.001,10000,1)
        for k,i in enumerate(sorted(indices)):
            p=actors[i]
            actors[i]=replace(p,z=p.z+delta*k)
    elif operation=="actors_terrain_walk":
        layer_id=_name(args,"layer")
        layer=next((l for l in project.layers if l.layer_id==layer_id),None)
        if layer is None:
            raise StudioError("source map layer not found")
        terrain=[(x,y) for y in range(layer.height) for x in range(layer.width)
                 if _traversable(layer,x,y)]
        if len(terrain)<len(indices):
            raise StudioError("insufficient terrain for unique actors")
        occupied=set()
        for i in indices:
            p=actors[i]
            at=min((loc for loc in terrain if loc not in occupied),
                   key=lambda loc:((p.x-loc[0])**2+(p.y-loc[1])**2,loc))
            occupied.add(at)
            actors[i]=replace(p,x=float(at[0]),y=float(at[1]),
                              z=float(layer.elevation_m))
    elif operation=="actors_depth_rank":
        minimum=_real(args,"base_z")
        spacing=_real(args,"step_z",.001,1e5,2)
        for k,i in enumerate(sorted(indices,key=lambda i:(actors[i].y,i))):
            actors[i]=replace(actors[i],z=minimum+k*spacing)
    elif operation=="actors_random_facing":
        rng=random.Random(_integer(args,"seed",0,2**63-1))
        for i in indices:
            actors[i]=replace(actors[i],facing_deg=rng.randrange(0,360))
    elif operation=="actors_clone_selected":
        dx=_real(args,"dx",-1e5,1e5,2)
        dy=_real(args,"dy",-1e5,1e5,2)
        dz=_real(args,"dz",-1e5,1e5,0)
        for i in indices:
            p=actors[i]
            actors.append(replace(p,x=p.x+dx,y=p.y+dy,z=p.z+dz))
    else:
        raise StudioError("unknown placed actor manipulation")
    result=tuple(actors)
    if result==project.placements:
        raise StudioError("selected transform made no actual world source edit")
    return replace(project,placements=result)
