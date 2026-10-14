"""Procedural *original* route-world recombination without borrowed level data.

Seeds alter many measurable traversal costs, risks and optional edges.
No game title, commercial map geometry, proprietary station names or
copyrighted level layout appears here. Each candidate is validated against
the same bounded executable world state model before any source export.

Uniqueness is a hash/content property, NOT a claim to have generated,
played, shipped or independently cleared millions of finished games.
"""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256

from .dragon_route_world import World,Traverse,validate_world

OPTIONS=(
    # A deterministic atlas of original optional encounters: real transfers,
    # not names pasted onto the same abstract path.
    ("guild_bike_path","bazaar","cliff","bicycle",31,8,7,3,22,
     ("alternate","scenic"),(),()),
    ("woodland_to_dock","forest","harbor","raft",41,0,13,9,39,
     ("detour","free_roam"),(),()),
    ("coastal_air_link","harbor","airport","water_taxi",29,19,3,4,45,
     ("alternate","scenic"),(),()),
    ("cliff_to_archives","cliff","ruined_archive","zipline",18,0,13,17,55,
     ("shortcut","challenge"),("climbing_kit",),()),
    ("open_woodland_loop","meadow","crossroads","trail",24,0,6,0,29,
     ("loop","free_roam"),(),()),
    ("temple_spacelane","ruined_archive","spaceport","magic_gate",43,0,8,14,65,
     ("world_transition","unlockable"),("rune",),()),
    ("sky_ruins_crossing","ruined_archive","sky_lane","flying_mount",65,0,8,25,80,
     ("challenge","alternate"),("rune","archive_map"),()),
    ("estuary_ferry","rain_delta","harbor","water_taxi",28,9,4,4,25,
     ("scenic","alternate"),(),("rain","high_tide")),
    ("deep_cavern_join","labyrinth","old_mine","tunnel",39,0,11,10,19,
     ("detour","free_roam"),(),()),
    ("moon_dream_shortcut","moon_outpost","dream_plane","wormhole",68,15,4,30,99,
     ("secret","world_transition"),("stellar_gate_key",),()),
    ("reef_sky_current","reef","sky_lane","updraft",58,0,10,27,72,
     ("weather_gated","challenge"),("diving_kit",),("windy",)),
    ("metro_market_return","underground_metro","bazaar","metro",8,3,0,0,5,
     ("return_only","loop"),("fare_card",),()),
)

def _hash(seed:int,name:str)->bytes:
    return sha256(f"original_route_world_v1:{seed}:{name}".encode("ascii")).digest()

def mutate_original_world(world:World,*,seed:int)->World:
    validate_world(world)
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("native original world variant seed must be uint32")
    # Core authored routes from the demo remain reachable; optional branch
    # details vary deterministically without multiplying a copied level map.
    unchanged={
        "walk_to_bazaar","market_to_taxi","taxi_to_goal",
        "market_to_bus","bus_to_goal","market_to_train","train_to_goal",
        "airport_path","airplane_depart","airplane_arrive",
        "spaceport_access","shuttle_to_orbit","orbit_to_moon","moon_to_citadel",
        "forest_entry","forest_to_ruins","ruins_return",
        "mine_sidepath","mine_return","secret_from_clue",
        "grotto_to_tunnel","tunnel_to_citadel",
        "harbor_path","harbor_to_reef","reef_to_ocean","ocean_to_goal",
        "forest_to_meadow","meadow_to_river","river_to_forest","meadow_to_goal",
        "magic_circle_entry","magic_gateway",
    }
    edges=[]
    for edge in world.connections:
        if edge.id in unchanged:
            edges.append(edge)
            continue
        digest=_hash(seed,edge.id)
        # All positive numbers stay within the original graph schema caps.
        edges.append(replace(
            edge,
            # Real multi-year generation-ship legs must survive seeded
            # recombination. Only ordinary short hops get local jitter;
            # reducing a decades-long journey to one day falsifies the game
            # clock and contradicts the bounded source witness.
            minutes=(edge.minutes if edge.minutes>1440 else
                     max(1,min(1440,edge.minutes+digest[0]%19-9))),
            danger=min(100,max(0,edge.danger+digest[1]%9-4)),
            spectacle=min(100,max(0,edge.spectacle+digest[2]%13-6)),
        ))
    sites={node.id for node in world.places}
    # Derived worlds may already carry optional routes. Recombination must
    # preserve unique graph edge identity instead of appending a second copy
    # of the same source-authored option under a new procedural seed.
    used={edge.id for edge in edges}
    for option in OPTIONS:
        name,a,b,mode,minutes,price,fatigue,danger,scenery,shapes,keys,weather=option
        if name in used or a not in sites or b not in sites:continue
        digest=_hash(seed,name)
        if digest[0]%4==0:continue
        secret=name=="moon_dream_shortcut"
        edges.append(Traverse(
            id=name,origin=a,destination=b,mode=mode,
            shapes=tuple(shapes),
            minutes=max(1,minutes+digest[1]%13-6),
            price=price,fatigue=fatigue,danger=danger,
            spectacle=scenery,requires=tuple(keys),
            weather_any=tuple(weather),
            secret_token="stellar_gate_key" if secret else "",
            mana=25 if mode=="wormhole" else 15 if mode=="magic_gate" else 0,
        ))
    changed=replace(world,connections=tuple(edges))
    validate_world(changed)
    return changed

def original_variant_receipt(world:World,*,seed:int)->dict:
    from .dragon_route_world_factory import scenario_digest,structural_report
    derived=mutate_original_world(world,seed=seed)
    before={edge.id for edge in world.connections}
    newly=[edge.id for edge in derived.connections if edge.id not in before]
    return {
        "schema":"skeleton.ai.dragon.original_world_variants.v1",
        "seed":seed,
        "source_world_sha256":scenario_digest(world),
        "derived_world_sha256":scenario_digest(derived),
        "original_optional_routes":newly,
        "network":structural_report(derived),
        "rights":"fresh abstract route grammar; independent clearance not asserted",
        "limits":"distinct world variants are not equivalent to completed game titles",
    }
