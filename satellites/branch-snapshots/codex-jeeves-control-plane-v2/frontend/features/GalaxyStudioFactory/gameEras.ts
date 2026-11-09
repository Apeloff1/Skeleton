// Galaxy Studio — Game Eras
// A single slider-like horizontal selector that sets the overall technological
// and aesthetic tone for asset generation. Spans 10 eras from 1972 to future.

export type GameEra = {
  id: string;
  label: string;
  year: string;
  tagline: string;
  icon: string;
  color: string;
  // Recommended defaults that applyEra() merges into the 29 classic sliders.
  classicOverrides: Record<string, number>;
  // Recommended defaults that applyEra() merges into the 100 extra params.
  extraOverrides?: Record<string, number>;
};

// Helpers for building common slider maps
const LOW_GFX = { graphicsEra: 1, animationFluidity: 2, lightingEngine: 1, particleEffects: 1, postProcessing: 0, foliageDensity: 0, waterSimulation: 0 };
const MID_GFX = { graphicsEra: 4, animationFluidity: 4, lightingEngine: 4, particleEffects: 4, postProcessing: 3, foliageDensity: 3, waterSimulation: 3 };
const HIGH_GFX = { graphicsEra: 7, animationFluidity: 7, lightingEngine: 7, particleEffects: 7, postProcessing: 7, foliageDensity: 7, waterSimulation: 7 };
const NEXT_GFX = { graphicsEra: 7, animationFluidity: 7, lightingEngine: 7, particleEffects: 7, postProcessing: 7, foliageDensity: 7, waterSimulation: 7, destructionPhysics: 7 };

