/** Interactive 500-operation Forge Studio editor over live authenticated project revisions. */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import GameFrontierHandbookPanel from './GameFrontierHandbookPanel';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  buildForge, copyForgeTiles, editForge, exportForge, inspectForge,
  searchForgeRecipes, type ForgeRecipeResults, type ForgeRecipe,
  previewForgeGameplay, type ForgeGameplayProbe,
  type ForgeDocument, type ForgeStep, type ForgeBuild,
} from '../../product/gameFrontierAuthoringClient';
import { getLearningProject, type LearningProject } from '../../product/gameLearningClient';

type Props = {
  project: LearningProject;
  disabled?: boolean;
  onSaved: (project: LearningProject) => void;
  onDirtyChange?: (dirty: boolean) => void;
};

const GROUPS: { title: string; actions: string[] }[] = [
  { title: 'Original world ecology', actions: [
    'terrain_fault_lines', 'terrain_plate_edges', 'terrain_tectonic_ridges', 'terrain_graben_valley', 'terrain_volcano_cone', 'terrain_lava_channels', 'terrain_caldera_ring', 'terrain_mesa_terraces',
    'terrain_karst_sinkholes', 'terrain_mountain_chain', 'terrain_alluvial_fans', 'terrain_delta_branches', 'terrain_oxbow_lakes', 'terrain_braided_streams', 'terrain_watershed_divide', 'terrain_glacial_valley',
    'terrain_moraine_ridges', 'terrain_fjord_channels', 'terrain_reef_atolls', 'terrain_tidal_flats', 'terrain_rainforest', 'terrain_savanna', 'terrain_taiga', 'terrain_tundra',
    'terrain_alpine_meadow', 'terrain_desert_badlands', 'terrain_mangrove', 'terrain_swamp_bog', 'terrain_grass_steppe', 'terrain_volcanic_ash', 'terrain_fungal_caverns', 'terrain_crystal_caves',
    'terrain_stalagmite_fields', 'terrain_limestone_pillars', 'terrain_underground_rivers', 'terrain_lava_tubes', 'terrain_geode_chambers', 'terrain_abyssal_pits', 'terrain_bioluminescent_groves', 'terrain_ruined_catacombs',
    'terrain_floating_islands', 'terrain_cloud_banks', 'terrain_wind_corridors', 'terrain_sky_arches', 'terrain_storm_belts', 'terrain_levitation_nodes', 'terrain_aurora_paths', 'terrain_meteor_craters',
    'terrain_gravity_wells', 'terrain_portal_constellations',
  ] },
  { title: 'Level & settlement architecture', actions: [
    'structure_village_square', 'structure_market_stalls', 'structure_courtyard', 'structure_town_grid', 'structure_radial_city', 'structure_harbor_piers', 'structure_farm_fields', 'structure_orchard_rows',
    'structure_house_cluster', 'structure_canal_district', 'structure_castle_keep', 'structure_outer_wall', 'structure_gatehouse', 'structure_corner_bastions', 'structure_moat_bridge', 'structure_watchtowers',
    'structure_wall_walk', 'structure_arrow_slits', 'structure_turret_ring', 'structure_fortified_crossroads', 'structure_dungeon_rooms', 'structure_dungeon_corridors', 'structure_spiral_vault', 'structure_treasure_chambers',
    'structure_pillar_hall', 'structure_prison_cells', 'structure_cathedral_nave', 'structure_catacomb_grid', 'structure_trap_gauntlet', 'structure_boss_arena', 'structure_factory_floor', 'structure_conveyor_lanes',
    'structure_power_grid', 'structure_storage_racks', 'structure_warehouse_aisles', 'structure_rail_depot', 'structure_shipyard_slips', 'structure_mining_shafts', 'structure_pipeline_array', 'structure_reactor_chamber',
    'structure_suspension_bridge', 'structure_stepping_stones', 'structure_ramp_switchbacks', 'structure_cliff_stairs', 'structure_tunnel_bore', 'structure_treetop_walks', 'structure_sky_platforms', 'structure_rope_bridge',
    'structure_portal_plaza', 'structure_island_airfield',
  ] },
  { title: 'Interactive game encounters', actions: [
    'encounter_village_crowd', 'encounter_market_vendors', 'encounter_tavern_guests', 'encounter_festival_parade', 'encounter_harbor_workers', 'encounter_farm_hands', 'encounter_caravan_merchants', 'encounter_city_patrol',
    'encounter_castle_guards', 'encounter_royal_court', 'encounter_wolf_pack', 'encounter_deer_herd', 'encounter_bird_flock', 'encounter_fish_school', 'encounter_insect_swarm', 'encounter_horse_stampede',
    'encounter_bear_den', 'encounter_predator_ring', 'encounter_migratory_line', 'encounter_turtle_nesting', 'encounter_squad_wedge', 'encounter_siege_lines', 'encounter_archer_wall', 'encounter_shield_circle',
    'encounter_cavalry_charge', 'encounter_ambush_arcs', 'encounter_flanking_pincer', 'encounter_rear_guard', 'encounter_scout_net', 'encounter_boss_minions', 'encounter_sky_pirates', 'encounter_airship_crew',
    'encounter_cloud_drakes', 'encounter_floating_island_settlers', 'encounter_wind_surfers', 'encounter_tower_watchers', 'encounter_balloon_riders', 'encounter_glider_convoy', 'encounter_sky_fishermen', 'encounter_aurora_procession',
    'encounter_dungeon_slimes', 'encounter_cave_bats', 'encounter_crypt_guardians', 'encounter_labyrinth_wardens', 'encounter_treasure_mimics', 'encounter_portal_sentinels', 'encounter_ruin_explorers', 'encounter_mine_workers',
    'encounter_fungal_foragers', 'encounter_underground_merchants',
  ] },
  { title: 'Original quest foundations', actions: [
    'quest_lighthouse_blackout', 'quest_sky_island_rescue', 'quest_stolen_compass', 'quest_moon_tide_survey', 'quest_forest_railway', 'quest_clockwork_herald', 'quest_flooded_archive', 'quest_starlit_observatory',
    'quest_copper_mine_dispute', 'quest_mountain_pass', 'quest_marsh_lanterns', 'quest_garden_of_machines', 'quest_whispering_canyon', 'quest_archipelago_mail', 'quest_ironwood_heirloom', 'quest_saltwind_market',
    'quest_beacon_constellation', 'quest_ruins_of_ash', 'quest_library_of_winds', 'quest_mirror_lake', 'quest_tower_chimes', 'quest_glass_dunes', 'quest_deepwater_engine', 'quest_hidden_canal',
    'quest_ember_festival', 'quest_orchard_winter', 'quest_jade_quarry', 'quest_bridge_of_mist', 'quest_river_sentinel', 'quest_northern_outpost', 'quest_cavern_echos', 'quest_sky_orchards',
    'quest_clocktower_apprentice', 'quest_wildlife_corridor', 'quest_aurora_station', 'quest_drowned_temple', 'quest_coral_foundry', 'quest_lost_weather_balloon', 'quest_underground_orchard', 'quest_firefly_navigation',
    'quest_solar_tide_engine', 'quest_icebound_caravan', 'quest_treetop_council', 'quest_sextant_apprentice', 'quest_broken_portal', 'quest_floating_foundry', 'quest_night_ferry', 'quest_echoes_of_the_city',
    'quest_moonlit_greenhouse', 'quest_last_skybridge',
  ] },
  { title: 'Reactive gameplay scenes', actions: [
    'reaction_storm_warning', 'reaction_rain_audio', 'reaction_fog_camera', 'reaction_gale_sails', 'reaction_wet_roads', 'reaction_river_flood', 'reaction_ground_freeze', 'reaction_turbulence_fx',
    'reaction_hail_shelter', 'reaction_humidity_fog', 'reaction_terminal_fall', 'reaction_rough_landing', 'reaction_kinetic_impact', 'reaction_skin_tension', 'reaction_low_stability', 'reaction_cliff_climb',
    'reaction_weight_shift', 'reaction_slick_fabric', 'reaction_updraft_lift', 'reaction_native_field', 'reaction_altitude_chart', 'reaction_sextant_sighting', 'reaction_bubble_sextant', 'reaction_compass_turn',
    'reaction_triangulation', 'reaction_skyisland_arrival', 'reaction_gyro_drift', 'reaction_pressure_front', 'reaction_navigation_current', 'reaction_night_navigation', 'reaction_party_low_morale', 'reaction_heroic_reputation',
    'reaction_quest_music', 'reaction_village_emotion', 'reaction_party_morale_boost', 'reaction_combat_music', 'reaction_stealth_audio', 'reaction_world_axis', 'reaction_quest_unlock', 'reaction_morale_camp',
    'reaction_moon_tide', 'reaction_sunrise_cinematic', 'reaction_eclipse_shadows', 'reaction_foliage_shadow', 'reaction_terrain_erosion', 'reaction_falling_building', 'reaction_cloud_portal', 'reaction_tidal_reef',
    'reaction_deep_night', 'reaction_seasonal_bloom',
  ] },
  { title: 'Tiles & geometry', actions: ['tile_set','rect_fill','line_draw','ellipse_fill','flood_fill',
    'replace_tile','checker_fill','stamp','region_paste','shift_layer','flip_horizontal','flip_vertical','rotate_90'] },
  { title: 'Layers & palettes', actions: ['layer_add','layer_remove','layer_duplicate','layer_reorder',
    'layer_elevation','palette_add','palette_replace','palette_swap','palette_remove','layer_resize',
    'layer_crop','layer_clear'] },
  { title: 'Prefabs & actors', actions: ['prefab_add','prefab_remove','prefab_clone','prefab_retarget',
    'prefab_interaction','placement_add','placement_remove','placement_move','placement_rotate',
    'placement_duplicate','placement_mirror','placement_grid'] },
  { title: 'Events & quests', actions: ['event_add','event_remove','event_condition','event_action',
    'event_trigger','quest_add','quest_remove','quest_stage_append','quest_objective','quest_title'] },
  { title: 'Soundtracks', actions: ['soundtrack_add','soundtrack_remove','soundtrack_reorder'] },
  { title: 'Environment RPG', actions: [
    'environment_page_add','environment_page_remove','environment_page_clone',
    'environment_page_priority','environment_page_enable','environment_page_repeat',
    'environment_page_cooldown','environment_condition_add','environment_condition_edit',
    'environment_condition_remove','environment_action_add','environment_action_edit',
    'environment_action_remove','environment_flag_require','environment_flag_clear',
  ] },
  { title: 'Native game trigger zones', actions: [
    'zone_add','zone_remove','zone_clone','zone_bind_actor','zone_bind_event',
    'zone_radius','zone_offset','zone_translate','zone_scale','zone_duplicate_to_actor',
  ] },
  { title: 'Active native physics fields', actions: [
    'field_add','field_remove','field_clone','field_bind_actor','field_kind',
    'field_radius','field_strength','field_offset','field_invert','field_duplicate_to_actor',
  ] },
  { title: 'Quest structure', actions: [
    'quest_stage_remove','quest_stage_link','quest_stage_unlink','quest_stage_split',
    'quest_stage_rename','quest_start_change','quest_stage_swap_objectives',
    'quest_duplicate','quest_stage_reorder','quest_rewrite_objectives',
  ] },
  { title: 'Procedural terrain', actions: [
    'terrain_noise','terrain_smooth','terrain_terrace','terrain_outline','terrain_erode',
  ] },
  { title: 'World generators', actions: [
    'terrain_height_noise', 'terrain_fractal', 'terrain_ridge', 'terrain_islands', 'terrain_crater',
    'terrain_meander_river', 'terrain_lake', 'terrain_coastline', 'terrain_talus', 'terrain_dunes',
    'terrain_voronoi', 'terrain_contours', 'terrain_floodplain', 'terrain_cave_automata',
    'terrain_room_dungeon', 'terrain_depth_maze', 'terrain_road_links', 'terrain_avoidance_path',
    'terrain_cliff_band', 'terrain_biome_mosaic'
  ] },
  { title: 'World population', actions: [
    'formation_line', 'formation_arc', 'formation_ring', 'formation_spiral', 'formation_wedge',
    'formation_stagger', 'formation_jitter_grid', 'formation_scatter', 'formation_poisson',
    'formation_waypoint_path', 'formation_perimeter', 'actors_translate', 'actors_rotate',
    'actors_mirror', 'actors_reassign_prefab'
  ] },
  { title: 'Narrative director', actions: [
    'narrative_branch_pair', 'narrative_branch_multi', 'narrative_extend_chain',
    'narrative_insert_stage', 'narrative_bypass_stage', 'narrative_relabel_quest',
    'narrative_fork_quest', 'narrative_merge_endings', 'event_clone', 'event_batch_retarget',
    'event_batch_retrigger', 'event_bind_quest', 'event_actor_dialogue_batch',
    'event_actor_audio_batch', 'event_actor_loot_batch'
  ] },
  { title: 'Level topology', actions: [
    'terrain_dilate_mask', 'terrain_erode_mask', 'terrain_open_mask', 'terrain_close_mask', 'terrain_majority_eight',
    'terrain_largest_region', 'terrain_connect_regions', 'terrain_diamond_landmass', 'terrain_hex_landmass', 'terrain_triangular_landmass',
    'terrain_radial_spokes', 'terrain_concentric_paths', 'terrain_bezier_road', 'terrain_spline_river', 'terrain_random_walker',
    'terrain_flow_channels', 'terrain_edge_falloff', 'terrain_moat_castle', 'terrain_ruin_foundations', 'terrain_forest_clusters',
    'terrain_patch_scatter', 'terrain_wave_pattern', 'terrain_checker_rotated', 'terrain_mountain_pass', 'terrain_archipelago_bridges',
  ] },
  { title: 'Actor layout', actions: [
    'actors_snap_grid', 'actors_snap_ground', 'actors_quantize_facing', 'actors_face_point', 'actors_face_actor',
    'actors_align_x', 'actors_align_y', 'actors_even_spacing', 'actors_radial_expand', 'actors_radial_contract',
    'actors_scale_cloud', 'actors_shift_altitude', 'actors_seeded_jitter', 'actors_separate_overlap', 'actors_snap_terrain',
    'actors_clamp_bounds', 'actors_swap_poses', 'actors_copy_facing', 'actors_center_group', 'actors_wave_offsets',
    'actors_staircase', 'actors_terrain_walk', 'actors_depth_rank', 'actors_random_facing', 'actors_clone_selected',
  ] },
  { title: 'Story production', actions: [
    'quest_add_prologue', 'quest_add_epilogue', 'quest_extend_terminal', 'quest_fork_terminal', 'quest_bridge_endings',
    'quest_detour_leaf', 'quest_stage_reparent', 'quest_swap_branches', 'quest_order_choices', 'quest_backfill_objectives',
    'quest_template_sequence', 'quest_template_binary_tree', 'quest_stage_cleanup', 'quest_mirror_branch', 'quest_convert_to_linear',
    'event_stage_dialogue', 'event_stage_flag', 'event_stage_cutscene', 'event_stage_music', 'event_stage_item',
    'event_stage_camera', 'event_stage_portal', 'event_trigger_promote', 'event_flag_gate', 'event_mass_duplicate',
  ] },
  { title: 'Environmental scenes', actions: [
    'sensor_wind_gust', 'sensor_rain_onset', 'sensor_visibility_warning', 'sensor_flood_tide', 'sensor_updraft_boost',
    'sensor_turbulence_alarm', 'sensor_low_traction', 'sensor_fast_fall', 'sensor_collision_impact', 'sensor_instrument_heading',
    'sensor_sextant_fix', 'sensor_gyro_tilt', 'sensor_island_altitude', 'sensor_pressure_change', 'sensor_party_morale',
    'page_condition_copy', 'page_action_copy', 'page_condition_swap', 'page_action_swap', 'page_condition_rotate',
    'page_action_rotate', 'page_threshold_shift', 'page_threshold_scale', 'page_duplicate_signal', 'page_dual_threshold_branches',
  ] },
];
const SAMPLE: Record<string, Record<string, unknown>> = {
  tile_set: { x: 0, y: 0, tile: 1 }, rect_fill: { x: 0, y: 0, width: 3, height: 3, tile: 1 },
  line_draw: { x: 0, y: 0, x2: 3, y2: 3, tile: 1 },
  ellipse_fill: { x: 0, y: 0, width: 4, height: 4, tile: 1 },
  flood_fill: { x: 0, y: 0, tile: 1 }, replace_tile: { before: 0, after: 1 },
  checker_fill: { x: 0, y: 0, width: 4, height: 4, a: 1, b: 2 },
  stamp: { x: 0, y: 0, width: 2, height: 2, tiles: [1, -1, 1, 1] },
  region_paste: { x: 0, y: 0, width: 2, height: 2, tiles: [1, 1, 1, 1] },
  shift_layer: { dx: 1, dy: 0, wrap: false }, rotate_90: { clockwise: true },
  layer_add: { layer: 'decoration', width: 16, height: 16, palette: ['foliage'], fill: -1 },
  layer_duplicate: { new_layer: 'ground_copy' }, layer_reorder: { position: 0 },
  layer_elevation: { elevation_m: 4 }, palette_add: { value: 'newtile' },
  palette_replace: { index: 0, value: 'newground' }, palette_swap: { a: 0, b: 1 },
  palette_remove: { index: 2 }, layer_resize: { width: 20, height: 20, fill: -1 },
  layer_crop: { x: 0, y: 0, width: 8, height: 8 },
  prefab_add: { prefab_id: 'hero', kind: 'character', era: 'tile', asset_digest: '' },
  prefab_remove: { prefab_id: 'hero' }, prefab_clone: { prefab_id: 'hero', new_prefab_id: 'hero_alt' },
  prefab_retarget: { prefab_id: 'hero', asset_digest: '' },
  prefab_interaction: { prefab_id: 'hero', interaction_type: 'dialogue' },
  placement_add: { prefab_id: 'hero', x: 0, y: 0, z: 0 },
  placement_remove: { index: 0 }, placement_move: { index: 0, x: 1, y: 0, z: 0 },
  placement_rotate: { index: 0, degrees: 90 },
  placement_duplicate: { index: 0, dx: 1, dy: 0, dz: 0 },
  placement_mirror: { index: 0, axis: 'x', pivot: 0 },
  placement_grid: { prefab_id: 'hero', x: 0, y: 0, z: 0,
    columns: 3, rows: 3, dx: 2, dy: 2 },
  event_add: { event_id: 'entrance', trigger: 'enter', action: 'show_dialogue',
    target: 'hero', value: 'Welcome' },
  event_remove: { event_id: 'entrance' },
  event_condition: { event_id: 'entrance', condition_flag: 'door_open', condition_value: true },
  event_action: { event_id: 'entrance', action: 'show_dialogue', target: 'hero', value: 'Hello' },
  event_trigger: { event_id: 'entrance', trigger: 'interact' },
  quest_add: { quest_id: 'first_quest', stage_id: 'begin', title: 'A new beginning',
    objective: 'Reach the harbor' },
  quest_remove: { quest_id: 'first_quest' },
  quest_stage_append: { quest_id: 'first_quest', from_stage_id: 'begin',
    stage_id: 'second', objective: 'Chart the sky islands' },
  quest_objective: { quest_id: 'first_quest', stage_id: 'begin', objective: 'Talk to the captain' },
  quest_title: { quest_id: 'first_quest', title: 'The First Journey' },
  soundtrack_add: { soundtrack_id: 'exploration_theme' },
  soundtrack_remove: { soundtrack_id: 'exploration_theme' },
  soundtrack_reorder: { soundtrack_id: 'exploration_theme', position: 0 },
  environment_page_add: {"page_id":"weather_rise","signal":"temperature_c","comparison":"above","threshold":27,"kind":"set_flag","channel":"world","target":"temperature_alarm","value":"true"},
  environment_page_remove: {"page_id":"weather_rise"},
  environment_page_clone: {"page_id":"weather_rise","new_page_id":"weather_rise_alt"},
  environment_page_priority: {"page_id":"weather_rise","priority":10},
  environment_page_enable: {"page_id":"weather_rise","enabled":false},
  environment_page_repeat: {"page_id":"weather_rise","repeat":false},
  environment_page_cooldown: {"page_id":"weather_rise","cooldown_ms":1500},
  environment_condition_add: {"page_id":"weather_rise","signal":"humidity","comparison":"above","threshold":0.8},
  environment_condition_edit: {"page_id":"weather_rise","index":0,"signal":"temperature_c","comparison":"above","threshold":30},
  environment_condition_remove: {"page_id":"weather_rise","index":1},
  environment_action_add: {"page_id":"weather_rise","kind":"change_light","channel":"environment","target":"world","value":"dim"},
  environment_action_edit: {"page_id":"weather_rise","index":0,"kind":"set_flag","channel":"world","target":"weather_alert","value":"true"},
  environment_action_remove: {"page_id":"weather_rise","index":1},
  environment_flag_require: {"page_id":"weather_rise","flag":"storm_ready","required":true},
  environment_flag_clear: {"page_id":"weather_rise","flag":"storm_ready"},
  zone_add: {"zone_id":"river_entry","actor_id":"tree:0","event_id":"river_enter","radius_m":2,"x":0,"y":0,"z":0},
  zone_remove: {"zone_id":"river_entry"},
  zone_clone: {"zone_id":"river_entry","new_zone_id":"river_entry2"},
  zone_bind_actor: {"zone_id":"river_entry","actor_id":"tree:1"},
  zone_bind_event: {"zone_id":"river_entry","event_id":"river_enter"},
  zone_radius: {"zone_id":"river_entry","radius_m":5},
  zone_offset: {"zone_id":"river_entry","x":1,"y":2,"z":0},
  zone_translate: {"zone_id":"river_entry","dx":0,"dy":3,"dz":0},
  zone_scale: {"zone_id":"river_entry","factor":1.3},
  zone_duplicate_to_actor: {"zone_id":"river_entry","new_zone_id":"river_entry3","new_actor_id":"tree:1"},
  field_add: {"field_id":"rise","actor_id":"tree:0","kind":"updraft","radius_m":10,"acceleration_mps2":8,"x":0,"y":0,"z":2},
  field_remove: {"field_id":"rise"},
  field_clone: {"field_id":"rise","new_field_id":"rise_alt"},
  field_bind_actor: {"field_id":"rise","actor_id":"tree:1"},
  field_kind: {"field_id":"rise","kind":"vortex"},
  field_radius: {"field_id":"rise","radius_m":12},
  field_strength: {"field_id":"rise","acceleration_mps2":6},
  field_offset: {"field_id":"rise","x":0,"y":0,"z":2},
  field_invert: {"field_id":"rise"},
  field_duplicate_to_actor: {"field_id":"rise","new_field_id":"rise2","new_actor_id":"tree:1"},
  quest_stage_remove: {"quest_id":"journey","stage_id":"optional"},
  quest_stage_link: {"quest_id":"journey","from_stage_id":"middle","to_stage_id":"final"},
  quest_stage_unlink: {"quest_id":"journey","from_stage_id":"middle","to_stage_id":"final"},
  quest_stage_split: {"quest_id":"journey","from_stage_id":"middle","to_stage_id":"final","new_stage_id":"bridge","objective":"Cross the pass"},
  quest_stage_rename: {"quest_id":"journey","stage_id":"middle","new_stage_id":"encounter"},
  quest_start_change: {"quest_id":"journey","stage_id":"middle"},
  quest_stage_swap_objectives: {"quest_id":"journey","stage_a":"start","stage_b":"middle"},
  quest_duplicate: {"quest_id":"journey","new_quest_id":"journey2","title":"A different journey"},
  quest_stage_reorder: {"quest_id":"journey","stage_id":"middle","position":0},
  quest_rewrite_objectives: {"quest_id":"journey","objectives":{"middle":"Scout the watchtower"}},
  terrain_noise: {"layer":"ground","x":0,"y":0,"width":8,"height":8,"seed":42,"a":0,"b":1,"percent_b":45},
  terrain_smooth: {"layer":"ground","x":0,"y":0,"width":8,"height":8,"passes":2},
  terrain_terrace: {"layer":"ground","x":0,"y":0,"width":8,"height":8,"bands":2},
  terrain_outline: {"layer":"ground","x":0,"y":0,"width":8,"height":8,"target":1,"replacement":2},
  terrain_erode: {"layer":"ground","x":0,"y":0,"width":8,"height":8,"target":1,"replacement":0},
};

