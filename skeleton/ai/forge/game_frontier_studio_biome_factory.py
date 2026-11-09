"""Fifty deterministic authored geology, biome, cave and sky-world generators.

Each recipe writes real palette-indexed Studio MapLayer cells. They use
distinct mathematical masks, local gradients, hydrology and seeded noise.
Native Godot terrain/route export consumes the edited layer without a new
project authority. Recipes are additive to the previous 250 tools.
"""
from __future__ import annotations

from dataclasses import replace
import math
import random
from typing import Any, Mapping

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _replace_layer
from .game_frontier_studio_procedural_edit import _fbm, _real, _seed

BIOME_ACTIONS = (
    "terrain_fault_lines",
    "terrain_plate_edges",
    "terrain_tectonic_ridges",
    "terrain_graben_valley",
    "terrain_volcano_cone",
    "terrain_lava_channels",
    "terrain_caldera_ring",
    "terrain_mesa_terraces",
    "terrain_karst_sinkholes",
    "terrain_mountain_chain",
    "terrain_alluvial_fans",
    "terrain_delta_branches",
    "terrain_oxbow_lakes",
    "terrain_braided_streams",
    "terrain_watershed_divide",
    "terrain_glacial_valley",
    "terrain_moraine_ridges",
    "terrain_fjord_channels",
    "terrain_reef_atolls",
    "terrain_tidal_flats",
    "terrain_rainforest",
    "terrain_savanna",
    "terrain_taiga",
    "terrain_tundra",
    "terrain_alpine_meadow",
    "terrain_desert_badlands",
    "terrain_mangrove",
    "terrain_swamp_bog",
    "terrain_grass_steppe",
    "terrain_volcanic_ash",
    "terrain_fungal_caverns",
    "terrain_crystal_caves",
    "terrain_stalagmite_fields",
    "terrain_limestone_pillars",
    "terrain_underground_rivers",
    "terrain_lava_tubes",
    "terrain_geode_chambers",
    "terrain_abyssal_pits",
    "terrain_bioluminescent_groves",
    "terrain_ruined_catacombs",
    "terrain_floating_islands",
    "terrain_cloud_banks",
    "terrain_wind_corridors",
    "terrain_sky_arches",
    "terrain_storm_belts",
    "terrain_levitation_nodes",
    "terrain_aurora_paths",
    "terrain_meteor_craters",
    "terrain_gravity_wells",
    "terrain_portal_constellations",
)


