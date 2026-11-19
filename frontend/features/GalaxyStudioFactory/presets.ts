// ═══════════════════════════════════════════════════════════════════════════════
// Galaxy Studio — Quick Start Templates
// One-tap configuration presets. Each template pre-fills:
//   - title + genre + description
//   - all 29 classic sliders (graphicsEra, npcDensity, ... moddingSupport)
//   - all 100 extended params (extraParams map)
// Users can still tweak anything after applying.
// ═══════════════════════════════════════════════════════════════════════════════

import { DEFAULT_EXTRA_PARAMS } from './extraParams';

export type GameTemplate = {
  id: string;
  name: string;
  tagline: string;
  icon: string;
  color: string;
  title: string;
  genre: string;          // matches backend genre ids: rpg, shooter, platformer, etc.
  subgenre?: string;
  description: string;
  gameVision: string;
  systemArch: string;
  worldLaws: string;
  agentInstructions: string;
  scaleCommand: string;
  complexity: number;     // 1-10
  ageTarget: string;      // 'EC' | 'E' | 'E10' | 'T' | 'M' | 'A'
  // Core 29 sliders (0-7)
  classic: {
    graphicsEra: number; npcDensity: number; soundEra: number; worldSize: number;
    physicsRealism: number; aiComplexity: number; lightingEngine: number; particleEffects: number;
    destructionPhysics: number; narrativeBranching: number; economyComplexity: number; multiplayerMax: number;
    weatherSystems: number; dayNightCycle: number; animationFluidity: number; postProcessing: number;
    foliageDensity: number; waterSimulation: number; uiMinimalism: number; lootVariety: number;
    craftingDepth: number; dialogDepth: number; stealthMechanics: number; vehicleSimulation: number;
    biomeDiversity: number; factionReputation: number; skillSystem: number; goreSystem: number;
    moddingSupport: number;
  };
  // Flat { key: 0-7 } override map for extra 100 params
  extraOverrides?: Record<string, number>;
};

// Helper: fill classic slider bundle uniformly
const c = (v: number) => ({
  graphicsEra: v, npcDensity: v, soundEra: v, worldSize: v,
  physicsRealism: v, aiComplexity: v, lightingEngine: v, particleEffects: v,
  destructionPhysics: v, narrativeBranching: v, economyComplexity: v, multiplayerMax: v,
  weatherSystems: v, dayNightCycle: v, animationFluidity: v, postProcessing: v,
  foliageDensity: v, waterSimulation: v, uiMinimalism: v, lootVariety: v,
  craftingDepth: v, dialogDepth: v, stealthMechanics: v, vehicleSimulation: v,
  biomeDiversity: v, factionReputation: v, skillSystem: v, goreSystem: v,
  moddingSupport: v,
});