const NEW_PROCEDURAL = new Set<string>([
  'terrain_height_noise','terrain_fractal','terrain_ridge','terrain_islands',
  'terrain_crater','terrain_meander_river','terrain_lake','terrain_coastline',
  'terrain_talus','terrain_dunes','terrain_voronoi','terrain_contours',
  'terrain_floodplain','terrain_cave_automata','terrain_room_dungeon',
  'terrain_depth_maze','terrain_road_links','terrain_avoidance_path',
  'terrain_cliff_band','terrain_biome_mosaic',
]);
const NEW_FORMATIONS = new Set<string>([
  'formation_line','formation_arc','formation_ring','formation_spiral',
  'formation_wedge','formation_stagger','formation_jitter_grid',
  'formation_scatter','formation_poisson','formation_waypoint_path','formation_perimeter',
]);
const NEW_NARRATIVE = new Set<string>([
  'narrative_branch_pair','narrative_branch_multi','narrative_extend_chain',
  'narrative_insert_stage','narrative_bypass_stage','narrative_relabel_quest',
  'narrative_fork_quest','narrative_merge_endings',
]);
function newActionDefaults(name: string, layer: string): Record<string, unknown> | undefined {
  if (NEW_PROCEDURAL.has(name)) {
    const base: Record<string, unknown> = {
      layer, x: 0, y: 0, width: 12, height: 12,
      seed: 42, floor: 0, wall: 1, scale: 5, threshold: 0.5,
    };
    if (name === 'terrain_road_links') base.nodes = [[1,1],[5,5],[10,8]];
    if (name === 'terrain_avoidance_path') Object.assign(base, {
      start_x: 0, start_y: 0, end_x: 11, end_y: 11,
    });
    return base;
  }
  if (NEW_FORMATIONS.has(name)) {
    return {
      prefab_id: 'hero', count: 8, x: 0, y: 0, z: 0,
      radius: 8, spacing: 2, seed: 42,
      ...(name === 'formation_waypoint_path' ? {
        waypoints: [[0,0,0],[10,0,0],[10,10,0]],
      } : {}),
      ...(name === 'formation_perimeter' ? { width: 10, height: 8 } : {}),
    };
  }
  if (name === 'actors_translate') return { indices: [0], dx: 2, dy: 0, dz: 0 };
  if (name === 'actors_rotate') return { indices: [0], angle_deg: 90, pivot_x: 0, pivot_y: 0 };
  if (name === 'actors_mirror') return { indices: [0], axis: 'x', pivot_x: 0 };
  if (name === 'actors_reassign_prefab') return { indices: [0], prefab_id: 'hero' };
  if (NEW_NARRATIVE.has(name)) {
    const common: Record<string, unknown> = { quest_id: 'first_quest' };
    if (name === 'narrative_branch_pair' || name === 'narrative_branch_multi')
      return { ...common, from_stage_id: 'begin', stage_prefix: 'alternative',
        objectives: ['Find the secret route', 'Travel through the mountains'],
        ...(name.endsWith('multi') ? { choices: 2 } : {}) };
    if (name === 'narrative_extend_chain')
      return { ...common, from_stage_id: 'begin',
        stage_prefix: 'chapter', objectives: ['Find the relic', 'Return to the city'] };
    if (name === 'narrative_insert_stage')
      return { ...common, from_stage_id: 'begin', to_stage_id: 'ending',
        new_stage_id: 'transition', objective: 'Explore the pass' };
    if (name === 'narrative_bypass_stage') return { ...common, stage_id: 'middle' };
    if (name === 'narrative_relabel_quest') return { ...common, new_quest_id: 'journey_revised' };
    if (name === 'narrative_fork_quest')
      return { ...common, new_quest_id: 'alternative_journey', title: 'Alternate journey' };
    return { ...common, epilogue_id: 'epilogue', objective: 'Reunite at the harbor' };
  }
  if (name === 'event_clone')
    return { event_id: 'opening', new_event_id: 'opening_alt', target: 'hero' };
  if (name === 'event_batch_retarget')
    return { event_ids: ['opening'], target: 'hero' };
  if (name === 'event_batch_retrigger')
    return { event_ids: ['opening'], trigger: 'enter' };
  if (name === 'event_bind_quest')
    return { event_id: 'start_journey', quest_id: 'first_quest', target: 'hero' };
  if (name.startsWith('event_actor_'))
    return { indices: [0,1], event_prefix: 'actor_event',
      value: name.endsWith('loot_batch') ? 'healing_potion' :
        name.endsWith('audio_batch') ? 'village_theme' : 'Welcome, adventurer' };
  return undefined;
}