def _landform(index: int, u: float, v: float, n: float, m: float,
              h: float, angle: float, phase: float) -> float:
    """Fifty separate dimensionless geology/biome fields (thresholded to tiles)."""
    x=u*math.cos(angle)-v*math.sin(angle)
    y=u*math.sin(angle)+v*math.cos(angle)
    r=math.hypot(u,v)
    theta=math.atan2(v,u)
    t=phase
    if index==0: return 1-abs(math.sin(x*6+t+n*1.3))
    if index==1: return abs(math.sin(x*8+n*2)) * abs(math.cos(y*4+m))
    if index==2: return math.exp(-(y*5+n-.5)**2)*(.6+.4*h)
    if index==3: return min(1,abs(y*3+n-1)*.5)
    if index==4: return max(0,1-r*.95)+(.5-n)*.3
    if index==5: return max(0,1-abs(x*3+math.sin(y*12+t)*.5)) * m
    if index==6: return math.exp(-((r-.65)*6)**2)
    if index==7: return (math.floor((1-r)*7)%3)/2+n*.15
    if index==8: return max(0,1-min(abs(x-.5),abs(y+.2))*3)*m
    if index==9: return .5+.45*math.sin(x*9+t)*(1-abs(y*.5))
    if index==10:return max(0,1-abs(y-abs(x)*.5)*5)*n
    if index==11:return max(0,1-abs(y-math.sin(x*8+t)*.4)*5)*(.6+.4*m)
    if index==12:return max(0,1-abs(r-.58-n*.15)*12)
    if index==13:return max(0,1-abs(y-math.sin(x*12+t)*.2)*8)+.15*math.sin(x*20)
    if index==14:return max(0,1-abs(y+n*.3-.2)*5)
    if index==15:return max(0,1-abs(y*1.2+math.sin(x*8)*.2)*3)*h
    if index==16:return max(0,1-abs(r-.55)*8)*(.5+.5*n)
    if index==17:return max(0,1-abs(x+math.sin(y*12+t)*.22)*7)
    if index==18:return math.exp(-((r-.62)*9)**2)*(.5+.5*n)
    if index==19:return min(1,max(0,.5+y*.9+(n-.5)*.5))
    if index==20:return n*.5+m*.5
    if index==21:return .4*n+.25*h+.35*max(0,1-abs(y))
    if index==22:return .5*n+.5*max(0,1-abs(u)*.65)
    if index==23:return max(0,1-abs(v)*1.4)*m
    if index==24:return n*.3+m*.3+h*.4
    if index==25:return 1-(n*.6+m*.4)
    if index==26:return max(0,1-abs(v+n-.7))*h
    if index==27:return m*.6+max(0,1-abs(x*.7))*n*.4
    if index==28:return (n+h)/2+math.sin(u*5)*.1
    if index==29:return h*.65+(1-m)*.35
    if index==30:return (1-n)*.6+(1-m)*.4
    if index==31:return (1-n)*.5+h*.5
    if index==32:return max(0,1-abs(math.sin(r*20+n*4)))*.75+h*.25
    if index==33:return max(0,1-abs(math.sin(x*10)*math.sin(y*10)))*n
    if index==34:return max(0,1-abs(y-math.sin(u*5+t)*.4)*6)
    if index==35:return max(0,1-abs(y*.8+n*.5-.4)*4)
    if index==36:return math.exp(-((r-.5)*5)**2)*m
    if index==37:return max(0,1-r*r)+(.5-n)*.45
    if index==38:return h*.35+m*.65
    if index==39:return max(0,1-abs(x*4+n-1)*3)*h
    if index==40:return max(0,1-r*.8)+(.5-n)*.5
    if index==41:return max(0,1-abs(y*4+n*.7-.35)*3)
    if index==42:return max(0,1-abs(r-.65)*5)*(.5+.5*h)
    if index==43:return max(0,1-abs(x*6+math.sin(y*6+t)*.4)*5)
    if index==44:return .4*n+.4*h+.2*abs(math.sin(x*10+t))
    if index==45:return max(0,1-abs(u*.7-v*.3-m*.25)*8)
    if index==46:return .5+.4*math.sin(theta*5+n*3+t)*max(0,1-r)
    if index==47:return max(0,1-r*.9)+.4*(m-.5)
    if index==48:return max(0,1-abs(r-.36)*6)+(.5-n)*.2
    return .45+.4*math.cos(theta*7+t)*max(0,1-r)+(.5-h)*.25


def edit_biome(project: StudioProject, action: str, args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or action not in BIOME_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("unknown executable original-world biome operation")
    index, layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor,wall=_tile(layer,args,"floor"),_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("generator needs distinct tile palette destinations")
    seed=_seed(args)
    scale=_real(args,"scale",.5,128,5)
    cutoff=_real(args,"threshold",0,1,.53)
    direction=math.radians(_real(args,"angle_deg",-360,360,0))
    phase=_real(args,"phase",-100,100,seed%31/7)
    number=BIOME_ACTIONS.index(action)
    data=list(layer.data)
    for y in range(y0,y0+h):
        v=2*(y-y0)/max(1,h-1)-1
        for x in range(x0,x0+w):
            u=2*(x-x0)/max(1,w-1)-1
            n=_fbm(seed,x,y,scale,4)
            m=_fbm(seed+7919,x,y,scale*1.4,3)
            h_noise=_fbm(seed+2111,x,y,scale*.7,3)
            value=_landform(number,u,v,n,m,h_noise,direction,phase)
            data[y*layer.width+x]=wall if value>=cutoff else floor
    if tuple(data)==layer.data:
        raise StudioError("biome recipe had no authored tile effect")
    return _replace_layer(project,index,replace(layer,data=tuple(data)))
