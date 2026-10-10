"""Deterministic original multimodal free-roam game world: *real* route edges.

A reusable playable route scenario rather than copied copyrighted maps.
Taxi/public transit, ferry/sail/current, plane/glider/wind/rain, hazard,
secret clue deadend, locked passage, mystical portal, interplanetary shuttle
and time scheduled trains all have actual traversal conditions.

Mode families are abstractions. This proves game graph transitions, not real
aviation/ocean/weather physics or manufacturer-certified vehicle simulators.
"""
from __future__ import annotations
from dataclasses import asdict,replace
from hashlib import sha256
import json

from .dragon_route_world import (
    Place,Traverse,World,Traveller,plan,portfolio,validate_world,
    SCHEMA,MAX_EDGES,
)
from .dragon_route_taxonomy import MODES

SOURCE="skeleton.ai.dragon.original_route_frontier.v1"

def make_frontier(*,seed:int=1,weather:str="clear",
                  hour:int=8)->tuple[World,Traveller]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("route world seed must be a genuine unsigned integer")
    if weather not in ("clear","rain","windy","storm","snow","high_tide"):
        raise ValueError("world weather must be one of the implemented routing scenarios")
    if type(hour) is not int or not 0<=hour<24:
        raise ValueError("world start time outside day")
    places=[]
    edges=[]
    def place(name,*,region="lowlands",biome="temperate",
              gifts=(),refill=0,cash=0,scenery=0,tags=()):
        places.append(Place(name,region,biome,tuple(gifts),
                            refill,cash,scenery,tuple(tags)))
    def connect(name,a,b,mode,minutes,*,price=0,fatigue=0,danger=0,
                spectacle=0,shapes=(),requires=(),one=(),gifts=(),
                uses=(),weather_any=(),weather_none=(),departures=(),
                discover="",resistance=""):
        if mode not in MODES:raise ValueError("missing original route taxonomy mode")
        edges.append(Traverse(
            name,a,b,mode,tuple(shapes),minutes,price,fatigue,danger,spectacle,
            tuple(requires),tuple(one),tuple(gifts),tuple(uses),
            tuple(weather_any),tuple(weather_none),tuple(departures),
            discover,resistance,
        ))

    # Original locations are abstract generator names, never an extracted
    # real/copyrighted game map. Visiting a site grants a token only once.
    place("crossroads",gifts=("map",),scenery=2)
    place("bazaar",gifts=("fare_card","raincoat"),scenery=12)
    place("citadel",region="highlands",biome="stone",scenery=15,
          tags=("objective",))
    place("forest",biome="woodland",gifts=("hiking_kit","climbing_kit"),scenery=32)
    place("meadow",biome="grassland",refill=10,scenery=50)
    place("river",biome="riparian",scenery=34)
    place("cliff",biome="mountain",gifts=("climbing_kit",),scenery=72)
    place("wind_peak",biome="mountain",gifts=("glider_licence",),scenery=90)
    place("rain_delta",biome="wetlands",scenery=40)
    place("old_mine",biome="cave",gifts=("forgotten_cipher",),scenery=12,
          tags=("clue_dead_end",))
    place("ruined_archive",biome="ruins",gifts=("rune","archive_map",),scenery=70)
    place("hidden_grotto",biome="cave",gifts=("hidden_key",),scenery=85,
          tags=("secret",))
    place("secret_tunnel",biome="cave",scenery=6,tags=("secret",))
    place("sealed_vault",biome="ruins",gifts=("teleporter_key",),scenery=78,
          tags=("unlockable",))
    place("taxi_rank",scenery=3)
    place("bus_terminal",scenery=5)
    place("rail_station",scenery=10)
    place("tram_stop",scenery=4)
    place("harbor",biome="coastal",gifts=("boat_pass",),scenery=30)
    place("reef",biome="marine",gifts=("diving_kit",),scenery=78)
    place("open_sea",biome="marine",scenery=95)
    place("submerged_gate",biome="underwater",scenery=95,tags=("hidden",))
    place("airport",biome="airfield",gifts=("boarding_pass",),scenery=10)
    place("sky_lane",biome="sky",scenery=99)
    place("cable_station",biome="mountain",scenery=50)
    place("magic_circle",biome="mystic",gifts=("astral_attunement",),scenery=95)
    place("dream_plane",region="astral",biome="ethereal",scenery=100)
    place("spaceport",biome="industrial",gifts=("launch_pass","space_suit",),
          scenery=18)
    place("orbit",region="space",biome="vacuum",scenery=100)
    place("moon_outpost",region="space",biome="lunar",gifts=("stargate_key",),
          scenery=95)
    place("asteroid",region="space",biome="vacuum",scenery=100)
    place("orbital_gate",region="space",biome="vacuum",scenery=100)
    place("ruins_approach",biome="desert",scenery=55)
    place("underground_metro",biome="industrial",scenery=4)
    place("service_hub",biome="industrial",gifts=("service_badge",),scenery=1)
    place("labyrinth",biome="cave",scenery=58)
    place("observation_deck",biome="mountain",refill=10,scenery=97)
    place("fog_bank",biome="coastal",scenery=45)

    # Everyday choices and public transport with physical fares, time and
    # timetables, rather than city names painted onto one generic edge.
    connect("walk_to_bazaar","crossroads","bazaar","walk",12,shapes=("critical",))
    connect("walk_to_goal","bazaar","citadel","walk",45,fatigue=18,
            shapes=("critical",))
    connect("pedestrian_shortcut","crossroads","citadel","parkour",16,
            fatigue=32,danger=20,shapes=("shortcut","challenge"),
            requires=("climbing_kit",))
    connect("market_to_taxi","bazaar","taxi_rank","walk",3)
    connect("taxi_to_goal","taxi_rank","citadel","taxi",14,price=45,
            shapes=("alternate",))
    connect("market_to_bus","bazaar","bus_terminal","walk",4)
    connect("bus_to_goal","bus_terminal","citadel","bus",37,price=6,
            departures=(0,240,480,720,960,1200),shapes=("alternate","time_gated"))
    connect("market_to_train","bazaar","rail_station","walk",8)
    connect("train_to_goal","rail_station","citadel","high_speed_rail",18,
            price=25,requires=("fare_card",),departures=(540,720,1080),
            shapes=("shortcut","time_gated"))
    connect("market_to_tram","bazaar","tram_stop","walk",6)
    connect("tram_to_goal","tram_stop","citadel","tram",30,price=4,
            departures=(60,180,300,420,540,660,780,900,1020,1140,1260,1380))
    connect("market_to_metro","bazaar","underground_metro","escalator",4)
    connect("metro_express","underground_metro","citadel","metro",20,price=3,
            requires=("fare_card",),shapes=("shortcut",))
    connect("market_to_service","bazaar","service_hub","maintenance_shaft",22,
            shapes=("dead_end","detour"))
    connect("service_return","service_hub","bazaar","walk",12)
    connect("service_to_goal","service_hub","citadel","service_transport",8,
            requires=("service_badge",),price=8,shapes=("unlockable","shortcut"))

    # Open-world exploration, side paths, dead ends, clue pickup, loop,
    # maze, long scenic inefficient options; optional but traversable.
    connect("forest_entry","crossroads","forest","trail",27,
            fatigue=12,spectacle=50,shapes=("free_roam","scenic"))
    connect("forest_to_meadow","forest","meadow","trail",34,fatigue=12,
            spectacle=65,shapes=("detour","scenic"))
    connect("meadow_to_river","meadow","river","trail",22,fatigue=7,
            spectacle=70,shapes=("loop","free_roam"))
    connect("river_to_forest","river","forest","trail",30,fatigue=10,
            spectacle=38,shapes=("loop",))
    connect("meadow_to_goal","meadow","citadel","trail",
            66,fatigue=30,spectacle=70,shapes=("impractical","scenic"))
    connect("river_to_goal","river","citadel","kayak",59,fatigue=15,
            spectacle=66,shapes=("alternate","scenic"),
            requires=("hiking_kit",))
    connect("desert_ruins_access","bazaar","ruins_approach","dune",55,
            fatigue=22,danger=8,spectacle=62,
            shapes=("detour","scenic","impractical"))
    connect("desert_to_ruins","ruins_approach","ruined_archive","desert",30,
            fatigue=16,danger=12,spectacle=60,
            shapes=("alternate","free_roam"))
    connect("forest_to_ruins","forest","ruined_archive","trail",42,
            fatigue=15,spectacle=65,shapes=("detour","optional"))
    connect("ruins_return","ruined_archive","crossroads","tunnel",29,
            fatigue=6,shapes=("return_only",))
    connect("mine_sidepath","crossroads","old_mine","cave",75,
            fatigue=15,danger=17,shapes=("dead_end","impractical"))
    connect("mine_return","old_mine","crossroads","tunnel",64,
            fatigue=13,shapes=("return_only",))
    connect("secret_from_clue","crossroads","hidden_grotto","hidden_passage",15,
            discover="forgotten_cipher",requires=("rune",),
            shapes=("secret","unlockable","secret_unlockable","hidden"))
    connect("grotto_to_tunnel","hidden_grotto","secret_tunnel","tunnel",11,
            requires=("hidden_key",),shapes=("unlockable","secret"),
            discover="forgotten_cipher")
    connect("tunnel_to_citadel","secret_tunnel","citadel","hidden_passage",8,
            shapes=("shortcut","secret"),discover="forgotten_cipher")
    connect("vault_open","ruined_archive","sealed_vault","tunnel",15,
            requires=("forgotten_cipher",),shapes=("unlockable","dead_end"))
    connect("vault_back","sealed_vault","ruined_archive","walk",20,
            shapes=("return_only",))
    connect("maze_entry","ruined_archive","labyrinth","maze",48,fatigue=12,
            danger=12,shapes=("detour","impractical"))
    connect("maze_exit","labyrinth","citadel","burrow",58,fatigue=23,
            shapes=("alternate","challenge"))

    # Mountains and weather-specific routes: no fabricated access when dry.
    connect("cliff_access","forest","cliff","climb",40,fatigue=26,
            requires=("climbing_kit",),danger=16,shapes=("challenge",))
    connect("cliff_rappel_return","cliff","forest","rappel",14,
            fatigue=11,requires=("climbing_kit",),shapes=("return_only","recovery"))
    connect("cliff_to_peak","cliff","wind_peak","rope",32,fatigue=22,
            danger=20,shapes=("detour",))
    connect("cable_down","wind_peak","cable_station","cable_car",15,
            price=5,shapes=("recovery","return_only"))
    connect("cable_backtrack","cable_station","crossroads","trail",18,
            fatigue=5,shapes=("recovery","return_only"))
    connect("peak_view","wind_peak","observation_deck","walk",10,
            spectacle=85,shapes=("scenic","optional"))
    connect("deck_back","observation_deck","wind_peak","trail",11)
    connect("cable_approach","crossroads","cable_station","walk",13)
    connect("cable_up","cable_station","wind_peak","cable_car",18,price=14,
            shapes=("alternate",))
    connect("wind_shortcut","wind_peak","citadel","glider",12,
            fatigue=5,danger=21,requires=("glider_licence",),
            weather_any=("windy","storm"),shapes=("shortcut","weather_gated"))
    connect("updraft_travel","wind_peak","citadel","updraft",9,
            fatigue=7,danger=28,weather_any=("windy",),
            requires=("glider_licence",),shapes=("weather_gated","challenge"))
    connect("market_to_rain","bazaar","rain_delta","trail",34,
            fatigue=17,spectacle=25,shapes=("detour",))
    connect("rain_flood_route","rain_delta","citadel","rain_route",13,
            fatigue=12,danger=25,weather_any=("rain","storm"),
            resistance="raincoat",shapes=("shortcut","weather_gated"))
    connect("dry_delta_detour","rain_delta","citadel","swamp",70,
            fatigue=31,weather_none=("rain","storm"),
            shapes=("impractical","weather_gated"))
    connect("snowfield_access","cliff","citadel","snowfield",47,
            fatigue=30,danger=35,weather_any=("snow",),
            shapes=("weather_gated","challenge"))
    connect("fog_sidepath","crossroads","fog_bank","fog_route",40,
            danger=25,weather_any=("rain","storm"),shapes=("weather_gated",))
    connect("fog_to_goal","fog_bank","citadel","raft",35,fatigue=12,
            shapes=("alternate",))

    # Multiple real nautical, river, underwater and tide-gated routes.
    connect("harbor_path","bazaar","harbor","walk",22,shapes=("alternate",))
    connect("ferry_to_goal","harbor","citadel","ferry",68,price=15,
            departures=(120,480,780,1140),shapes=("time_gated","scenic"))
    connect("harbor_to_reef","harbor","reef","sailboat",93,price=13,
            requires=("boat_pass",),spectacle=75,shapes=("detour","scenic"))
    connect("reef_to_goal","reef","citadel","kayak",80,fatigue=15,
            shapes=("impractical",))
    connect("reef_to_ocean","reef","open_sea","cargo_ship",180,price=30,
            shapes=("impractical","detour"))
    connect("ocean_to_goal","open_sea","citadel","motorboat",110,price=24,
            shapes=("impractical","scenic"))
    connect("reef_to_gate","reef","submerged_gate","dive",34,
            fatigue=26,requires=("diving_kit",),
            shapes=("hidden","unlockable"),discover="diving_kit")
    connect("gate_to_goal","submerged_gate","citadel","underwater_cave",19,
            fatigue=16,requires=("diving_kit",),
            shapes=("secret","shortcut"),discover="diving_kit")
    connect("tidal_shortcut","harbor","citadel","tidal_passage",11,
            weather_any=("high_tide",),shapes=("weather_gated","shortcut"))

    # Air, rare alternate shortcuts and actual ticket/boarding rules.
    connect("airport_path","bazaar","airport","taxi",18,price=12)
    connect("airplane_depart","airport","sky_lane","passenger_jet",64,
            price=74,requires=("boarding_pass",),
            departures=(180,480,900,1230),
            shapes=("time_gated","alternate"))
    connect("airplane_arrive","sky_lane","citadel","paraglider",15,
            fatigue=8,danger=15,shapes=("scenic","alternate"))
    connect("airship_route","airport","citadel","airship",105,price=30,
            requires=("boarding_pass",),shapes=("scenic","impractical"))

    # Fantasy + magic are *gated real world graph actions*, not free travel
    # from anywhere. Remote destination needs both discovery and unlock.
    connect("magic_circle_entry","ruined_archive","magic_circle","rune_path",26,
            requires=("rune",),shapes=("unlockable","scenic"))
    connect("astral_hop","magic_circle","dream_plane","astral_projection",73,
            requires=("astral_attunement",),shapes=("impractical","world_transition"))
    connect("dream_exit","dream_plane","citadel","dream_path",41,
            shapes=("alternate","world_transition"))
    connect("vault_teleport","sealed_vault","citadel","teleporter",2,
            requires=("teleporter_key",),shapes=("shortcut","unlockable","secret"),
            discover="forgotten_cipher")
    connect("magic_gateway","magic_circle","citadel","magic_gate",4,
            requires=("rune","astral_attunement"),
            shapes=("shortcut","unlockable"))

    # Space travel with access prerequisites and genuinely long paths.
    connect("spaceport_access","crossroads","spaceport","train",60,price=20,
            departures=(0,480,960),shapes=("time_gated","alternate"))
    connect("shuttle_to_orbit","spaceport","orbit","orbital_shuttle",160,
            price=90,requires=("launch_pass","space_suit"),
            departures=(120,600,1080),shapes=("impractical","world_transition"))
    connect("orbit_to_moon","orbit","moon_outpost","orbital_transfer",140,
            price=40,requires=("space_suit",),shapes=("impractical","detour"))
    connect("moon_to_gate","moon_outpost","orbital_gate","space_taxi",90,
            price=20,requires=("space_suit",),shapes=("detour","alternate"))
    connect("stargate_to_goal","orbital_gate","citadel","stargate",3,
            requires=("stargate_key",),shapes=("shortcut","unlockable",
                                               "world_transition"))
    connect("asteroid_visit","orbit","asteroid","eva",60,fatigue=12,
            requires=("space_suit",),shapes=("scenic","dead_end"))
    connect("asteroid_return","asteroid","orbit","orbital_transfer",65,
            requires=("space_suit",),shapes=("return_only",))
    connect("moon_to_citadel","moon_outpost","citadel","wormhole",19,
            requires=("stargate_key",),shapes=("shortcut","world_transition"))

    # Synthetic seed changes costs on *some* genuinely traversable edges.
    # This is original variation, not a copied map reordering.
    delta=seed%7
    edges=[
        replace(edge,minutes=edge.minutes+(
            delta if edge.id in ("forest_to_meadow","ferry_to_goal",
                                 "airship_route","ocean_to_goal") else 0))
        for edge in edges
    ]
    world=World(tuple(places),tuple(edges),"crossroads","citadel",
                (weather,),True,"generated_original",MAX_MINUTES)
    from .dragon_route_world_variants import mutate_original_world
    world=mutate_original_world(world,seed=seed)
    validate_world(world)
    return world,Traveller(cash=240,energy=100,max_energy=100,
                           start_minute=hour*60)