const NEW_HUNDRED_GROUPS = {
  topology: new Set<string>(['terrain_dilate_mask','terrain_erode_mask','terrain_open_mask','terrain_close_mask','terrain_majority_eight','terrain_largest_region','terrain_connect_regions','terrain_diamond_landmass','terrain_hex_landmass','terrain_triangular_landmass','terrain_radial_spokes','terrain_concentric_paths','terrain_bezier_road','terrain_spline_river','terrain_random_walker','terrain_flow_channels','terrain_edge_falloff','terrain_moat_castle','terrain_ruin_foundations','terrain_forest_clusters','terrain_patch_scatter','terrain_wave_pattern','terrain_checker_rotated','terrain_mountain_pass','terrain_archipelago_bridges']),
  actors: new Set<string>(['actors_snap_grid','actors_snap_ground','actors_quantize_facing','actors_face_point','actors_face_actor','actors_align_x','actors_align_y','actors_even_spacing','actors_radial_expand','actors_radial_contract','actors_scale_cloud','actors_shift_altitude','actors_seeded_jitter','actors_separate_overlap','actors_snap_terrain','actors_clamp_bounds','actors_swap_poses','actors_copy_facing','actors_center_group','actors_wave_offsets','actors_staircase','actors_terrain_walk','actors_depth_rank','actors_random_facing','actors_clone_selected']),
  story: new Set<string>(['quest_add_prologue','quest_add_epilogue','quest_extend_terminal','quest_fork_terminal','quest_bridge_endings','quest_detour_leaf','quest_stage_reparent','quest_swap_branches','quest_order_choices','quest_backfill_objectives','quest_template_sequence','quest_template_binary_tree','quest_stage_cleanup','quest_mirror_branch','quest_convert_to_linear','event_stage_dialogue','event_stage_flag','event_stage_cutscene','event_stage_music','event_stage_item','event_stage_camera','event_stage_portal','event_trigger_promote','event_flag_gate','event_mass_duplicate']),
  environment: new Set<string>(['sensor_wind_gust','sensor_rain_onset','sensor_visibility_warning','sensor_flood_tide','sensor_updraft_boost','sensor_turbulence_alarm','sensor_low_traction','sensor_fast_fall','sensor_collision_impact','sensor_instrument_heading','sensor_sextant_fix','sensor_gyro_tilt','sensor_island_altitude','sensor_pressure_change','sensor_party_morale','page_condition_copy','page_action_copy','page_condition_swap','page_action_swap','page_condition_rotate','page_action_rotate','page_threshold_shift','page_threshold_scale','page_duplicate_signal','page_dual_threshold_branches']),
};
function hundredActionDefaults(name: string, layer: string): Record<string, unknown> | undefined {
  if (NEW_HUNDRED_GROUPS.topology.has(name)) {
    const args: Record<string, unknown> = {
      layer, x: 0, y: 0, width: 12, height: 12, floor: 0, wall: 1, seed: 42,
    };
    if (name === 'terrain_bezier_road' || name === 'terrain_spline_river')
      args.control_points = [[0,0],[6,8],[11,11]];
    if (name === 'terrain_archipelago_bridges') args.seed = 42;
    return args;
  }
  if (NEW_HUNDRED_GROUPS.actors.has(name)) {
    const args: Record<string, unknown> = {indices: [0, 1]};
    const extras: Record<string, Record<string, unknown>> = {
      actors_snap_grid:{step:2},actors_snap_ground:{ground_z:0},
      actors_quantize_facing:{degrees:45},actors_face_point:{target_x:10,target_y:10},
      actors_face_actor:{target_index:2},actors_align_x:{value:5},
      actors_align_y:{value:5},actors_radial_expand:{distance:2},
      actors_radial_contract:{distance:2},actors_scale_cloud:{factor:1.5},
      actors_shift_altitude:{dz:2},actors_seeded_jitter:{seed:42,amplitude:1},
      actors_separate_overlap:{minimum_distance:2},actors_snap_terrain:{layer},
      actors_clamp_bounds:{min_x:0,max_x:12,min_y:0,max_y:12},
      actors_copy_facing:{source_index:2},actors_center_group:{x:5,y:5},
      actors_wave_offsets:{amplitude:2,period:3},actors_staircase:{step:2},
      actors_terrain_walk:{layer},actors_depth_rank:{base_z:0,step_z:1},
      actors_random_facing:{seed:42},actors_clone_selected:{dx:3,dy:2,dz:0},
    };
    return {...args,...(extras[name] || {})};
  }
  if (NEW_HUNDRED_GROUPS.story.has(name)) {
    const a: Record<string, unknown> = {quest_id:'first_quest'};
    if (name.startsWith('event_stage_')) return {
      event_id:'chapter_scene',target:'hero',value:'Welcome',trigger:'quest',
    };
    if (name === 'event_trigger_promote') return {event_id:'opening',trigger:'quest'};
    if (name === 'event_flag_gate') return {event_id:'opening',flag:'quest_ready',expected:true};
    if (name === 'event_mass_duplicate') return {
      source_event_ids:['opening'],prefix:'chapter',
    };
    return {...a,stage_id:'begin',new_stage_id:'next_chapter',
      objective:'Explore the region',prefix:'chapter',count:4,depth:2,
      from_stage_id:'begin',stage_a:'begin',stage_b:'middle',
      parent_stage_id:'begin',new_parent_id:'begin',
      choices:['middle'],objectives:['Find the temple','Follow the road'],
      stage_order:['begin','middle','ending']};
  }
  if (NEW_HUNDRED_GROUPS.environment.has(name)) {
    if (name.startsWith('sensor_')) return {page_id:name+'_event',priority:5};
    const a:Record<string,unknown>={page_id:'weather_rise'};
    if (name.endsWith('_copy')) a.source_index=0;
    if (name.endsWith('_swap')) Object.assign(a,{a:0,b:1});
    if (name.endsWith('_rotate')) a.offset=1;
    if (name==='page_threshold_shift') a.delta=5;
    if (name==='page_threshold_scale') a.factor=1.2;
    if (name==='page_duplicate_signal') Object.assign(a,{
      new_page_id:'weather_alt',signal:'altitude_m',comparison:'above',threshold:100,
    });
    if (name==='page_dual_threshold_branches') Object.assign(a,{
      low_page_id:'sensor_low',high_page_id:'sensor_high',low:10,high:100,
    });
    return a;
  }
  return undefined;
}


