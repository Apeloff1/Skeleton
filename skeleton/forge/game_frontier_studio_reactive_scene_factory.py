"""Fifty executable original-game multi-sensor RPG encounter composers.

Each command authors a two-signal, validated RPGEventPage with an actual
typed in-game action (weather, camera, music, quest, gameplay, ecology).
Existing deterministic sensor evaluator and Godot page compiler consume it.
No observation or platform event is fabricated by the editor.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Any, Mapping

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_map_edit import _name, _integer
from .game_frontier_rpg_events import (
    RPGEventPage, RPGEventAction, EnvironmentalTrigger,
    RPG_ENVIRONMENT_SIGNALS, ACTIONS, EVENT_CHANNELS, COMPARISONS,
)

REACTIVE_SCENES=(
    ["reaction_storm_warning","wind_mps","above",18,"rain_mm_h","above",4,"show_dialogue","ui","weather_warning","Seek shelter"],
    ["reaction_rain_audio","rain_mm_h","above",2,"humidity","above",0.6,"spatial_audio","audio","rain_ambience","wet"],
    ["reaction_fog_camera","fog_visibility_m","below",120,"humidity","above",0.7,"change_camera","cinematic","camera","fog"],
    ["reaction_gale_sails","wind_mps","above",16,"updraft_mps","above",1,"apply_gameplay_effect","character","sailor","wind_push"],
    ["reaction_wet_roads","soil_wetness","above",0.6,"rain_mm_h","above",1,"set_flag","world","slippery_roads","true"],
    ["reaction_river_flood","water_depth_m","above",2,"tide_height_m","above",1,"change_tide","environment","river","flood"],
    ["reaction_ground_freeze","ground_ice_fraction","above",0.5,"temperature_c","below",0,"apply_gameplay_effect","character","traveler","ice_slip"],
    ["reaction_turbulence_fx","turbulence_mps","above",10,"wind_mps","above",5,"trigger_foliage_fx","environment","trees","shake"],
    ["reaction_hail_shelter","temperature_c","below",2,"rain_mm_h","above",4,"show_dialogue","ui","storm_alert","Cold rain ahead"],
    ["reaction_humidity_fog","humidity","above",0.85,"fog_visibility_m","below",300,"change_camera","cinematic","camera","haze"],
    ["reaction_terminal_fall","fall_speed_mps","above",38,"native_vertical_speed_mps","below",-24,"take_damage","character","traveler","heavy_fall"],
    ["reaction_rough_landing","impact_impulse_ns","above",350,"native_contact_count","above",0,"trigger_impact_fx","environment","ground","dust"],
    ["reaction_kinetic_impact","collision_energy_j","above",300,"native_kinetic_energy_j","above",50,"take_damage","character","traveler","impact"],
    ["reaction_skin_tension","skin_strain","above",0.7,"impact_impulse_ns","above",100,"set_flag","world","skin_overload","true"],
    ["reaction_low_stability","support_margin_m","below",0.1,"center_of_mass_offset_m","above",0.25,"apply_gameplay_effect","character","traveler","stumble"],
    ["reaction_cliff_climb","climb_angle_deg","above",60,"traction_slip_risk","above",0.5,"set_flag","world","unsafe_climb","true"],
    ["reaction_weight_shift","character_mass_kg","above",120,"support_margin_m","below",0.2,"apply_gameplay_effect","character","traveler","heavy_load"],
    ["reaction_slick_fabric","garment_wetness","above",0.8,"temperature_c","below",5,"set_npc_emotion","character","party","cold"],
    ["reaction_updraft_lift","updraft_mps","above",6,"native_vertical_speed_mps","above",2,"apply_gameplay_effect","character","traveler","lift"],
    ["reaction_native_field","native_gameplay_field_force_n","above",100,"native_actor_speed_mps","above",3,"trigger_impact_fx","environment","field","force"],
    ["reaction_altitude_chart","barometric_altitude_m","above",1200,"pressure_pa","below",90000,"inspect_instrument","ui","altimeter","high"],
    ["reaction_sextant_sighting","sextant_altitude_deg","above",35,"solar_height","above",10,"inspect_instrument","ui","sextant","fix"],
    ["reaction_bubble_sextant","bubble_sextant_altitude_deg","above",25,"gyro_tilt_deg","below",5,"inspect_instrument","ui","bubble_sextant","fix"],
    ["reaction_compass_turn","compass_heading_deg","above",270,"wind_mps","above",3,"change_camera","cinematic","camera","westward"],
    ["reaction_triangulation","trigonometric_altitude_m","above",500,"barometric_altitude_m","above",400,"set_flag","navigation","survey_complete","true"],
    ["reaction_skyisland_arrival","sky_island_height_m","above",350,"native_actor_speed_mps","below",6,"start_quest","quest","sky_realm","landed"],
    ["reaction_gyro_drift","gyro_tilt_deg","above",15,"turbulence_mps","above",4,"inspect_instrument","ui","gyro","recalibrate"],
    ["reaction_pressure_front","pressure_pa","below",95000,"wind_mps","above",10,"show_dialogue","ui","forecast","Low pressure"],
    ["reaction_navigation_current","tide_height_m","above",2,"wind_mps","above",8,"set_flag","navigation","current_risk","true"],
    ["reaction_night_navigation","daylight","below",0.2,"moon_phase","above",0.3,"inspect_instrument","ui","star_chart","night"],
    ["reaction_party_low_morale","party_morale","below",0.25,"quest_progress","below",0.6,"set_npc_emotion","character","party","anxious"],
    ["reaction_heroic_reputation","npc_reputation","above",75,"quest_progress","above",0.8,"set_faction_reputation","character","allies","trusted"],
    ["reaction_quest_music","quest_progress","above",0.6,"music_intensity","below",0.4,"play_music","audio","theme","hope"],
    ["reaction_village_emotion","npc_reputation","below",-25,"party_morale","below",0.5,"set_npc_emotion","character","villagers","worried"],
    ["reaction_party_morale_boost","party_morale","above",0.8,"npc_reputation","above",15,"play_music","audio","theme","triumph"],
    ["reaction_combat_music","music_intensity","above",0.75,"native_contact_count","above",1,"play_music","audio","combat","high"],
    ["reaction_stealth_audio","sound_occlusion","above",0.7,"daylight","below",0.3,"spatial_audio","audio","footsteps","muffled"],
    ["reaction_world_axis","quest_progress","above",0.95,"npc_reputation","above",60,"set_world_axis","world","alignment","allied"],
    ["reaction_quest_unlock","quest_progress","above",0.95,"party_morale","above",0.5,"unlock_skill","character","traveler","veteran"],
    ["reaction_morale_camp","party_morale","below",0.35,"temperature_c","below",2,"save_bookmark","ui","camp","shelter"],
    ["reaction_moon_tide","moon_phase","above",0.8,"tide_height_m","above",2,"change_tide","environment","harbor","spring_tide"],
    ["reaction_sunrise_cinematic","solar_height","above",1,"daylight","above",0.4,"play_cutscene","cinematic","sunrise","dawn"],
    ["reaction_eclipse_shadows","shadow_fraction","above",0.8,"daylight","below",0.4,"change_light","environment","sun","dim"],
    ["reaction_foliage_shadow","leaf_shadow_area_m2","above",20,"wind_mps","above",5,"trigger_foliage_fx","environment","trees","flutter"],
    ["reaction_terrain_erosion","erosion","above",0.7,"rain_mm_h","above",10,"deform_terrain","environment","hillside","washout"],
    ["reaction_falling_building","building_integrity","below",0.3,"wind_mps","above",12,"trigger_impact_fx","environment","building","collapse"],
    ["reaction_cloud_portal","sky_island_height_m","above",600,"fog_visibility_m","below",100,"world_portal","navigation","portal","cloudgate"],
    ["reaction_tidal_reef","tide_height_m","below",0.2,"water_depth_m","below",1,"set_flag","world","reef_exposed","true"],
    ["reaction_deep_night","daylight","below",0.1,"solar_height","below",-5,"change_light","environment","night","dark"],
    ["reaction_seasonal_bloom","temperature_c","above",16,"humidity","above",0.65,"trigger_foliage_fx","environment","flowers","bloom"],
)
REACTIVE_SCENE_ACTIONS=tuple(row[0] for row in REACTIVE_SCENES)
if len(REACTIVE_SCENE_ACTIONS)!=50 or len(set(REACTIVE_SCENE_ACTIONS))!=50:
    raise RuntimeError("exactly 50 distinct original game reaction scenes required")


def edit_reactive_scene(project: StudioProject, action: str,
                        args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in REACTIVE_SCENE_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unknown playable original-game sensor reaction")
    number=REACTIVE_SCENE_ACTIONS.index(action)
    (ident,sig1,op1,t1,sig2,op2,t2,
     kind,channel,target,value)=REACTIVE_SCENES[number]
    page_id=_name(args,"page_id")
    if page_id in {p.page_id for p in project.environmental_pages} | {e.event_id for e in project.events}:
        raise StudioError("event source identity already exists")
    priority=_integer(args,"priority",-100,100) if "priority" in args else 0
    cooldown=_integer(args,"cooldown_ms",0,86400000) if "cooldown_ms" in args else 0
    required=args.get("required_flags",{})
    if type(required) is not dict or len(required)>32 or any(
            type(k) is not str or not k or len(k)>128 or type(v) is not bool
            for k,v in required.items()):
        raise StudioError("RPG reaction needs a bounded typed source flag map")
    thresholds=args.get("thresholds",[t1,t2])
    if type(thresholds) is not list or len(thresholds)!=2:
        raise StudioError("reaction needs two numeric sensor thresholds")
    comparisons=args.get("comparisons",[op1,op2])
    if type(comparisons) is not list or len(comparisons)!=2 or any(
            type(v) is not str or v not in COMPARISONS for v in comparisons):
        raise StudioError("reaction must use canonical supported comparisons")
    response=args.get("response",{})
    if type(response) is not dict or set(response)-{"kind","channel","target","value"}:
        raise StudioError("invalid RPG response overrides")
    raw={"kind":kind,"channel":channel,"target":target,"value":value}
    raw.update(response)
    action_record=RPGEventAction(**raw)
    conditions=(
        EnvironmentalTrigger(sig1,comparisons[0],thresholds[0]),
        EnvironmentalTrigger(sig2,comparisons[1],thresholds[1]),
    )
    page=RPGEventPage(
        page_id,priority,conditions,(action_record,),
        required_flags=tuple(sorted(required.items())),
        cooldown_ms=cooldown,
        enabled=True,repeat=bool(args.get("repeat",True)),
    )
    return replace(project,environmental_pages=project.environmental_pages+(page,))