export const GAME_ERAS: GameEra[] = [
  {
    id: 'pong_1972',
    label: 'Pong Era',
    year: '1972',
    tagline: 'Monochrome, paddle-simple',
    icon: 'square-outline',
    color: '#6B7280',
    classicOverrides: { ...LOW_GFX, soundEra: 1, npcDensity: 0, worldSize: 1, physicsRealism: 1, narrativeBranching: 0, dialogDepth: 0, uiMinimalism: 7, goreSystem: 0 },
    extraOverrides: { music_variety: 0, voice_line_count: 0, main_quest_length: 0, side_quest_count: 0, color_palette_richness: 1, texture_resolution: 0 },
  },
  {
    id: 'atari_1977',
    label: 'Atari 2600',
    year: '1977',
    tagline: '8-color pixel art, beeps',
    icon: 'grid-outline',
    color: '#F59E0B',
    classicOverrides: { ...LOW_GFX, graphicsEra: 1, soundEra: 1, npcDensity: 1, worldSize: 1, animationFluidity: 1, uiMinimalism: 6 },
    extraOverrides: { music_variety: 1, sfx_variety: 2, color_palette_richness: 2, texture_resolution: 1, shader_complexity: 0 },
  },
  {
    id: 'nes_1985',
    label: 'NES Era',
    year: '1985',
    tagline: '8-bit, chiptune, scrolling',
    icon: 'game-controller-outline',
    color: '#EF4444',
    classicOverrides: { graphicsEra: 2, soundEra: 2, npcDensity: 2, worldSize: 2, physicsRealism: 2, animationFluidity: 2, lightingEngine: 1, particleEffects: 2, postProcessing: 0, foliageDensity: 1, waterSimulation: 1, uiMinimalism: 5, lootVariety: 3, narrativeBranching: 2, dialogDepth: 2 },
    extraOverrides: { music_variety: 4, sfx_variety: 3, color_palette_richness: 3, texture_resolution: 1, main_quest_length: 3, side_quest_count: 2 },
  },
  {
    id: 'snes_1990',
    label: 'SNES / Genesis',
    year: '1990',
    tagline: '16-bit, Mode-7, CD audio',
    icon: 'color-palette-outline',
    color: '#8B5CF6',
    classicOverrides: { graphicsEra: 3, soundEra: 3, npcDensity: 3, worldSize: 3, physicsRealism: 2, animationFluidity: 3, lightingEngine: 2, particleEffects: 3, foliageDensity: 2, waterSimulation: 2, uiMinimalism: 5, lootVariety: 4, narrativeBranching: 3, dialogDepth: 4, skillSystem: 3 },
    extraOverrides: { music_variety: 6, sfx_variety: 5, color_palette_richness: 5, texture_resolution: 2, main_quest_length: 5, side_quest_count: 4, magic_schools: 4 },
  },
  {
    id: 'ps1_1995',
    label: 'PS1 / N64',
    year: '1995',
    tagline: 'Early 3D, low-poly, FMV',
    icon: 'cube-outline',
    color: '#2563EB',
    classicOverrides: { graphicsEra: 4, soundEra: 4, npcDensity: 3, worldSize: 4, physicsRealism: 3, animationFluidity: 3, lightingEngine: 3, particleEffects: 3, postProcessing: 1, foliageDensity: 3, waterSimulation: 3, uiMinimalism: 4, lootVariety: 4, vehicleSimulation: 4, skillSystem: 4 },
    extraOverrides: { music_variety: 5, voice_line_count: 3, texture_resolution: 3, shader_complexity: 2, main_quest_length: 6, dialog_tree_depth: 4 },
  },
  {
    id: 'ps2_2000',
    label: 'PS2 / GameCube',
    year: '2000',
    tagline: '3D mainstream, online arrives',
    icon: 'git-network-outline',
    color: '#22C55E',
    classicOverrides: { ...MID_GFX, graphicsEra: 5, soundEra: 5, npcDensity: 4, worldSize: 5, physicsRealism: 4, multiplayerMax: 4, lootVariety: 5, craftingDepth: 4, dialogDepth: 5, stealthMechanics: 4, biomeDiversity: 4, skillSystem: 5 },
    extraOverrides: { music_variety: 6, voice_line_count: 5, texture_resolution: 4, shader_complexity: 4, main_quest_length: 6, side_quest_count: 5, companion_variety: 5 },
  },
  {
    id: 'xbox360_2005',
    label: 'Xbox 360 / PS3',
    year: '2005',
    tagline: 'HD shaders, HDR, live online',
    icon: 'flash-outline',
    color: '#3B82F6',
    classicOverrides: { graphicsEra: 6, soundEra: 6, npcDensity: 5, worldSize: 6, physicsRealism: 5, animationFluidity: 6, lightingEngine: 6, particleEffects: 6, postProcessing: 5, foliageDensity: 5, waterSimulation: 5, uiMinimalism: 4, lootVariety: 6, craftingDepth: 5, dialogDepth: 6, stealthMechanics: 5, vehicleSimulation: 5, biomeDiversity: 5, factionReputation: 5, skillSystem: 6, multiplayerMax: 5 },
    extraOverrides: { music_variety: 6, voice_line_count: 6, texture_resolution: 5, shader_complexity: 6, main_quest_length: 6, side_quest_count: 6, boss_pattern_variety: 6, combo_system: 6 },
  },
  {
    id: 'ps4_2013',
    label: 'PS4 / Xbox One',
    year: '2013',
    tagline: 'Modern AAA, open world standard',
    icon: 'planet-outline',
    color: '#A855F7',
    classicOverrides: { ...HIGH_GFX, graphicsEra: 7, soundEra: 7, npcDensity: 6, worldSize: 7, physicsRealism: 6, destructionPhysics: 5, multiplayerMax: 6, weatherSystems: 6, dayNightCycle: 6, lootVariety: 6, craftingDepth: 6, dialogDepth: 6, stealthMechanics: 6, vehicleSimulation: 6, biomeDiversity: 6, factionReputation: 6, skillSystem: 7, narrativeBranching: 6 },
    extraOverrides: { music_variety: 7, voice_line_count: 7, texture_resolution: 7, shader_complexity: 7, shadow_quality: 7, reflection_quality: 6, main_quest_length: 7, side_quest_count: 7, lore_layers: 7 },
  },
  {
    id: 'ps5_2020',
    label: 'PS5 / Series X',
    year: '2020',
    tagline: 'Ray tracing, 4K, SSD streaming',
    icon: 'sparkles-outline',
    color: '#EC4899',
    classicOverrides: { ...NEXT_GFX, soundEra: 7, npcDensity: 7, worldSize: 7, physicsRealism: 7, multiplayerMax: 7, weatherSystems: 7, dayNightCycle: 7, lootVariety: 7, craftingDepth: 7, dialogDepth: 7, stealthMechanics: 7, vehicleSimulation: 7, biomeDiversity: 7, factionReputation: 7, skillSystem: 7, narrativeBranching: 7, moddingSupport: 5 },
    extraOverrides: { music_variety: 7, voice_line_count: 7, texture_resolution: 7, shader_complexity: 7, shadow_quality: 7, reflection_quality: 7, volumetric_effects: 7, spatial_audio: 7, ai_learning_rate: 7, enemy_adaptability: 7 },
  },
  {
    id: 'singularity',
    label: 'Singularity',
    year: '2030+',
    tagline: 'AI-generated, photoreal, infinite',
    icon: 'infinite-outline',
    color: '#F97316',
    classicOverrides: { ...NEXT_GFX, soundEra: 7, npcDensity: 7, worldSize: 7, physicsRealism: 7, aiComplexity: 7, multiplayerMax: 7, weatherSystems: 7, dayNightCycle: 7, lootVariety: 7, craftingDepth: 7, dialogDepth: 7, stealthMechanics: 7, vehicleSimulation: 7, biomeDiversity: 7, factionReputation: 7, skillSystem: 7, narrativeBranching: 7, moddingSupport: 7, goreSystem: 7 },
    extraOverrides: {
      // All 100 params max out for singularity era
      music_variety: 7, ambient_layers: 7, voice_line_count: 7, sfx_variety: 7, adaptive_music: 7, spatial_audio: 7,
      color_palette_richness: 7, texture_resolution: 7, shader_complexity: 7, shadow_quality: 7, reflection_quality: 7, volumetric_effects: 7,
      ai_learning_rate: 7, enemy_adaptability: 7, companion_intelligence: 7, npc_daily_schedule: 7, boss_pattern_variety: 7,
      main_quest_length: 7, side_quest_count: 7, dialog_tree_depth: 7, lore_layers: 7, consequence_propagation: 7, moral_choice_weight: 7,
      combat_lethality: 7, weapon_variety: 7, combo_system: 7, status_effects: 7,
      magic_schools: 7, spell_count: 7, elemental_variety: 7, spell_crafting: 7,
    },
  },
];

// Pick a reasonable default
export const DEFAULT_ERA_ID = 'ps5_2020';
