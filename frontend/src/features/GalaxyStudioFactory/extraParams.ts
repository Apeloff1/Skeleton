// ═══════════════════════════════════════════════════════════════════════════════
// Galaxy Studio — 100 Extended Customization Parameters (v2)
// Grouped into 10 categories × 10 sliders each. Each slider uses the 0-7 scale
// where 0 = N/A (skip this aspect) and 1-7 = intensity/depth level.
// These are sent to the backend as { extra_params: { param_key: int, ... } }.
// ═══════════════════════════════════════════════════════════════════════════════

export type ExtraParam = {
  key: string;
  label: string;
  help?: string;
};

export type ExtraParamCategory = {
  id: string;
  title: string;
  icon: string; // Ionicons name
  color: string;
  params: ExtraParam[];
};

export const EXTRA_PARAM_CATEGORIES: ExtraParamCategory[] = [
  {
    id: 'combat',
    title: 'Combat',
    icon: 'flash-outline',
    color: '#EF4444',
    params: [
      { key: 'combat_lethality', label: 'Combat Lethality' },
      { key: 'weapon_variety', label: 'Weapon Variety' },
      { key: 'melee_depth', label: 'Melee Depth' },
      { key: 'ranged_precision', label: 'Ranged Precision' },
      { key: 'combo_system', label: 'Combo System' },
      { key: 'parry_timing', label: 'Parry Timing Window' },
      { key: 'block_stamina', label: 'Block Stamina' },
      { key: 'status_effects', label: 'Status Effects' },
      { key: 'combat_ai', label: 'Combat AI' },
      { key: 'finisher_variety', label: 'Finisher Variety' },
    ],
  },
  {
    id: 'magic',
    title: 'Magic & Powers',
    icon: 'sparkles-outline',
    color: '#8B5CF6',
    params: [
      { key: 'magic_schools', label: 'Magic Schools' },
      { key: 'spell_count', label: 'Spell Count' },
      { key: 'mana_regen_speed', label: 'Mana Regen Speed' },
      { key: 'elemental_variety', label: 'Elemental Variety' },
      { key: 'enchantment_depth', label: 'Enchantment Depth' },
      { key: 'summon_variety', label: 'Summon Variety' },
      { key: 'curse_potency', label: 'Curse Potency' },
      { key: 'buff_variety', label: 'Buff Variety' },
      { key: 'spell_crafting', label: 'Spell Crafting' },
      { key: 'magic_cooldowns', label: 'Magic Cooldowns' },
    ],
  },
  {
    id: 'economy',
    title: 'Economy',
    icon: 'cash-outline',
    color: '#F59E0B',
    params: [
      { key: 'currency_variety', label: 'Currency Variety' },
      { key: 'market_volatility', label: 'Market Volatility' },
      { key: 'trade_routes', label: 'Trade Routes' },
      { key: 'shop_inventory_depth', label: 'Shop Inventory Depth' },
      { key: 'pricing_dynamics', label: 'Dynamic Pricing' },
      { key: 'inflation_model', label: 'Inflation Model' },
      { key: 'black_market_depth', label: 'Black Market' },
      { key: 'taxation_system', label: 'Taxation System' },
      { key: 'bounty_variety', label: 'Bounty Variety' },
      { key: 'auction_house', label: 'Auction House' },
    ],
  },
  {
    id: 'exploration',
    title: 'Exploration',
    icon: 'compass-outline',
    color: '#22C55E',
    params: [
      { key: 'hidden_areas', label: 'Hidden Areas' },
      { key: 'secret_density', label: 'Secret Density' },
      { key: 'lore_documents', label: 'Lore Documents' },
      { key: 'landmark_variety', label: 'Landmark Variety' },
      { key: 'fast_travel_coverage', label: 'Fast Travel Coverage' },
      { key: 'treasure_abundance', label: 'Treasure Abundance' },
      { key: 'dungeon_complexity', label: 'Dungeon Complexity' },
      { key: 'cave_density', label: 'Cave Density' },
      { key: 'vista_frequency', label: 'Vista Frequency' },
      { key: 'easter_egg_density', label: 'Easter Eggs' },
    ],
  },
  {
    id: 'social',
    title: 'Social & Relationships',
    icon: 'people-outline',
    color: '#EC4899',
    params: [
      { key: 'npc_relationships', label: 'NPC Relationships' },
      { key: 'romance_depth', label: 'Romance Depth' },
      { key: 'companion_variety', label: 'Companion Variety' },
      { key: 'tribe_dynamics', label: 'Tribe Dynamics' },
      { key: 'faction_count', label: 'Faction Count' },
      { key: 'reputation_tiers', label: 'Reputation Tiers' },
      { key: 'guild_system', label: 'Guild System' },
      { key: 'mentor_system', label: 'Mentor System' },
      { key: 'rivalry_system', label: 'Rivalry System' },
      { key: 'marriage_system', label: 'Marriage System' },
    ],
  },
  {
    id: 'audio',
    title: 'Audio Detail',
    icon: 'musical-notes-outline',
    color: '#2563EB',
    params: [
      { key: 'music_variety', label: 'Music Variety' },
      { key: 'ambient_layers', label: 'Ambient Layers' },
      { key: 'voice_line_count', label: 'Voice Line Count' },
      { key: 'sfx_variety', label: 'SFX Variety' },
      { key: 'adaptive_music', label: 'Adaptive Music' },
      { key: 'spatial_audio', label: 'Spatial Audio' },
      { key: 'footstep_variety', label: 'Footstep Variety' },
      { key: 'combat_sfx_layers', label: 'Combat SFX Layers' },
      { key: 'dialogue_emotion', label: 'Dialogue Emotion' },
      { key: 'soundscape_richness', label: 'Soundscape Richness' },
    ],
  },
  {
    id: 'visual_fx',
    title: 'Visual FX',
    icon: 'color-palette-outline',
    color: '#A78BFA',
    params: [
      { key: 'color_palette_richness', label: 'Color Palette' },
      { key: 'texture_resolution', label: 'Texture Resolution' },
      { key: 'shader_complexity', label: 'Shader Complexity' },
      { key: 'shadow_quality', label: 'Shadow Quality' },
      { key: 'reflection_quality', label: 'Reflection Quality' },
      { key: 'volumetric_effects', label: 'Volumetric FX' },
      { key: 'motion_blur', label: 'Motion Blur' },
      { key: 'depth_of_field', label: 'Depth of Field' },
      { key: 'bloom_intensity', label: 'Bloom Intensity' },
      { key: 'chromatic_aberration', label: 'Chromatic Aberration' },
    ],
  },
  {
    id: 'narrative',
    title: 'Narrative',
    icon: 'book-outline',
    color: '#F97316',
    params: [
      { key: 'main_quest_length', label: 'Main Quest Length' },
      { key: 'side_quest_count', label: 'Side Quest Count' },
      { key: 'dialog_tree_depth', label: 'Dialog Tree Depth' },
      { key: 'moral_choice_weight', label: 'Moral Choice Weight' },
      { key: 'consequence_propagation', label: 'Consequence Chain' },
      { key: 'lore_layers', label: 'Lore Layers' },
      { key: 'prophecy_density', label: 'Prophecy Density' },
      { key: 'flashback_usage', label: 'Flashback Usage' },
      { key: 'plot_twist_frequency', label: 'Plot Twist Frequency' },
      { key: 'epilogue_variety', label: 'Epilogue Variety' },
    ],
  },
  {
    id: 'ai_behavior',
    title: 'AI & Behavior',
    icon: 'hardware-chip-outline',
    color: '#3B82F6',
    params: [
      { key: 'ai_learning_rate', label: 'AI Learning Rate' },
      { key: 'enemy_adaptability', label: 'Enemy Adaptability' },
      { key: 'companion_intelligence', label: 'Companion Intel' },
      { key: 'npc_daily_schedule', label: 'NPC Schedule' },
      { key: 'herd_behavior', label: 'Herd Behavior' },
      { key: 'predator_prey_chain', label: 'Predator-Prey Chain' },
      { key: 'boss_pattern_variety', label: 'Boss Patterns' },
      { key: 'ambush_frequency', label: 'Ambush Frequency' },
      { key: 'patrol_complexity', label: 'Patrol Complexity' },
      { key: 'ally_tactics', label: 'Ally Tactics' },
    ],
  },
  {
    id: 'accessibility',
    title: 'Accessibility & QoL',
    icon: 'accessibility-outline',
    color: '#60A5FA',
    params: [
      { key: 'colorblind_modes', label: 'Colorblind Modes' },
      { key: 'subtitle_customization', label: 'Subtitle Options' },
      { key: 'control_remapping', label: 'Control Remapping' },
      { key: 'difficulty_granularity', label: 'Difficulty Granularity' },
      { key: 'tutorial_depth', label: 'Tutorial Depth' },
      { key: 'objective_clarity', label: 'Objective Clarity' },
      { key: 'autosave_frequency', label: 'Autosave Frequency' },
      { key: 'pause_granularity', label: 'Pause Granularity' },
      { key: 'text_scale_options', label: 'Text Scale Options' },
      { key: 'motion_sickness_options', label: 'Motion Sickness Options' },
    ],
  },
  // ═══════════════════════════════════════════════════════════════════════════════
  // AAA Delivery — 30 sliders that specifically drive massive, AAA-quality output
  // ═══════════════════════════════════════════════════════════════════════════════
  {
    id: 'storyline',
    title: 'Storyline & Narrative',
    icon: 'book-outline',
    color: '#F59E0B',
    params: [
      { key: 'main_plot_arcs', label: 'Main Plot Arcs' },
      { key: 'side_quest_density', label: 'Side Quest Density' },
      { key: 'character_backstories', label: 'Character Backstories' },
      { key: 'plot_twists', label: 'Plot Twists' },
      { key: 'multiple_endings', label: 'Multiple Endings' },
      { key: 'branching_paths', label: 'Branching Paths' },
      { key: 'lore_depth', label: 'Lore / World Bible Depth' },
      { key: 'companion_arcs', label: 'Companion Story Arcs' },
      { key: 'moral_choices', label: 'Moral Choice Weight' },
      { key: 'emotional_beats', label: 'Emotional Beats' },
    ],
  },
  {
    id: 'cinematic',
    title: 'Cinematic & Presentation',
    icon: 'film-outline',
    color: '#A855F7',
    params: [
      { key: 'cutscene_density', label: 'Cutscene Density' },
      { key: 'cinematic_camera', label: 'Cinematic Camera' },
      { key: 'mocap_fidelity', label: 'Motion Capture Fidelity' },
      { key: 'voice_acting_density', label: 'Voice Acting Density' },
      { key: 'lipsync_quality', label: 'Lip-Sync Quality' },
      { key: 'orchestral_score', label: 'Orchestral Score' },
      { key: 'dynamic_music', label: 'Dynamic Music Layers' },
      { key: 'ambient_sound_design', label: 'Ambient Sound Design' },
      { key: 'environmental_storytelling', label: 'Environmental Storytelling' },
      { key: 'trailer_quality_shots', label: 'Trailer-Quality Set-Pieces' },
    ],
  },
  {
    id: 'live_service',
    title: 'Live Service & Monetization',
    icon: 'server-outline',
    color: '#3B82F6',
    params: [
      { key: 'netcode_tier', label: 'Netcode Tier (lag comp)' },
      { key: 'anticheat_level', label: 'Anti-Cheat Level' },
      { key: 'matchmaking_quality', label: 'Matchmaking Quality' },
      { key: 'leaderboard_depth', label: 'Leaderboard Depth' },
      { key: 'season_pass_depth', label: 'Season Pass Depth' },
      { key: 'dlc_pipeline', label: 'DLC Pipeline' },
      { key: 'microtx_restraint', label: 'Microtransaction Restraint' },
      { key: 'live_event_frequency', label: 'Live Event Frequency' },
      { key: 'clan_guild_systems', label: 'Clan / Guild Systems' },
      { key: 'cross_play', label: 'Cross-Play / Cross-Save' },
    ],
  },
];

// Build a flat default map { param_key: 7 } for all 100 params
export const DEFAULT_EXTRA_PARAMS: Record<string, number> = (() => {
  const out: Record<string, number> = {};
  for (const cat of EXTRA_PARAM_CATEGORIES) {
    for (const p of cat.params) {
      out[p.key] = 7;
    }
  }
  return out;
})();

export const TOTAL_EXTRA_PARAMS = Object.keys(DEFAULT_EXTRA_PARAMS).length; // 100
