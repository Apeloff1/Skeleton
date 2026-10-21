/** Interactive 50-operation Forge Studio editor over live authenticated project revisions. */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  buildForge, copyForgeTiles, editForge, exportForge, inspectForge,
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
  const listed = useMemo(() => GROUPS.map(group => ({
    ...group, actions: group.actions.filter(item => (!doc || doc.action_catalog.includes(item))
      && item.includes(search.trim().toLowerCase())),
  })).filter(group => group.actions.length), [doc, search]);
  const choose = (name: string) => {
    setAction(name);
    const args = { ...(hundredActionDefaults(name, selectedLayer) || newActionDefaults(name, selectedLayer) || SAMPLE[name] || {}) };
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
    <Text style={{ color: '#a7bacf' }}>500 executable tools for maps, characters, quests, environmental events, native physics and soundtracks.
      Every saved edit changes the project source and is consumed by the real game compiler.</Text>
    {!doc ? <ActivityIndicator color="#8bd5e8" /> : <View>
      <Text style={{ color: '#bdcddd' }}>Revision {doc.expected_version} · {doc.layers.length} layers
        · {doc.placed_actor_count} actors · {doc.quest_count} quests · {doc.music_cue_count} audio cues</Text>
      <Text selectable style={{ color: '#829db0', fontSize: 11 }}>{doc.source_sha256}</Text>
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
    <TextInput value={search} onChangeText={setSearch} accessibilityLabel="Search 500 game editor tools"
      placeholder="Search tiles, NPCs, quests, events…" placeholderTextColor="#75869a"
      style={{ color: '#f0f5fb', borderWidth: 1, borderColor: '#526478', borderRadius: 7, padding: 10 }} />
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