const NEW_500_BIOME=new Set<string>(['terrain_fault_lines','terrain_plate_edges','terrain_tectonic_ridges','terrain_graben_valley','terrain_volcano_cone','terrain_lava_channels','terrain_caldera_ring','terrain_mesa_terraces','terrain_karst_sinkholes','terrain_mountain_chain','terrain_alluvial_fans','terrain_delta_branches','terrain_oxbow_lakes','terrain_braided_streams','terrain_watershed_divide','terrain_glacial_valley','terrain_moraine_ridges','terrain_fjord_channels','terrain_reef_atolls','terrain_tidal_flats','terrain_rainforest','terrain_savanna','terrain_taiga','terrain_tundra','terrain_alpine_meadow','terrain_desert_badlands','terrain_mangrove','terrain_swamp_bog','terrain_grass_steppe','terrain_volcanic_ash','terrain_fungal_caverns','terrain_crystal_caves','terrain_stalagmite_fields','terrain_limestone_pillars','terrain_underground_rivers','terrain_lava_tubes','terrain_geode_chambers','terrain_abyssal_pits','terrain_bioluminescent_groves','terrain_ruined_catacombs','terrain_floating_islands','terrain_cloud_banks','terrain_wind_corridors','terrain_sky_arches','terrain_storm_belts','terrain_levitation_nodes','terrain_aurora_paths','terrain_meteor_craters','terrain_gravity_wells','terrain_portal_constellations']);
const NEW_500_STRUCTURE=new Set<string>(['structure_village_square','structure_market_stalls','structure_courtyard','structure_town_grid','structure_radial_city','structure_harbor_piers','structure_farm_fields','structure_orchard_rows','structure_house_cluster','structure_canal_district','structure_castle_keep','structure_outer_wall','structure_gatehouse','structure_corner_bastions','structure_moat_bridge','structure_watchtowers','structure_wall_walk','structure_arrow_slits','structure_turret_ring','structure_fortified_crossroads','structure_dungeon_rooms','structure_dungeon_corridors','structure_spiral_vault','structure_treasure_chambers','structure_pillar_hall','structure_prison_cells','structure_cathedral_nave','structure_catacomb_grid','structure_trap_gauntlet','structure_boss_arena','structure_factory_floor','structure_conveyor_lanes','structure_power_grid','structure_storage_racks','structure_warehouse_aisles','structure_rail_depot','structure_shipyard_slips','structure_mining_shafts','structure_pipeline_array','structure_reactor_chamber','structure_suspension_bridge','structure_stepping_stones','structure_ramp_switchbacks','structure_cliff_stairs','structure_tunnel_bore','structure_treetop_walks','structure_sky_platforms','structure_rope_bridge','structure_portal_plaza','structure_island_airfield']);
const NEW_500_ENCOUNTER=new Set<string>(['encounter_village_crowd','encounter_market_vendors','encounter_tavern_guests','encounter_festival_parade','encounter_harbor_workers','encounter_farm_hands','encounter_caravan_merchants','encounter_city_patrol','encounter_castle_guards','encounter_royal_court','encounter_wolf_pack','encounter_deer_herd','encounter_bird_flock','encounter_fish_school','encounter_insect_swarm','encounter_horse_stampede','encounter_bear_den','encounter_predator_ring','encounter_migratory_line','encounter_turtle_nesting','encounter_squad_wedge','encounter_siege_lines','encounter_archer_wall','encounter_shield_circle','encounter_cavalry_charge','encounter_ambush_arcs','encounter_flanking_pincer','encounter_rear_guard','encounter_scout_net','encounter_boss_minions','encounter_sky_pirates','encounter_airship_crew','encounter_cloud_drakes','encounter_floating_island_settlers','encounter_wind_surfers','encounter_tower_watchers','encounter_balloon_riders','encounter_glider_convoy','encounter_sky_fishermen','encounter_aurora_procession','encounter_dungeon_slimes','encounter_cave_bats','encounter_crypt_guardians','encounter_labyrinth_wardens','encounter_treasure_mimics','encounter_portal_sentinels','encounter_ruin_explorers','encounter_mine_workers','encounter_fungal_foragers','encounter_underground_merchants']);
const NEW_500_QUEST=new Set<string>(['quest_lighthouse_blackout','quest_sky_island_rescue','quest_stolen_compass','quest_moon_tide_survey','quest_forest_railway','quest_clockwork_herald','quest_flooded_archive','quest_starlit_observatory','quest_copper_mine_dispute','quest_mountain_pass','quest_marsh_lanterns','quest_garden_of_machines','quest_whispering_canyon','quest_archipelago_mail','quest_ironwood_heirloom','quest_saltwind_market','quest_beacon_constellation','quest_ruins_of_ash','quest_library_of_winds','quest_mirror_lake','quest_tower_chimes','quest_glass_dunes','quest_deepwater_engine','quest_hidden_canal','quest_ember_festival','quest_orchard_winter','quest_jade_quarry','quest_bridge_of_mist','quest_river_sentinel','quest_northern_outpost','quest_cavern_echos','quest_sky_orchards','quest_clocktower_apprentice','quest_wildlife_corridor','quest_aurora_station','quest_drowned_temple','quest_coral_foundry','quest_lost_weather_balloon','quest_underground_orchard','quest_firefly_navigation','quest_solar_tide_engine','quest_icebound_caravan','quest_treetop_council','quest_sextant_apprentice','quest_broken_portal','quest_floating_foundry','quest_night_ferry','quest_echoes_of_the_city','quest_moonlit_greenhouse','quest_last_skybridge']);
const NEW_500_REACTION=new Set<string>(['reaction_storm_warning','reaction_rain_audio','reaction_fog_camera','reaction_gale_sails','reaction_wet_roads','reaction_river_flood','reaction_ground_freeze','reaction_turbulence_fx','reaction_hail_shelter','reaction_humidity_fog','reaction_terminal_fall','reaction_rough_landing','reaction_kinetic_impact','reaction_skin_tension','reaction_low_stability','reaction_cliff_climb','reaction_weight_shift','reaction_slick_fabric','reaction_updraft_lift','reaction_native_field','reaction_altitude_chart','reaction_sextant_sighting','reaction_bubble_sextant','reaction_compass_turn','reaction_triangulation','reaction_skyisland_arrival','reaction_gyro_drift','reaction_pressure_front','reaction_navigation_current','reaction_night_navigation','reaction_party_low_morale','reaction_heroic_reputation','reaction_quest_music','reaction_village_emotion','reaction_party_morale_boost','reaction_combat_music','reaction_stealth_audio','reaction_world_axis','reaction_quest_unlock','reaction_morale_camp','reaction_moon_tide','reaction_sunrise_cinematic','reaction_eclipse_shadows','reaction_foliage_shadow','reaction_terrain_erosion','reaction_falling_building','reaction_cloud_portal','reaction_tidal_reef','reaction_deep_night','reaction_seasonal_bloom']);
function newFiveHundredDefaults(action: string, layer: string): Record<string, unknown> | undefined {
  if (NEW_500_BIOME.has(action)) return {
    layer, x: 0, y: 0, width: 12, height: 12,
    floor: 0, wall: 1, seed: 42, threshold: 0.53, scale: 5,
  };
  if (NEW_500_STRUCTURE.has(action)) return {
    layer, x: 0, y: 0, width: 12, height: 12, floor: 0, wall: 1, seed: 42,
  };
  if (NEW_500_ENCOUNTER.has(action)) return {
    prefab_id: 'merchant', count: 8, event_prefix: action,
    dialogue: 'Welcome to this world', x: 8, y: 8, z: 0,
    seed: 42, radius: 9, spacing: 2,
  };
  if (NEW_500_QUEST.has(action)) return {
    quest_id: action, event_id: action + '_start',
  };
  if (NEW_500_REACTION.has(action)) return {
    page_id: action + '_page', priority: 5, cooldown_ms: 2000,
  };
  return undefined;
}

