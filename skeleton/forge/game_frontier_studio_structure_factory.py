"""Fifty playable, source-authored architectural and traversal tile blueprints.

Different templates carve real walkable floors from the currently selected
wall palette. Their outputs enter existing Godot 4 terrain and waypoint routes.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Mapping, Any
import math
import random

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_procedural_edit import _line, _seed

STRUCTURE_ACTIONS=(
    "structure_village_square",
    "structure_market_stalls",
    "structure_courtyard",
    "structure_town_grid",
    "structure_radial_city",
    "structure_harbor_piers",
    "structure_farm_fields",
    "structure_orchard_rows",
    "structure_house_cluster",
    "structure_canal_district",
    "structure_castle_keep",
    "structure_outer_wall",
    "structure_gatehouse",
    "structure_corner_bastions",
    "structure_moat_bridge",
    "structure_watchtowers",
    "structure_wall_walk",
    "structure_arrow_slits",
    "structure_turret_ring",
    "structure_fortified_crossroads",
    "structure_dungeon_rooms",
    "structure_dungeon_corridors",
    "structure_spiral_vault",
    "structure_treasure_chambers",
    "structure_pillar_hall",
    "structure_prison_cells",
    "structure_cathedral_nave",
    "structure_catacomb_grid",
    "structure_trap_gauntlet",
    "structure_boss_arena",
    "structure_factory_floor",
    "structure_conveyor_lanes",
    "structure_power_grid",
    "structure_storage_racks",
    "structure_warehouse_aisles",
    "structure_rail_depot",
    "structure_shipyard_slips",
    "structure_mining_shafts",
    "structure_pipeline_array",
    "structure_reactor_chamber",
    "structure_suspension_bridge",
    "structure_stepping_stones",
    "structure_ramp_switchbacks",
    "structure_cliff_stairs",
    "structure_tunnel_bore",
    "structure_treetop_walks",
    "structure_sky_platforms",
    "structure_rope_bridge",
    "structure_portal_plaza",
    "structure_island_airfield",
)


def edit_structure(project: StudioProject, action: str, args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in STRUCTURE_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unregistered world architecture authoring tool")
    idx,layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor=_tile(layer,args,"floor")
    wall=_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("architecture needs independent floor and wall tiles")
    rng=random.Random(_seed(args))
    data=list(layer.data)
    def put(x,y,t):
        if x0<=x<x0+w and y0<=y<y0+h:
            data[y*layer.width+x]=t
    def rect(x,y,width,height,t):
        for xx in range(x,x+max(0,width)):
            for yy in range(y,y+max(0,height)):
                put(xx,yy,t)
    def ring(x,y,width,height,t):
        for xx in range(x,x+width):
            put(xx,y,t)
            put(xx,y+height-1,t)
        for yy in range(y,y+height):
            put(x,yy,t)
            put(x+width-1,yy,t)
    def path(a,b,t=0,thickness=0):
        for px,py in _line(*a,*b):
            for dx in range(-thickness,thickness+1):
                for dy in range(-thickness,thickness+1):
                    if dx*dx+dy*dy<=thickness*thickness:
                        put(px+dx,py+dy,floor if t==0 else wall)
    def circle(cx,cy,r,t,fill):
        for x in range(x0,x0+w):
            for y in range(y0,y0+h):
                d=math.hypot(x-cx,y-cy)
                if d<=r and (fill or d>=r-1):
                    put(x,y,t)
    def dotted(cols,rows,t):
        for y in range(y0,y0+h,max(1,rows)):
            for x in range(x0,x0+w,max(1,cols)):
                put(x,y,t)
    center=(x0+w//2,y0+h//2)
    local=STRUCTURE_ACTIONS.index(action)
    family,mode=divmod(local,10)
    rect(x0,y0,w,h,wall)
    if family==0:
        rect(x0+1,y0+1,w-2,h-2,floor)
        if mode==0:
            rect(center[0]-max(1,w//5),center[1]-max(1,h//5),max(2,w//3),max(2,h//3),wall)
        elif mode==1:
            for x in range(x0+2,x0+w-2,3):
                rect(x,y0+2,2,2,wall)
            path((x0,center[1]),(x0+w-1,center[1]))
        elif mode==2:
            ring(x0+2,y0+2,max(2,w-4),max(2,h-4),wall)
            path((center[0],y0),(center[0],y0+h-1))
        elif mode==3:
            for x in range(x0+3,x0+w-1,4):path((x,y0),(x,y0+h-1),1)
            for y in range(y0+3,y0+h-1,4):path((x0,y),(x0+w-1,y),1)
        elif mode==4:
            for i in range(8):
                angle=i*math.pi/4
                path(center,(center[0]+round(w*.5*math.cos(angle)),
                             center[1]+round(h*.5*math.sin(angle))))
        elif mode==5:
            for x in range(x0+2,x0+w-2,4):
                path((x,y0),(x,y0+h-1))
        elif mode==6:
            for y in range(y0+2,y0+h-2,3):path((x0+2,y),(x0+w-3,y),1)
        elif mode==7:
            dotted(3,3,wall)
        elif mode==8:
            for i in range(5):
                px=rng.randrange(x0,x0+w)
                py=rng.randrange(y0,y0+h)
                ring(px,py,min(4,x0+w-px),min(4,y0+h-py),wall)
        else:
            for x in range(x0+3,x0+w-1,4):path((x,y0),(x,y0+h-1),1)
            for x in range(x0+1,x0+w-1,4):path((x,y0),(x,y0+h-1))
    elif family==1:
        rect(x0+1,y0+1,w-2,h-2,floor)
        ring(x0+1,y0+1,max(2,w-2),max(2,h-2),wall)
        if mode==0:rect(center[0]-2,center[1]-2,5,5,wall)
        elif mode==1:ring(x0+3,y0+3,max(2,w-6),max(2,h-6),wall)
        elif mode==2:rect(center[0]-1,y0,3,4,floor)
        elif mode==3:
            for at in ((x0+1,y0+1),(x0+w-3,y0+1),(x0+1,y0+h-3),(x0+w-3,y0+h-3)):
                rect(*at,3,3,wall)
        elif mode==4:
            ring(x0+3,y0+3,max(2,w-6),max(2,h-6),wall)
            path((center[0],y0),(center[0],center[1]))
        elif mode==5:
            dotted(max(2,w-3),max(2,h-3),wall)
        elif mode==6:
            ring(x0+2,y0+2,max(2,w-4),max(2,h-4),floor)
        elif mode==7:
            for x in range(x0+2,x0+w-2,3):put(x,y0+1,floor)
        elif mode==8:circle(*center,max(1,min(w,h)//3),wall,False)
        else:
            path((x0,center[1]),(x0+w-1,center[1]))
            path((center[0],y0),(center[0],y0+h-1))
    elif family==2:
        rect(x0+1,y0+1,w-2,h-2,floor)
        if mode==0:
            for i in range(4):
                x=x0+1+(i%2)*(w//2)
                y=y0+1+(i//2)*(h//2)
                ring(x,y,max(2,w//2-1),max(2,h//2-1),wall)
                put(x+1,y,floor)
        elif mode==1:
            for y in range(y0+3,y0+h-1,3):path((x0,y),(x0+w-1,y),1)
            path((center[0],y0),(center[0],y0+h-1))
        elif mode==2:
            for t in range(min(w,h)//2):
                ring(x0+t,y0+t,max(2,w-2*t),max(2,h-2*t),floor if t%2 else wall)
                put(x0+t,y0+t,floor)
        elif mode==3:
            for i in range(4):
                px=x0+2+(i%2)*max(1,w//2)
                py=y0+2+(i//2)*max(1,h//2)
                circle(px,py,max(1,min(w,h)//7),wall,False)
        elif mode==4:dotted(3,3,wall)
        elif mode==5:
            for x in range(x0+2,x0+w-1,3):path((x,y0+1),(x,y0+h-2),1)
            path((x0,center[1]),(x0+w-1,center[1]))
        elif mode==6:
            path((center[0],y0),(center[0],y0+h-1))
            for x in (x0+2,x0+w-3):path((x,y0+1),(x,y0+h-2),1)
        elif mode==7:
            for y in range(y0+2,y0+h-2,3):path((x0,y),(x0+w-1,y),1)
            for x in range(x0+2,x0+w-2,5):path((x,y0),(x,y0+h-1))
        elif mode==8:
            for x in range(x0+3,x0+w-1,4):path((x,y0+1),(x,y0+h-2),1)
        else:circle(*center,max(2,min(w,h)//3),floor,True)
    elif family==3:
        rect(x0+1,y0+1,w-2,h-2,floor)
        if mode==0:
            dotted(4,4,wall)
        elif mode==1:
            for y in range(y0+2,y0+h-2,3):path((x0+1,y),(x0+w-2,y),1)
        elif mode==2:
            for x in range(x0+3,x0+w-2,4):path((x,y0+2),(x,y0+h-3),1)
        elif mode==3:
            for x in range(x0+2,x0+w-2,3):rect(x,y0+2,2,max(1,h-4),wall)
        elif mode==4:
            for y in range(y0+2,y0+h-2,3):rect(x0+2,y,max(1,w-4),2,wall)
        elif mode==5:
            for x in range(x0+1,x0+w-1,3):path((x,y0),(x,y0+h-1),1)
        elif mode==6:
            for x in range(x0+2,x0+w-2,3):path((x,y0),(x,y0+h-1))
        elif mode==7:
            for x in range(x0+2,x0+w-1,4):path((x,y0),(x,y0+h-1),1)
        elif mode==8:
            path((x0,center[1]),(x0+w-1,center[1]),1)
            for x in range(x0+3,x0+w-1,4):put(x,center[1],floor)
        else:circle(*center,max(2,min(w,h)//3),wall,False)
    else:
        # Travel infrastructure is deliberately connected and floor-passable.
        if mode==0:
            path((x0,center[1]),(x0+w-1,center[1]),0,1)
            dotted(4,4,wall)
        elif mode==1:
            for i in range(min(w,h)):
                put(x0+i,y0+i,floor)
                if i%2==0:put(x0+i,min(y0+h-1,y0+i+1),floor)
        elif mode==2:
            for i in range(h):
                x=x0+(i%4)*max(1,(w-1)//4)
                path((x,y0+i),(x0+w-1-x+x0,y0+i))
        elif mode==3:
            for i in range(min(w,h)):path((x0+i,y0+i),(x0+i,y0+i),0)
        elif mode==4:
            path((x0,center[1]),(x0+w-1,center[1]),0,2)
        elif mode==5:
            for y in range(y0+1,y0+h-1,3):path((x0,y),(x0+w-1,y))
            path((center[0],y0),(center[0],y0+h-1))
        elif mode==6:
            for i in range(5):
                x=x0+(i%3)*max(1,w//3)
                y=y0+(i//3)*max(1,h//2)
                rect(x,y,max(1,w//4),max(1,h//4),floor)
            path((x0,center[1]),(x0+w-1,center[1]))
        elif mode==7:path((x0,center[1]),(x0+w-1,center[1]))
        elif mode==8:
            circle(*center,max(2,min(w,h)//3),floor,True)
            circle(*center,max(1,min(w,h)//6),wall,False)
        else:
            for x in range(x0+1,x0+w-1,3):path((x,y0),(x,y0+h-1))
            path((x0,center[1]),(x0+w-1,center[1]))
    if tuple(data)==layer.data:
        raise StudioError("blueprint made no level change")
    return _replace_layer(project,idx,replace(layer,data=tuple(data)))