def structural_report(world:World)->dict:
    validate_world(world)
    outgoing={node.id:[] for node in world.places}
    incoming={node.id:[] for node in world.places}
    for edge in world.connections:
        outgoing[edge.origin].append(edge)
        incoming[edge.destination].append(edge)
    # A dead end has no outgoing route except a reverse of its incoming edge;
    # pointlessly labeled deadends are not treated as proved structure.
    dead_ends=[]
    for node in world.places:
        if node.id in (world.start,world.goal):continue
        neighbors={edge.origin for edge in incoming[node.id]}
        forward={edge.destination for edge in outgoing[node.id]}
        if forward and forward<=neighbors:dead_ends.append(node.id)
    # Directed cycles are proven by a reachability test, not tags.
    adjacency={k:{edge.destination for edge in v} for k,v in outgoing.items()}
    def reachable(start,goal):
        pending=[start];seen=set()
        while pending:
            current=pending.pop()
            if current==goal:return True
            if current in seen:continue
            seen.add(current);pending.extend(adjacency[current]-seen)
        return False
    cycle_edges=sum(reachable(x.destination,x.origin)
                    for x in world.connections)
    shortest,states,truncated=plan(world,Traveller(),
                                   objective="fastest",expansion_cap=8000)
    return {
        "schema":SOURCE,
        "places":len(world.places),"routes":len(world.connections),
        "modes":sorted({x.mode for x in world.connections}),
        "families":sorted({MODES[x.mode] for x in world.connections}),
        "dead_end_places":sorted(dead_ends),
        "real_cycle_edges":cycle_edges,
        "secret_routes":sum(bool(x.secret_token) for x in world.connections),
        "locked_routes":sum(bool(x.requires) for x in world.connections),
        "timed_routes":sum(bool(x.departures) for x in world.connections),
        "weather_routes":sum(bool(x.weather_any or x.weather_none)
                             for x in world.connections),
        "actual_fastest_found":shortest is not None,
        "analysis_states":states,
        "analysis_truncated":truncated,
        "claim":"actual original state graph; specialized water/air/magic/space physics not provided",
    }

def scenario_digest(world:World)->str:
    validate_world(world)
    payload=json.dumps(asdict(world),sort_keys=True,separators=(",",":"))
    return sha256(payload.encode("utf-8")).hexdigest()