function label(name: string) { return name.replace(/_/g, ' '); }
const palette = ['#1b4230','#62727f','#406c99','#7d704c','#8b5b83','#777c3e','#5e6274'];
function Button({ title, press, disabled }: { title: string; press: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={title}
    accessibilityState={{ disabled: !!disabled }} onPress={press} disabled={disabled}
    style={{ paddingVertical: 10, paddingHorizontal: 13, borderRadius: 8, borderWidth: 1,
      borderColor: '#4d6780', backgroundColor: disabled ? '#232933' : '#293c4d', margin: 3 }}>
    <Text style={{ color: disabled ? '#8792a0' : '#e8eff6', fontWeight: '600' }}>{title}</Text>
  </TouchableOpacity>;
}
export default function GameFrontierAuthoringPanel({ project, disabled = false, onSaved, onDirtyChange }: Props) {
  const [doc, setDoc] = useState<ForgeDocument | null>(null);
  const [action, setAction] = useState('tile_set');
  const [search, setSearch] = useState('');
  const [toolFamily, setToolFamily] = useState('Tiles & geometry');
  const [recipeView, setRecipeView] = useState(false);
  const [recipeQuery, setRecipeQuery] = useState('');
  const [recipeDomain, setRecipeDomain] = useState('');
  const [recipeGeneration, setRecipeGeneration] = useState<'classic' | 'expanded' | 'directed' | 'final' | 'worldline' | 'phase' | 'campaign' | 'chronicle' | 'epoch'>('epoch');
  const [systemLayer, setSystemLayer] = useState('');
  const [director, setDirector] = useState('');
  const [finish, setFinish] = useState('');
  const [worldline, setWorldline] = useState('');
  const [phase, setPhase] = useState('');
  const [campaign, setCampaign] = useState('');
  const [chronicle, setChronicle] = useState('');
  const [epoch, setEpoch] = useState('');
  const [recipeResults, setRecipeResults] = useState<ForgeRecipeResults | null>(null);
  const [parameters, setParameters] = useState('{"layer":"ground","x":0,"y":0,"tile":1}');
  const [steps, setSteps] = useState<ForgeStep[]>([]);
  const [selectedLayer, setSelectedLayer] = useState('ground');
  const [tilePixels, setTilePixels] = useState<number[]>([]);
  const [gridSize, setGridSize] = useState<[number,number]>([0, 0]);
  const [seed, setSeed] = useState('42');
  const [islands, setIslands] = useState('12');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ForgeBuild | null>(null);
  const [gameplayProbe, setGameplayProbe] = useState<ForgeGameplayProbe | null>(null);
  const [probePosition, setProbePosition] = useState('[1,1,0]');
  const [probeSignals, setProbeSignals] = useState('{"altitude_m":0}');
  const pending = disabled || busy;
  useEffect(() => { onDirtyChange?.(steps.length > 0); }, [steps.length, onDirtyChange]);
  const load = useCallback(async () => {
    const current = await inspectForge(project.project_id);
    setDoc(current);
    setSelectedLayer(value => current.layers.some(layer => layer.id === value) ?
      value : current.layers[0]?.id || 'ground');
  }, [project.project_id]);
  useEffect(() => {
    let live = true;
    inspectForge(project.project_id).then(value => {
      if (!live) return;
      setDoc(value);
      setSelectedLayer(old => value.layers.some(layer => layer.id === old) ?
        old : value.layers[0]?.id || 'ground');
    }).catch(reason => { if (live) setError(String(reason?.message || reason)); });
    return () => { live = false; };
  }, [project.project_id, project.version]);
  useEffect(() => {
    if (!doc) return;
    const layer = doc.layers.find(row => row.id === selectedLayer);
    if (!layer) return;
    const width = Math.min(12, layer.size[0]), height = Math.min(12, layer.size[1]);
    let live = true;
    copyForgeTiles(project.project_id, selectedLayer, 0, 0, width, height).then(value => {
      if (live) { setTilePixels(value.tiles); setGridSize([width, height]); }
    }).catch(() => { if (live) setTilePixels([]); });
    return () => { live = false; };
  }, [doc?.source_sha256, selectedLayer, project.project_id]);
  const listed = useMemo(() => {
    const query = search.trim().toLowerCase();
    return GROUPS.filter(group => query.length > 0 || group.title === toolFamily)
      .map(group => ({
        ...group, actions: group.actions.filter(item =>
          (!doc || doc.action_catalog.includes(item)) && item.includes(query)),
      })).filter(group => group.actions.length);
  }, [doc, search, toolFamily]);
  const loadRecipes = async (offset = 0) => {
    if (pending) return;
    setBusy(true);
    setError('');
    try {
      const result = await searchForgeRecipes(recipeQuery, recipeDomain, offset, 32,
        recipeGeneration, systemLayer, director, finish, worldline, phase, campaign, chronicle, epoch);
      setRecipeResults(result);
      setNotice(result.matched + ' source-changing production recipes match your search.');
    } catch (reason: any) {
      setError(String(reason?.message || reason));
    } finally { setBusy(false); }
  };
  const selectRecipe = (recipe: ForgeRecipe) => {
    if (!(/^(produce_[a-z_]+__[a-z_]+|expand_[a-z_]+__[a-z_]+___[a-z_]+|direct_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+|complete_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+|worldline_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+|phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+|campaign_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+|chronicle_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+|epoch_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+)$/.test(recipe.operation))) {
      setError('Invalid game production recipe identity.'); return;
    }
    const layer = doc?.layers.find(item => item.id === selectedLayer) || doc?.layers[0];
    const actor = doc?.actor_catalog?.[0];
    const chosen = {
      layer: layer?.id || 'ground', x: 0, y: 0,
      width: Math.min(12, layer?.size[0] || 12),
      height: Math.min(12, layer?.size[1] || 12),
      floor: 0, wall: 1, seed: 42, scale: 5, threshold: .53,
      instance_id: "a",
      prefab_id: doc?.prefab_catalog?.[0]?.id || 'author_prefab_first',
      count: 4, z: 0, radius: 8, spacing: 2,
      ...(actor ? {target: actor.prefab_id + ':' + actor.index} : {}),
    };
    setAction(recipe.operation);
    setParameters(JSON.stringify(chosen, null, 2));
    setNotice('Selected: ' + recipe.domain + ' / ' + recipe.source_blueprint +
      ' / ' + recipe.treatment +
      (recipe.system_layer ? ' / '+recipe.system_layer : '') +
      (recipe.direction ? ' / '+recipe.direction : '') +
      (recipe.finish ? ' / '+recipe.finish : '') +
      (recipe.worldline ? ' / '+recipe.worldline : '') +
      (recipe.phase ? ' / '+recipe.phase : '') +
      (recipe.campaign ? ' / '+recipe.campaign : '') +
      (recipe.chronicle ? ' / '+recipe.chronicle : '') +
       (recipe.epoch ? ' / '+recipe.epoch : '') +
      '. Preview actual source edits before saving.');
  };
  const choose = (name: string) => {
    setAction(name);
    const args = { ...(newFiveHundredDefaults(name, selectedLayer) || hundredActionDefaults(name, selectedLayer) || newActionDefaults(name, selectedLayer) || SAMPLE[name] || {}) };
    if (NEW_500_ENCOUNTER.has(name) && doc?.prefab_catalog?.length)
      args.prefab_id = doc.prefab_catalog[0].id;
    if (NEW_500_QUEST.has(name) && doc?.actor_catalog?.length) {
      const actor = doc.actor_catalog[0];
      args.target = actor.prefab_id + ':' + actor.index;
    }
    if (!NEW_PROCEDURAL.has(name) && ['tile_set','rect_fill','line_draw','ellipse_fill','flood_fill','replace_tile',
      'checker_fill','stamp','region_paste','shift_layer','flip_horizontal','flip_vertical',
      'rotate_90','layer_remove','layer_duplicate','layer_reorder','layer_elevation',
      'palette_add','palette_replace','palette_swap','palette_remove','layer_resize',
      'layer_crop','layer_clear'].includes(name)) args.layer = selectedLayer;
    setParameters(JSON.stringify(args, null, 2));
  };
  const enqueue = () => {
    try {
      if (steps.length >= 64) throw Error('One transaction supports at most 64 editor actions.');
      const args: unknown = JSON.parse(parameters);
      if (!args || Array.isArray(args) || typeof args !== 'object') throw Error(
        'Action parameters must be a JSON object.');
      setSteps(existing => [...existing, { action, parameters: args as Record<string, unknown> }]);
      setError('');
    } catch (reason: any) { setError(String(reason?.message || reason)); }
  };
  const transact = async (preview: boolean) => {
    if (!doc || steps.length === 0) return;
    setBusy(true); setError('');
    try {
      const result = await editForge(project.project_id, doc, steps, preview);
      if (!preview && result.persisted) {
        setSteps([]);
        await load();
        onSaved(await getLearningProject(project.project_id));
        setNotice('Real game source committed to the project revision history.');
      } else if ('candidate_sha256' in result) setNotice('Preview compiled: ' + result.candidate_sha256.slice(0, 16) +
        ' · no source changes persisted.');
    } catch (reason: any) { setError(String(reason?.message || reason)); }
    finally { setBusy(false); }
  };
  const build = async (publish: boolean) => {
    if (!doc) return;
    const numberSeed = Number(seed), numberIslands = Number(islands);
    if (!Number.isSafeInteger(numberSeed) || numberSeed < 0 ||
        !Number.isSafeInteger(numberIslands) || numberIslands < 3 || numberIslands > 64) {
      setError('Choose an integer seed and between 3 and 64 sky islands.'); return;
    }
    setBusy(true); setError('');
    try {
      const result = publish ? await exportForge(project.project_id, doc, numberSeed, numberIslands)
        : await buildForge(project.project_id, numberSeed, numberIslands);
      setReport(result);
      setNotice(publish ? 'Actual Godot project files added to your saved project.' :
        'Playable expedition compiled and route-playtested from current Forge source.');
      if (publish) { await load(); onSaved(await getLearningProject(project.project_id)); }
    } catch (reason: any) { setError(String(reason?.message || reason)); }
    finally { setBusy(false); }
  };
  const probe = async () => {
    setBusy(true); setError('');
    try {
      const coords: unknown = JSON.parse(probePosition);
      const signals: unknown = JSON.parse(probeSignals);
      if (!Array.isArray(coords) || coords.length !== 3 ||
          coords.some(value => typeof value !== 'number' || !Number.isFinite(value)) ||
          !signals || typeof signals !== 'object' || Array.isArray(signals) ||
          Object.values(signals).some(value => typeof value !== 'number' || !Number.isFinite(value))) {
        throw new Error('Provide three finite source XYZ numbers and a typed sensor signal object.');
      }
      const result = await previewForgeGameplay(project.project_id, coords as number[],
        signals as Record<string, number>);
      setGameplayProbe(result);
      setNotice('Real RPG/physics reference simulation evaluated from saved source.');
    } catch (reason: any) { setError(String(reason?.message || reason)); }
    finally { setBusy(false); }
  };
  return <View style={{ gap: 12, paddingVertical: 10 }}>
    <Text style={{ color: '#eef3fa', fontSize: 20, fontWeight: '700' }}>Forge Studio · Real Game Authoring</Text>
    <Text style={{ color: '#a7bacf' }}>5,000 executable tools for maps, characters, quests, environmental events, native physics and soundtracks.
      Every saved edit changes the project source and is consumed by the real game compiler.</Text>
    {!doc ? <ActivityIndicator color="#8bd5e8" /> : <View>
      <Text style={{ color: '#bdcddd' }}>Revision {doc.expected_version} · {doc.layers.length} layers
        · {doc.placed_actor_count} actors · {doc.quest_count} quests · {doc.music_cue_count} audio cues</Text>
      <Text selectable style={{ color: '#829db0', fontSize: 11 }}>{doc.source_sha256}</Text>
      <Text selectable style={{ color: '#aec5d6', fontSize: 12 }}>
        Actual prefabs: {doc.prefab_catalog?.map(item => item.id).join(', ') || '(author a prefab first)'}
      </Text>
      <Text selectable style={{ color: '#aec5d6', fontSize: 12 }}>
        Placed actors: {doc.actor_catalog?.map(item => item.prefab_id + ':' + item.index).join(', ')
          || '(place an actor before creating quest-giver events)'}
      </Text>
      <Text selectable style={{ color: '#aec5d6', fontSize: 12 }}>
        Authored quests: {doc.quest_catalog?.map(item => item.id).join(', ') || '(none yet)'}
      </Text>
    </View>}
    {!!error && <Text accessibilityRole="alert" style={{ color: '#ffb1a9' }}>{error}</Text>}
    {!!notice && <Text style={{ color: '#b2e3c7' }}>{notice}</Text>}
    <Text style={{ color: '#d5e2f0', fontWeight: '700' }}>Tile viewport (press a tile to queue its paint coordinates)</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator>
      <View style={{ gap: 2 }}>{Array.from({ length: gridSize[1] }, (_, y) =>
        <View key={y} style={{ flexDirection: 'row', gap: 2 }}>{Array.from({ length: gridSize[0] }, (_, x) => {
          const v = tilePixels[y * gridSize[0] + x] ?? -1;
          return <TouchableOpacity key={x} accessibilityRole="button"
            accessibilityLabel={'Paint map coordinate ' + x + ',' + y}
            disabled={pending} onPress={() => {
              setAction('tile_set'); setParameters(JSON.stringify({
                layer: selectedLayer, x, y, tile: 1,
              }, null, 2));
            }} style={{ width: 26, height: 26, borderRadius: 2,
              borderWidth: 1, borderColor: '#536272',
              backgroundColor: v < 0 ? '#171b22' : palette[v % palette.length] }} />;
        })}</View>)}</View>
    </ScrollView>
    <Text style={{ color: '#c4d4e4' }}>Active layer</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator style={{ maxHeight: 51 }}>
      <View style={{ flexDirection: 'row' }}>{doc?.layers.map(layer =>
        <Button key={layer.id} title={(selectedLayer === layer.id ? '✓ ' : '') + layer.id}
          disabled={pending} press={() => setSelectedLayer(layer.id)} />)}</View>
    </ScrollView>
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Choose an executable editor tool</Text>
    <TextInput value={search} onChangeText={setSearch} accessibilityLabel="Search 500 core game editor tools"
      placeholder="Search tiles, NPCs, quests, events…" placeholderTextColor="#75869a"
      style={{ color: '#f0f5fb', borderWidth: 1, borderColor: '#526478', borderRadius: 7, padding: 10 }} />
    <ScrollView horizontal showsHorizontalScrollIndicator accessibilityLabel="Forge tool categories">
      <View style={{ flexDirection: 'row' }}>{GROUPS.map(group =>
        <Button key={group.title} title={(toolFamily === group.title ? '✓ ' : '') + group.title}
          disabled={pending} press={() => { setToolFamily(group.title); setSearch(''); }} />)}</View>
    </ScrollView>
    <Button title={(recipeView ? '✓ ' : '') + 'Browse 4,999,999,500 production recipes'}
      disabled={pending || !doc} press={() => {
        setRecipeView(value => !value); setRecipeResults(null);
      }} />
    {recipeView && <View style={{ gap: 8 }}>
      <Text style={{ color: '#dae8f4', fontWeight: '700' }}>
        Production · 499,999,999,500 compositions across nine source-authoring generations
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Button disabled={pending} title={(recipeGeneration === 'classic' ? '✓ ' : '') + 'Original 4,500'}
          press={() => { setRecipeGeneration('classic'); setEpoch(''); setChronicle(''); setSystemLayer(''); setDirector(''); setFinish(''); setWorldline(''); setPhase(''); setCampaign(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'expanded' ? '✓ ' : '') + 'Gameplay 45,000'}
          press={() => { setRecipeGeneration('expanded'); setEpoch(''); setChronicle(''); setDirector(''); setFinish(''); setWorldline(''); setPhase(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'directed' ? '✓ ' : '') + 'Directed 450,000'}
          press={() => { setRecipeGeneration('directed'); setEpoch(''); setChronicle(''); setFinish(''); setWorldline(''); setPhase(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'final' ? '✓ ' : '') + 'Final 4,500,000'}
          press={() => { setRecipeGeneration('final'); setEpoch(''); setChronicle(''); setWorldline(''); setPhase(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'worldline' ? '✓ ' : '') + 'Worldlines 45M'}
          press={() => { setRecipeGeneration('worldline'); setEpoch(''); setChronicle(''); setPhase(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'phase' ? '✓ ' : '') + 'Phases 450M'}
          press={() => { setRecipeGeneration('phase'); setEpoch(''); setChronicle(''); setCampaign(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'campaign' ? '✓ ' : '') + 'Campaigns 4.5B'}
          press={() => { setRecipeGeneration('campaign'); setEpoch(''); setChronicle(''); setRecipeQuery(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'chronicle' ? '✓ ' : '') + 'Chronicles 45B'}
          press={() => { setRecipeGeneration('chronicle'); setEpoch(''); setRecipeQuery(''); setRecipeResults(null); }}/>
        <Button disabled={pending} title={(recipeGeneration === 'epoch' ? '✓ ' : '') + 'Epochs 450B'}
          press={() => { setRecipeGeneration('epoch'); setRecipeQuery(''); setRecipeResults(null); }}/>
      </View>
      <TextInput value={recipeQuery} onChangeText={setRecipeQuery}
        editable={recipeGeneration !== 'epoch' && recipeGeneration !== 'chronicle' && recipeGeneration !== 'campaign'}
        accessibilityLabel="Search production recipes"
        placeholder="Search worlds, quests, NPCs, weather…"
        placeholderTextColor="#8393a6"
        style={{ color:'#f3f7ff', borderWidth:1, borderRadius:7,
          padding:10, borderColor:'#51677e' }} />
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection:'row' }}>
          {['','realm','architecture','population','chronicle','atmosphere',
            'settlement','wildland','stronghold','expedition','living_story'].map(domain =>
            <Button key={domain || 'all'} disabled={pending}
              title={(recipeDomain === domain ? '✓ ' : '') + (domain || 'All')}
              press={() => { setRecipeDomain(domain); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>
      {(recipeGeneration === 'expanded' || recipeGeneration === 'directed' || recipeGeneration === 'final' || recipeGeneration === 'worldline' || recipeGeneration === 'phase' || recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection: 'row' }}>
          {['','wayfinding','seasons','destructibles','weather','combat','commerce',
            'stealth','verticality','migration','story_convergence'].map(layer =>
            <Button key={layer || 'all'} disabled={pending}
              title={(systemLayer === layer ? '✓ ' : '') + (layer || 'All systems')}
              press={() => { setSystemLayer(layer); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'directed' || recipeGeneration === 'final' || recipeGeneration === 'worldline' || recipeGeneration === 'phase' || recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection: 'row' }}>
          {['','navigation_alternates','ecology_cycles','tactical_zones','cinematic_staging',
            'resource_routes','faction_reactions','physics_obstacles','audio_cues',
            'quest_continuity','player_agency'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(director === name ? '✓ ' : '') + (name || 'All directors')}
              press={() => { setDirector(name); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'final' || recipeGeneration === 'worldline' || recipeGeneration === 'phase' || recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection:'row' }}>
          {['','route_optimization','settlement_life','environmental_fidelity',
            'character_staging','combat_readiness','resource_balance',
            'cinematic_continuity','vertical_routes','ecosystem_restore',
            'alternate_endings'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(finish === name ? '✓ ' : '') + (name || 'All finishing passes')}
              press={() => { setFinish(name); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'worldline' || recipeGeneration === 'phase' || recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection:'row' }}>
          {['','river_network','city_circulation','wilderness_ecology','tactical_encounters',
            'subterranean_routes','sky_navigation','social_reputation',
            'environmental_pressure','narrative_consequence','cinematic_blocking'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(worldline === name ? '✓ ' : '') + (name || 'All worldlines')}
              press={() => { setWorldline(name); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'phase' || recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection:'row' }}>
          {['','dawn_routes','winter_crossings','storm_shelters','market_cycles','siege_fronts',
            'night_patrols','habitat_migrations','sky_transits','faction_turns',
            'ending_convergence'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(phase === name ? '✓ ' : '') + (name || 'All phases')}
              press={() => { setPhase(name); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'campaign' || recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection:'row' }}>
          {['','chapter_crossroads','civic_worlds','open_ocean_routes','sky_island_circuit',
            'underground_transit','faction_frontiers','siege_campaigns',
            'ecological_chains','cinematic_sequences','epilogue_variants'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(campaign === name ? '✓ ' : '') + (name || 'All campaigns')}
              press={() => { setCampaign(name); setRecipeQuery(''); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {(recipeGeneration === 'chronicle' || recipeGeneration === 'epoch') && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection: 'row' }}>
          {['','first_arrival','survey_and_discovery','settlement_growth',
            'regional_upheaval','emergency_response','diaspora_routes',
            'institutional_change','faction_reconciliation',
            'generational_legacy','renewal_and_return'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(chronicle === name ? '✓ ' : '') + (name || 'All chronicles')}
              press={() => { setChronicle(name); setRecipeResults(null); }} />)}
        </View>
      </ScrollView>}
      {recipeGeneration === 'epoch' && <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ flexDirection: 'row' }}>
          {['','daybreak_routes','nightfall_networks','spring_thaw',
            'summer_drought','autumn_trade','winter_shelter','flood_recovery',
            'post_siege_repair','forest_regrowth','future_convergence'].map(name =>
            <Button key={name || 'all'} disabled={pending}
              title={(epoch === name ? '✓ ' : '') + (name || 'All epochs')}
              press={() => { setEpoch(name); setRecipeResults(null); }}/>)}
        </View>
      </ScrollView>}
      <Button title="Search executable recipes" disabled={pending}
        press={() => { void loadRecipes(0); }} />
      {recipeResults && <Text style={{ color:'#b1cada' }}>
        {recipeResults.matched} matching recipes · showing {recipeResults.offset + 1}–
        {recipeResults.offset + recipeResults.items.length}
      </Text>}
      {recipeResults?.items.map(recipe => <Button key={recipe.operation}
        disabled={pending} title={recipe.operation.replace(/^(produce_|expand_|direct_|complete_|worldline_|phase_|campaign_|chronicle_|epoch_)/, '').replace(/_/g, ' ')}
        press={() => selectRecipe(recipe)} />)}
      {recipeResults?.next_offset !== null && recipeResults?.next_offset !== undefined &&
        <Button title="Next recipes" disabled={pending}
          press={() => { void loadRecipes(recipeResults.next_offset ?? 0); }} />}
      {recipeResults && recipeResults.offset > 0 &&
        <Button title="Previous recipes" disabled={pending}
          press={() => { void loadRecipes(Math.max(0, recipeResults.offset - 32)); }} />}
    </View>}
    {recipeResults?.items.filter(item => item.operation === action && !!item.worldline)
      .map(item => <GameFrontierHandbookPanel key={item.operation} recipe={item} disabled={pending} />)}
    {listed.map(group => <View key={group.title} style={{ gap: 4 }}>
      <Text style={{ color: '#a8c1d6', fontWeight: '600' }}>{group.title}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{group.actions.map(name =>
        <Button key={name} title={(action === name ? '✓ ' : '') + label(name)}
          disabled={pending} press={() => choose(name)} />)}</View></View>)}
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Parameters for {label(action)}</Text>
    <TextInput accessibilityLabel="Authoring tool parameters JSON" value={parameters}
      onChangeText={setParameters} multiline autoCapitalize="none" autoCorrect={false}
      maxLength={120000} editable={!pending}
      style={{ color: '#edf4fc', backgroundColor: '#202936', borderRadius: 8,
        padding: 12, minHeight: 125, textAlignVertical: 'top', fontFamily: 'monospace' }} />
    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
      <Button title="Queue editor action" disabled={pending || !doc} press={enqueue} />
      <Button title="Undo last queued" disabled={pending || !steps.length}
        press={() => setSteps(current => current.slice(0, -1))} />
      <Button title="Preview changes" disabled={pending || !steps.length}
        press={() => { void transact(true); }} />
      <Button title="Save source changes" disabled={pending || !steps.length}
        press={() => { void transact(false); }} />
    </View>
    <Text style={{ color: '#bed1e4' }}>{steps.length} queued changes</Text>
    {steps.slice(-8).map((step, index) => <Text key={index} style={{ color: '#a5bdcc' }}>
      {steps.length - Math.min(steps.length, 8) + index + 1}. {label(step.action)}</Text>)}

    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Simulate authored 3D gameplay</Text>
    <Text style={{ color: '#a7bacf' }}>Probe a local game coordinate and available
      environment sensors. Results use real source-based equations; no native hardware
      execution is implied.</Text>
    <TextInput accessibilityLabel="Reference game position source XYZ JSON"
      value={probePosition} onChangeText={setProbePosition} editable={!pending}
      autoCapitalize="none" style={{ color: '#eef6ff', backgroundColor: '#202936', padding: 10,
        borderRadius: 7 }} />
    <TextInput accessibilityLabel="Game environment sensor observations JSON"
      value={probeSignals} onChangeText={setProbeSignals} editable={!pending}
      autoCapitalize="none" style={{ color: '#eef6ff', backgroundColor: '#202936', padding: 10,
        borderRadius: 7 }} />
    <Button title="Simulate physics, zones and RPG events" disabled={pending || !doc}
      press={() => { void probe(); }} />
    {gameplayProbe && <View style={{ gap: 4 }}>
      <Text style={{ color: '#bce4d2' }}>
        Active zones: {gameplayProbe.occupied_zones.length} · Force fields: {gameplayProbe.field_forces.length}
        · Triggered RPG pages: {gameplayProbe.environment_accepted.length}
      </Text>
      <Text style={{ color: '#a7bbd0' }}>Net force XYZ (newtons): {gameplayProbe.net_force_xyz_n.map(
        n => n.toFixed(2)).join(', ')}</Text>
      {gameplayProbe.occupied_zones.map(row => <Text key={row.zone_id}
        style={{ color: '#b9d8ea' }}>Zone {row.zone_id}: {row.action_kind}</Text>)}
      {gameplayProbe.missing_sensor_signals.length > 0 &&
        <Text style={{ color: '#efc58c' }}>Unobserved signals:
          {gameplayProbe.missing_sensor_signals.join(', ')}</Text>}
      <Text selectable style={{ color: '#829db0', fontSize: 11 }}>{gameplayProbe.receipt_sha256}</Text>
    </View>}
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Compile & export real game</Text>
    <View style={{ flexDirection: 'row', gap: 10 }}>
      <TextInput value={seed} onChangeText={setSeed} keyboardType="numeric" accessibilityLabel="Procedural world seed"
        placeholder="Seed" placeholderTextColor="#8392a7" style={{ flex: 1, color: '#f4f8fc',
          borderWidth: 1, borderColor: '#526478', padding: 8, borderRadius: 7 }} />
      <TextInput value={islands} onChangeText={setIslands} keyboardType="numeric"
        accessibilityLabel="Sky island count" placeholder="Islands" placeholderTextColor="#8392a7"
        style={{ flex: 1, color: '#f4f8fc', borderWidth: 1, borderColor: '#526478', padding: 8, borderRadius: 7 }} />
    </View>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
      <Button title="Compile & playtest world" disabled={pending || !doc}
        press={() => { void build(false); }} />
      <Button title="Save real Godot project" disabled={pending || !doc}
        press={() => { void build(true); }} />
    </View>
    {report && <View style={{ gap: 4 }}>
      <Text selectable style={{ color: '#b6e3cc' }}>Game source: {report.source_sha256}</Text>
      <Text style={{ color: '#a6bdce' }}>Waypoints: {report.world_nodes ?? '—'}
        · Travel links: {report.travel_edges ?? '—'} · Godot source files: {report.file_count ?? 0}</Text>
      {!!report.file_paths?.length && <Text selectable style={{ color: '#abc4db' }}>
        {report.file_paths.slice(0, 8).join('\n')}</Text>}
      <Text style={{ color: '#b8c4d2' }}>Native hardware run and release certification remain separate.</Text>
    </View>}
  </View>;
}
