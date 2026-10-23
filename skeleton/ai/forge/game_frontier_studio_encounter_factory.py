"""Fifty original-game encounter population recipes with interactive NPC events.

Spawns actual previously authored StudioPrefab instances at bounded XYZ poses
and writes unique StudioEvent interactions targeting their stable source IDs.
Native expedition waypoint/actor and event compilers consume these records.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping
import math
import random

from .game_frontier_studio import StudioProject, StudioPlacement, StudioEvent, StudioError
from .game_frontier_studio_map_edit import _name, _integer
from .game_frontier_studio_population_edit import _real

ENCOUNTER_ACTIONS=(
    "encounter_village_crowd",
    "encounter_market_vendors",
    "encounter_tavern_guests",
    "encounter_festival_parade",
    "encounter_harbor_workers",
    "encounter_farm_hands",
    "encounter_caravan_merchants",
    "encounter_city_patrol",
    "encounter_castle_guards",
    "encounter_royal_court",
    "encounter_wolf_pack",
    "encounter_deer_herd",
    "encounter_bird_flock",
    "encounter_fish_school",
    "encounter_insect_swarm",
    "encounter_horse_stampede",
    "encounter_bear_den",
    "encounter_predator_ring",
    "encounter_migratory_line",
    "encounter_turtle_nesting",
    "encounter_squad_wedge",
    "encounter_siege_lines",
    "encounter_archer_wall",
    "encounter_shield_circle",
    "encounter_cavalry_charge",
    "encounter_ambush_arcs",
    "encounter_flanking_pincer",
    "encounter_rear_guard",
    "encounter_scout_net",
    "encounter_boss_minions",
    "encounter_sky_pirates",
    "encounter_airship_crew",
    "encounter_cloud_drakes",
    "encounter_floating_island_settlers",
    "encounter_wind_surfers",
    "encounter_tower_watchers",
    "encounter_balloon_riders",
    "encounter_glider_convoy",
    "encounter_sky_fishermen",
    "encounter_aurora_procession",
    "encounter_dungeon_slimes",
    "encounter_cave_bats",
    "encounter_crypt_guardians",
    "encounter_labyrinth_wardens",
    "encounter_treasure_mimics",
    "encounter_portal_sentinels",
    "encounter_ruin_explorers",
    "encounter_mine_workers",
    "encounter_fungal_foragers",
    "encounter_underground_merchants",
)


def _place(mode: int, index: int, count: int, radius: float,
           angle: float, spacing: float, rng: random.Random):
    """50 independent geometry profiles; returned coordinates are local."""
    t=index/max(1,count-1)
    theta=angle+2*math.pi*index/max(1,count)
    group,style=divmod(mode,10)
    if group==0:
        if style==0:return (rng.uniform(-radius,radius),rng.uniform(-radius,radius),0)
        if style==1:return ((index%5-2)*spacing,(index//5-2)*spacing,0)
        if style==2:return (radius*math.cos(theta),radius*math.sin(theta),0)
        if style==3:return (spacing*index,math.sin(index*.6)*spacing,0)
        if style==4:return ((index%3)*spacing,(index//3)*spacing,0)
        if style==5:return ((index%4)*spacing,(index//4)*spacing,0)
        if style==6:return (index*spacing,index%2*spacing,0)
        if style==7:return (radius*math.cos(theta),radius*math.sin(theta),0)
        if style==8:return (radius*math.cos(theta),radius*math.sin(theta),0)
        return ((index%6)*spacing,(index//6)*spacing,0)
    if group==1:
        if style==0:return (radius*math.cos(theta)+rng.uniform(-1,1),radius*math.sin(theta),0)
        if style==1:return (rng.uniform(-radius,radius),rng.uniform(-radius/2,radius/2),0)
        if style==2:return (radius*math.cos(theta),radius*math.sin(theta),abs(math.sin(theta))*radius)
        if style==3:return (radius*math.sin(index*.8),radius*math.cos(index*.8),-index*spacing/10)
        if style==4:return (radius*rng.uniform(-1,1),radius*rng.uniform(-1,1),rng.uniform(0,3))
        if style==5:return (index*spacing,math.sin(index)*spacing,0)
        if style==6:return (rng.uniform(-radius,radius),rng.uniform(-radius,radius),0)
        if style==7:return (radius*math.cos(theta),radius*math.sin(theta),0)
        if style==8:return (index*spacing,radius*math.sin(index*.2),0)
        return (radius*math.cos(theta),radius*math.sin(theta),0)
    if group==2:
        if style==0:return (index*spacing,(index%3-1)*spacing,0)
        if style==1:return (index*spacing,(index//5)*spacing,0)
        if style==2:return ((index%8)*spacing,(index//8)*spacing,0)
        if style==3:return (radius*math.cos(theta),radius*math.sin(theta),0)
        if style==4:return (index*spacing,rng.uniform(-spacing,spacing),0)
        if style==5:return (radius*math.cos(theta)*.7,radius*math.sin(theta),0)
        if style==6:return ((index%2)*radius+(index//2)*spacing,(-1)**index*radius*.5,0)
        if style==7:return (-index*spacing,(index%2)*spacing,0)
        if style==8:return (radius*math.cos(theta),radius*math.sin(theta),rng.uniform(0,3))
        return (radius*math.cos(theta),radius*math.sin(theta),-t*radius*.5)
    if group==3:
        if style==0:return (radius*math.cos(theta),radius*math.sin(theta),2+radius*.1)
        if style==1:return ((index%4)*spacing,(index//4)*spacing,2)
        if style==2:return (radius*math.cos(theta),radius*math.sin(theta),index%4*spacing)
        if style==3:return (rng.uniform(-radius,radius),rng.uniform(-radius,radius),5)
        if style==4:return (index*spacing,math.sin(index)*spacing,1+index*.2)
        if style==5:return (radius*math.cos(theta),radius*math.sin(theta),index*spacing)
        if style==6:return (index*spacing,math.sin(index*.5)*radius,5+t*radius)
        if style==7:return (index*spacing,math.sin(index*.6)*spacing,2+t*radius)
        if style==8:return (radius*math.sin(theta),radius*math.cos(theta),2)
        return (radius*math.cos(theta),radius*math.sin(theta),1+math.sin(theta)*2)
    if style==0:return (rng.uniform(-radius,radius),rng.uniform(-radius,radius),0)
    if style==1:return (radius*math.cos(theta),radius*math.sin(theta),3)
    if style==2:return (radius*math.cos(theta),radius*math.sin(theta),0)
    if style==3:return (index*spacing,math.sin(index)*spacing,0)
    if style==4:return (radius*math.sin(theta),radius*math.cos(theta),0)
    if style==5:return ((index%5)*spacing,(index//5)*spacing,0)
    if style==6:return (rng.uniform(-radius,radius),rng.uniform(-radius,radius),0)
    if style==7:return (index*spacing,(index%2)*spacing,-index*.3)
    if style==8:return (radius*math.cos(theta),radius*math.sin(theta),-radius*.1)
    return (radius*math.cos(theta),radius*math.sin(theta),0)


def edit_encounter(project: StudioProject, action: str, args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in ENCOUNTER_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unknown authored playable encounter recipe")
    ident=_name(args,"prefab_id")
    if ident not in {p.prefab_id for p in project.prefabs}:
        raise StudioError("encounter needs an actual authored character/creature prefab")
    count=_integer(args,"count",1,128)
    if len(project.placements)+count>100000:
        raise StudioError("original-game placed actor capacity exceeded")
    x=_real(args,"x",-1e6,1e6,0)
    y=_real(args,"y",-1e6,1e6,0)
    z=_real(args,"z",-1e6,1e6,0)
    radius=_real(args,"radius",.1,10000,9)
    spacing=_real(args,"spacing",.1,1000,2)
    angle=math.radians(_real(args,"angle_deg",-360,360,0))
    seed=_integer(args,"seed",0,2**63-1)
    rng=random.Random(seed)
    i=ENCOUNTER_ACTIONS.index(action)
    created=[]
    dialogues=[]
    prefix=_name(args,"event_prefix")
    spoken=args.get("dialogue",action.replace("encounter_","").replace("_"," ").capitalize())
    if type(spoken) is not str or not 1<=len(spoken)<=128:
        raise StudioError("encounter source needs bounded authored dialogue")
    assigned={e.event_id for e in project.events}
    for j in range(count):
        dx,dy,dz=_place(i,j,count,radius,angle,spacing,rng)
        facing=(math.degrees(math.atan2(-dy,-dx))%360 if abs(dx)+abs(dy)>1e-9 else 0)
        created.append(StudioPlacement(ident,x+dx,y+dy,z+dz,facing))
        event_id=f"{prefix}_{len(project.placements)+j:05d}"
        if event_id in assigned or len(event_id)>128:
            raise StudioError("encounter actor event ID collision")
        dialogues.append(StudioEvent(
            event_id,"interact","",True,"show_dialogue",
            f"{ident}:{len(project.placements)+j}",spoken))
    if len(project.events)+count>8192:
        raise StudioError("encounter would exceed playable event catalog budget")
    return replace(project,placements=project.placements+tuple(created),
                   events=project.events+tuple(dialogues))
