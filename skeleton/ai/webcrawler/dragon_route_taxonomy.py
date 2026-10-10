"""Original game route modality registry, not a catalog of copied games.

Each registry identifier has executable shared traversal semantics (resource,
capability, weather, timetable, hazard, visibility, discovery and gates)
through dragon_route_world. Domain-specific movement physics and audiovisual
implementations are explicitly separate adapters.
"""
from __future__ import annotations
from dataclasses import dataclass

SCHEMA="skeleton.ai.dragon.route_taxonomy.v1"

# Families are intentionally open to original mechanical combinations.
# These are *categories*, not trademarked vehicles, exact titles, assets,
# licensed engines or a claim of dedicated per-mode native animations.
FAMILIES:dict[str,tuple[str,...]]={
 "pedestrian":(
  "walk","run","sprint","sneak","crawl","prone","climb","ladder","rope",
  "rappel","parkour","vault","wall_run","wall_jump","slide","jump","glide",
  "zipline","grapple","elevator","escalator","stairwell","conveyor",
  "trail","cave","burrow","tunnel","labyrinth","maze","maintenance_shaft",
  "roof_route","sewer","subway_tunnel","catwalk","vent","hidden_passage",
 ),
 "wheeled":(
  "bicycle","scooter","motorcycle","car","taxi","rideshare","bus",
  "tram","streetcar","trolleybus","train","metro","high_speed_rail",
  "funicular","cable_car","monorail","maglev","truck","offroad",
  "all_terrain","skateboard","rollerblade","wheelchair","hoverboard",
  "wheelbarrow","sled","snowmobile","tank","armored_convoy",
 ),
 "water":(
  "swim","dive","snorkel","surf","kayak","canoe","rowboat","raft",
  "sailboat","ferry","water_taxi","riverboat","barge","cargo_ship",
  "motorboat","speedboat","hydrofoil","hovercraft","submarine",
  "diving_bell","ocean_current","canal","waterfall","ice_bridge",
  "tidal_passage","underwater_cave","coral_corridor",
 ),
 "air":(
  "glider","hang_glider","paraglider","wingsuit","jetpack","helicopter",
  "seaplane","airplane","passenger_jet","cargo_plane","balloon",
  "airship","drone_cabin","autogyro","wind_tunnel","updraft",
  "thermal_lift","storm_glide","skybridge","flying_mount",
 ),
 "environment":(
  "mud","quicksand","swamp","desert","dune","blizzard","snowfield",
  "glacier","ice_climb","volcanic_slope","lava_bridge","ash_cloud",
  "rain_route","floodplain","storm_route","lightning_field",
  "windward","leeward","sandstorm","fog_route","darkness",
  "low_gravity","zero_gravity","high_gravity","magnetic_field",
  "pressure_cave","acid_rain","radiation_zone","fire_route",
  "jungle","vine_canopy","moving_platform","collapsing_bridge",
 ),
 "creature":(
  "horse","pack_animal","sled_dogs","flying_creature","swimming_mount",
  "giant_insect","mechanical_mount","beast_caravan","migration",
 ),
 "fictional":(
  "portal","teleporter","blink","phase_shift","astral_projection",
  "magic_gate","rune_path","enchanted_road","dream_path",
  "spirit_bridge","summoning_circle","shapeshift","time_rift",
  "time_loop","dimension_hop","parallel_world","shadow_plane",
  "mirror_passage","gravity_spell","elemental_gate","leyline",
  "ritual_bridge","wormhole","quantum_tunnel",
 ),
 "space":(
  "orbital_shuttle","launch_vehicle","space_elevator","spaceplane",
  "orbital_transfer","lunar_rover","planetary_lander","asteroid_hop",
  "eva","airlock","station_corridor","docking_tube","space_taxi",
  "deep_space_cruise","solar_sail","ion_ship","hyperspace",
  "interstellar_ship","stellar_gate","gravity_assist","generation_ship",
  "rescue_pod","colony_transport",
 ),
 "digital":(
  "network_tunnel","cyberspace","hologram_route","simulation_hop",
  "remote_possession","robot_drone","data_stream","virtual_portal",
 ),
 "social":(
  "guided_tour","caravan","escort_convoy","festival_parade",
  "smuggler_passage","service_transport","evacuation_route",
  "merchant_route","diplomatic_corridor","restricted_access",
  "quest_passage","secret_society","paid_shortcut",
 ),
}
MODES={name:family for family,names in FAMILIES.items() for name in names}
if sum(len(x) for x in FAMILIES.values())!=len(MODES):
    raise RuntimeError("ambiguous route modality name in original catalog")

# Functional classification; edge behavior is enforced by world transitions.
ROUTE_SHAPES=(
 "critical","alternate","detour","dead_end","cul_de_sac","loop",
 "circuit","shortcut","hidden","secret","unlockable","secret_unlockable",
 "optional","free_roam","scenic","impractical","time_gated",
 "weather_gated","resource_gated","quest_gated","faction_gated",
 "ability_gated","vehicle_gated","one_way","return_only","emergency",
 "risk_reward","speedrun","stealth","challenge","recovery","multi_stage",
 "world_transition","parallel_dimension","interplanetary",
)
ENVIRONMENT_FLAGS=(
 "dry","rain","storm","windy","blizzard","snow","ice","flood","low_tide",
 "high_tide","fog","night","day","heatwave","cold_snap","sandstorm",
 "updraft","low_gravity","zero_gravity","underwater","vacuum","radiation",
 "magnetic_storm","lava","toxic","darkness","clear",
)

@dataclass(frozen=True)
class RouteModality:
    id:str
    family:str
    movement_model:str
    native_specific_physics:bool
    claim:str

def capabilities()->dict:
    return {
        "schema":SCHEMA,
        "families":{k:list(v) for k,v in FAMILIES.items()},
        "modality_count":len(MODES),
        "shapes":list(ROUTE_SHAPES),
        "environment_flags":list(ENVIRONMENT_FLAGS),
        "world_graph_behavior":"mode-aware generalized traversal with real gates, time, economy and resources",
        "native_physics_claim":"generic traversal only; modality-specific movement and animation need separate adapters",
        "origin":"original abstract routing mechanics; not a copied level, transit map or commercial title",
    }

def modality(name:str)->RouteModality:
    if type(name) is not str or name not in MODES:
        raise ValueError("unknown original game traversal modality")
    family=MODES[name]
    return RouteModality(name,family,"bounded_world_graph_state_transition",False,
        "generic runnable route gating; not physical simulation or commercial asset")