export const GAME_TEMPLATES: GameTemplate[] = [
  {
    id: 'aaa_open_world',
    name: 'AAA Open World',
    tagline: 'Witcher / GTA scale, max everything',
    icon: 'globe-outline',
    color: '#8B5CF6',
    title: 'Eternal Expanse',
    genre: 'rpg',
    description: 'A sprawling open-world AAA action-RPG with branching narrative and systemic emergent gameplay.',
    gameVision: 'Players harvest chronitons across a shattered multiverse, shaping reality with every choice.',
    systemArch: 'Voxel destruction + adaptive AI director + 5-layer weather + physically-based rendering.',
    worldLaws: '24-hour day-night with persistent consequences. NPCs age, factions evolve, weather erodes terrain.',
    agentInstructions: 'All 1.4M agents maximize polish, variety, and branching. No placeholders.',
    scaleCommand: '500,000 assets, 25 GB, 150 hours of content',
    complexity: 10,
    ageTarget: 'M',
    classic: { ...c(7) },
    extraOverrides: { ...DEFAULT_EXTRA_PARAMS },
  },
  {
    id: 'soulslike',
    name: 'Soulslike Dark Fantasy',
    tagline: 'Punishing combat, cryptic lore',
    icon: 'skull-outline',
    color: '#EF4444',
    title: 'Ashen Veil',
    genre: 'action',
    description: 'A methodical, unforgiving dark-fantasy soulslike with stamina-based combat and fragmented lore.',
    gameVision: 'Die, learn, rise. Every enemy is a puzzle. Every item tells a story.',
    systemArch: 'Weighted stamina combat, parry/riposte, poise stagger, bonfire checkpoints, invasion PvP.',
    worldLaws: 'Interconnected zones, no quest markers. Lore is environmental and item-driven.',
    agentInstructions: 'Prioritize animation weight, enemy telegraphs, boss arenas, and item flavor text.',
    scaleCommand: '40 interconnected zones, 60 bosses, 500 weapons',
    complexity: 7,
    ageTarget: 'M',
    classic: {
      ...c(6),
      graphicsEra: 7, animationFluidity: 7, aiComplexity: 7, narrativeBranching: 4,
      economyComplexity: 3, multiplayerMax: 4, lootVariety: 7, craftingDepth: 2,
      dialogDepth: 3, stealthMechanics: 3, vehicleSimulation: 0, biomeDiversity: 5,
      factionReputation: 5, skillSystem: 6, goreSystem: 7, moddingSupport: 3,
    },
    extraOverrides: {
      ...DEFAULT_EXTRA_PARAMS,
      combat_lethality: 7, parry_timing: 7, status_effects: 7, boss_pattern_variety: 7,
      finisher_variety: 7, main_quest_length: 6, lore_layers: 7, plot_twist_frequency: 5,
      romance_depth: 0, marriage_system: 0, guild_system: 2, auction_house: 0,
      tutorial_depth: 2, objective_clarity: 2,
    },
  },
  {
    id: 'cozy_farm',
    name: 'Cozy Farm Sim',
    tagline: 'Stardew vibes, relaxed pacing',
    icon: 'leaf-outline',
    color: '#22C55E',
    title: 'Hearthmoor Valley',
    genre: 'simulation',
    description: 'A warm, cozy farming sim with seasonal festivals, meaningful NPC relationships, and no combat pressure.',
    gameVision: 'Slow living. Plant crops, build friendships, decorate your farm.',
    systemArch: 'Seasonal crop cycles, animal husbandry, cooking, fishing, NPC relationship graphs.',
    worldLaws: 'No combat. NPCs have routines, preferences, birthdays. Festivals seasonally.',
    agentInstructions: 'Focus on warmth, pixel art charm, NPC personality, and no stress mechanics.',
    scaleCommand: '30 villagers, 100 recipes, 200 decor items',
    complexity: 5,
    ageTarget: 'E',
    classic: {
      ...c(4),
      graphicsEra: 3, npcDensity: 4, soundEra: 5, worldSize: 4,
      physicsRealism: 2, aiComplexity: 3, particleEffects: 3, destructionPhysics: 0,
      narrativeBranching: 4, economyComplexity: 5, multiplayerMax: 3,
      animationFluidity: 5, foliageDensity: 7, waterSimulation: 4,
      lootVariety: 3, craftingDepth: 6, dialogDepth: 6, stealthMechanics: 0,
      vehicleSimulation: 0, biomeDiversity: 4, skillSystem: 3, goreSystem: 0,
    },
    extraOverrides: {
      ...DEFAULT_EXTRA_PARAMS,
      combat_lethality: 0, weapon_variety: 0, melee_depth: 0, ranged_precision: 0,
      combo_system: 0, parry_timing: 0, block_stamina: 0, finisher_variety: 0,
      magic_schools: 0, spell_count: 0, curse_potency: 0,
      romance_depth: 7, companion_variety: 6, marriage_system: 7, mentor_system: 5,
      npc_relationships: 7, music_variety: 7, ambient_layers: 7,
      bounty_variety: 0, black_market_depth: 0, gore_system: 0 as any,
    },
  },
  {
    id: 'retro_arcade',
    name: 'Retro Arcade Shooter',
    tagline: '16-bit, pure gameplay',
    icon: 'game-controller-outline',
    color: '#F59E0B',
    title: 'Neon Pulse',
    genre: 'shooter',
    subgenre: 'arcade',
    description: 'A pixel-art, high-score-chasing arcade shooter with CRT effects and synthwave soundtrack.',
    gameVision: '60fps twin-stick mayhem. Simple rules, deep mastery.',
    systemArch: 'Bullet-hell patterns, wave spawning, power-up chains, combo multipliers.',
    worldLaws: 'Score is everything. Perma-death per run. Leaderboard-driven.',
    agentInstructions: 'Pixel-perfect collision, 60fps, no cutscenes. Juice everything.',
    scaleCommand: '50 enemy types, 20 bosses, 10 stages',
    complexity: 3,
    ageTarget: 'T',
    classic: {
      ...c(3),
      graphicsEra: 1, soundEra: 2, npcDensity: 2, worldSize: 2,
      physicsRealism: 2, aiComplexity: 3, particleEffects: 6, postProcessing: 5,
      narrativeBranching: 1, economyComplexity: 1, multiplayerMax: 2,
      weatherSystems: 0, dayNightCycle: 0, animationFluidity: 4,
      lootVariety: 3, craftingDepth: 0, dialogDepth: 1, stealthMechanics: 0,
      biomeDiversity: 2, skillSystem: 2, goreSystem: 2,
    },
    extraOverrides: {
      ...DEFAULT_EXTRA_PARAMS,
      magic_schools: 0, romance_depth: 0, companion_variety: 0, marriage_system: 0,
      dialog_tree_depth: 1, side_quest_count: 0, moral_choice_weight: 0,
      music_variety: 6, ambient_layers: 3, sfx_variety: 7,
      trade_routes: 0, auction_house: 0, inflation_model: 0,
      subtitle_customization: 3, difficulty_granularity: 6, tutorial_depth: 2,
    },
  },
  {
    id: 'horror_survival',
    name: 'Horror Survival',
    tagline: 'Tension, scarcity, dread',
    icon: 'warning-outline',
    color: '#DC2626',
    title: 'Black Hollow',
    genre: 'horror',
    description: 'A first-person survival horror with limited resources, psychological dread, and permadeath.',
    gameVision: 'Every bullet counts. Every shadow might be a friend. Or not.',
    systemArch: 'Limited inventory, sanity meter, flashlight battery scarcity, dynamic dread music.',
    worldLaws: 'Monsters learn. Resources respawn rarely. Save points are costly.',
    agentInstructions: 'Maximize atmosphere, sound design, lighting. Minimize UI clutter.',
    scaleCommand: '12 hours, 15 monsters, 60 locations',
    complexity: 7,
    ageTarget: 'M',
    classic: {
      ...c(5),
      graphicsEra: 7, soundEra: 7, lightingEngine: 7, postProcessing: 7,
      aiComplexity: 7, narrativeBranching: 6, multiplayerMax: 1,
      animationFluidity: 6, foliageDensity: 5, weatherSystems: 5,
      lootVariety: 4, craftingDepth: 5, dialogDepth: 4, stealthMechanics: 7,
      goreSystem: 6, moddingSupport: 2,
    },
    extraOverrides: {
      ...DEFAULT_EXTRA_PARAMS,
      ambient_layers: 7, spatial_audio: 7, dialogue_emotion: 7, soundscape_richness: 7,
      shadow_quality: 7, volumetric_effects: 7, bloom_intensity: 3,
      ambush_frequency: 7, enemy_adaptability: 7, patrol_complexity: 6,
      hidden_areas: 7, secret_density: 6, lore_documents: 7,
      romance_depth: 0, marriage_system: 0, auction_house: 0,
      motion_sickness_options: 7, colorblind_modes: 4, subtitle_customization: 6,
    },
  },
  {
    id: 'metroidvania',
    name: 'Metroidvania',
    tagline: 'Interconnected, ability-gated',
    icon: 'map-outline',
    color: '#2563EB',
    title: 'Hollow Spires',
    genre: 'platformer',
    subgenre: 'metroidvania',
    description: 'A hand-drawn metroidvania with tight platforming, ability unlocks, and interconnected world.',
    gameVision: 'Explore, gain power, revisit old areas with new eyes.',
    systemArch: 'Ability-gated world, dash/wall-climb/double-jump progression, hidden upgrade nodes.',
    worldLaws: 'No fast travel until mid-game. Backtracking rewards exploration.',
    agentInstructions: 'Every ability unlock changes 10+ old areas. Boss fights test all abilities.',
    scaleCommand: '400 rooms, 18 bosses, 35 abilities',
    complexity: 7,
    ageTarget: 'T',
    classic: {
      ...c(5),
      graphicsEra: 4, animationFluidity: 7, aiComplexity: 5,
      narrativeBranching: 3, economyComplexity: 3, multiplayerMax: 1,
      foliageDensity: 4, waterSimulation: 3, uiMinimalism: 6,
      lootVariety: 5, craftingDepth: 3, dialogDepth: 3,
      biomeDiversity: 7, skillSystem: 6, goreSystem: 2, moddingSupport: 4,
    },
    extraOverrides: {
      ...DEFAULT_EXTRA_PARAMS,
      hidden_areas: 7, secret_density: 7, landmark_variety: 7, easter_egg_density: 6,
      combat_lethality: 5, boss_pattern_variety: 7, combo_system: 5,
      magic_schools: 3, spell_count: 4,
      marriage_system: 0, auction_house: 0, taxation_system: 0,
      main_quest_length: 5, side_quest_count: 4, lore_layers: 6,
    },
  },
  {
    id: 'random',
    name: 'Randomize Everything',
    tagline: 'Surprise me',
    icon: 'dice-outline',
    color: '#EC4899',
    title: 'Chaos Engine',
    genre: '',  // Signals random genre pick on apply
    description: 'Completely randomized configuration. Every slider, every param gets a surprise value.',
    gameVision: 'Let the AI decide.',
    systemArch: '',
    worldLaws: '',
    agentInstructions: 'Maximize variety and experimentation.',
    scaleCommand: '',
    complexity: 5,
    ageTarget: 'T',
    classic: { ...c(4) },  // Gets overridden on apply
    extraOverrides: {},
  },
];

// Utility: generate a randomized classic + extra bundle at apply-time
export function randomizeConfig() {
  const r = () => Math.floor(Math.random() * 8); // 0-7
  const classic = {
    graphicsEra: r(), npcDensity: r(), soundEra: r(), worldSize: r(),
    physicsRealism: r(), aiComplexity: r(), lightingEngine: r(), particleEffects: r(),
    destructionPhysics: r(), narrativeBranching: r(), economyComplexity: r(), multiplayerMax: r(),
    weatherSystems: r(), dayNightCycle: r(), animationFluidity: r(), postProcessing: r(),
    foliageDensity: r(), waterSimulation: r(), uiMinimalism: r(), lootVariety: r(),
    craftingDepth: r(), dialogDepth: r(), stealthMechanics: r(), vehicleSimulation: r(),
    biomeDiversity: r(), factionReputation: r(), skillSystem: r(), goreSystem: r(),
    moddingSupport: r(),
  };
  const extra: Record<string, number> = {};
  for (const k of Object.keys(DEFAULT_EXTRA_PARAMS)) extra[k] = r();
  return { classic, extra };
}
