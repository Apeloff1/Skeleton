/**
 * QuestionnaireMatrices — every part of the Galaxy Studio build questionnaire,
 * expressed as a "phase × axes" tensor. Each matrix is comparable in scale
 * to NarrativePhaseSliders (40+ phases × 5+ axes).
 *
 * Goal: extreme expressivity in the questionnaire without exploding the
 * GalaxyStudioFactoryModal file. The backend agents receive one structured
 * JSON dict per matrix and can ground every phase against the RAG fabric.
 */
import { MatrixConfig } from './MatrixSliders';

// ─── Shared axes ─────────────────────────────────────────────────────
// 2026 SOTA spec:
//   • All sliders start at 0 (default = 0)
//   • Standard max = 100
//   • Output-impacting axes (count / secrets / quests / easter eggs /
//     mutation / sample-amplifying agent dials) reach 1000
const FIVE_AXES = [
  { id: 'count',      label: 'count',      min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'complexity', label: 'complexity', min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'intricacy',  label: 'intricacy',  min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'secrets',    label: 'secrets',    min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'diversity',  label: 'diversity',  min: 0, max: 100,  default: 0 },
];

const PROD_AXES = [
  { id: 'depth',       label: 'depth',       min: 0, max: 100, default: 0 },
  { id: 'fidelity',    label: 'fidelity',    min: 0, max: 100, default: 0 },
  { id: 'variety',     label: 'variety',     min: 0, max: 100, default: 0 },
  { id: 'innovation',  label: 'innovation',  min: 0, max: 100, default: 0 },
  { id: 'budget',      label: 'budget',      min: 0, max: 100, default: 0 },
];

const TECH_AXES = [
  { id: 'priority',    label: 'priority',    min: 0, max: 100, default: 0 },
  { id: 'optimisation',label: 'optimisation',min: 0, max: 100, default: 0 },
  { id: 'scalability', label: 'scalability', min: 0, max: 100, default: 0 },
  { id: 'reliability', label: 'reliability', min: 0, max: 100, default: 0 },
  { id: 'flexibility', label: 'flexibility', min: 0, max: 100, default: 0 },
];

// ML axes: sample/context/consistency dials are directly output-volume
// amplifying — they belong on the 1000 scale.
const ML_AXES = [
  { id: 'weight',          label: 'weight',          min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'temperature',     label: 'temperature',     min: 0, max: 200,  default: 0, step: 1 }, // /100 on agent side
  { id: 'samples',         label: 'samples',         min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'context_depth',   label: 'context depth',   min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'self_consistency',label: 'self-consistency',min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
];

const MONEY_AXES = [
  { id: 'aggressiveness', label: 'aggressiveness', min: 0, max: 100, default: 0 },
  { id: 'fairness',       label: 'fairness',       min: 0, max: 100, default: 0 },
  { id: 'frequency',      label: 'frequency',      min: 0, max: 100, default: 0 },
  { id: 'reward_rate',    label: 'reward rate',    min: 0, max: 100, default: 0 },
  { id: 'whale_lean',     label: 'whale lean',     min: 0, max: 100, default: 0 },
];

const QA_AXES = [
  { id: 'coverage',     label: 'coverage',     min: 0, max: 100, default: 0 },
  { id: 'severity',     label: 'severity',     min: 0, max: 100, default: 0 },
  { id: 'frequency',    label: 'frequency',    min: 0, max: 100, default: 0 },
  { id: 'automation',   label: 'automation',   min: 0, max: 100, default: 0 },
  { id: 'humanreview',  label: 'human review', min: 0, max: 100, default: 0 },
];

// ─── 1. MECHANICS MATRIX (40 phases) ─────────────────────────────────
export const MECHANICS_MATRIX: MatrixConfig = {
  id: 'mechanics',
  title: 'Mechanics Matrix',
  icon: 'game-controller',
  accent: '#2563EB',
  hint: 'Combat → Magic → Crafting → Social. Every mechanic gets 5 dials.',
  axes: FIVE_AXES,
  phases: [
    // Combat & action
    { id: 'melee',          label: 'Melee Combat',     emoji: '⚔️',  group: 'Combat & Action' },
    { id: 'ranged',         label: 'Ranged Combat',    emoji: '🏹',  group: 'Combat & Action' },
    { id: 'magic',          label: 'Magic',            emoji: '🔮',  group: 'Combat & Action' },
    { id: 'tactical',       label: 'Tactical Combat',  emoji: '♟️',  group: 'Combat & Action' },
    { id: 'stealth',        label: 'Stealth',          emoji: '🥷',  group: 'Combat & Action' },
    { id: 'gunplay',        label: 'Gunplay',          emoji: '🔫',  group: 'Combat & Action' },
    { id: 'parkour',        label: 'Parkour',          emoji: '🏃',  group: 'Combat & Action' },
    { id: 'driving',        label: 'Vehicles',         emoji: '🚗',  group: 'Combat & Action' },
    { id: 'mounts',         label: 'Mounts & Riding',  emoji: '🐎',  group: 'Combat & Action' },
    { id: 'flight',         label: 'Flight',           emoji: '🦅',  group: 'Combat & Action' },
    { id: 'naval',          label: 'Naval & Sailing',  emoji: '⛵',  group: 'Combat & Action' },
    { id: 'underwater',     label: 'Diving',           emoji: '🤿',  group: 'Combat & Action' },
    // Progression & systems
    { id: 'skills',         label: 'Skill Tree',       emoji: '🌳',  group: 'Progression & Systems' },
    { id: 'classes',        label: 'Classes & Jobs',   emoji: '🧙',  group: 'Progression & Systems' },
    { id: 'attributes',     label: 'Attribute System', emoji: '📊',  group: 'Progression & Systems' },
    { id: 'leveling',       label: 'Leveling Curve',   emoji: '📈',  group: 'Progression & Systems' },
    { id: 'prestige',       label: 'Prestige / NG+',   emoji: '⭐',  group: 'Progression & Systems' },
    { id: 'reputation',     label: 'Reputation',       emoji: '🎖️',  group: 'Progression & Systems' },
    { id: 'alignment',      label: 'Alignment / Morality', emoji: '⚖️', group: 'Progression & Systems' },
    { id: 'achievements',   label: 'Achievements',     emoji: '🏆',  group: 'Progression & Systems' },
    // Crafting & economy
    { id: 'crafting',       label: 'Crafting',         emoji: '🔨',  group: 'Crafting & Economy' },
    { id: 'forging',        label: 'Forging',          emoji: '⚒️',  group: 'Crafting & Economy' },
    { id: 'alchemy',        label: 'Alchemy',          emoji: '⚗️',  group: 'Crafting & Economy' },
    { id: 'cooking',        label: 'Cooking',          emoji: '🍳',  group: 'Crafting & Economy' },
    { id: 'farming',        label: 'Farming',          emoji: '🌾',  group: 'Crafting & Economy' },
    { id: 'building',       label: 'Building',         emoji: '🏗️',  group: 'Crafting & Economy' },
    { id: 'economy',        label: 'Player Economy',   emoji: '💱',  group: 'Crafting & Economy' },
    { id: 'trading',        label: 'Trading',          emoji: '💹',  group: 'Crafting & Economy' },
    { id: 'auction',        label: 'Auction House',    emoji: '🪙',  group: 'Crafting & Economy' },
    // Social & narrative-mechanic
    { id: 'dialogue',       label: 'Dialogue System',  emoji: '💬',  group: 'Social & Narrative' },
    { id: 'romance',        label: 'Romance',          emoji: '💘',  group: 'Social & Narrative' },
    { id: 'companion',      label: 'Companions',       emoji: '🐺',  group: 'Social & Narrative' },
    { id: 'factions',       label: 'Factions',         emoji: '🛡️',  group: 'Social & Narrative' },
    { id: 'guilds',         label: 'Guilds & Clans',   emoji: '🏰',  group: 'Social & Narrative' },
    { id: 'politics',       label: 'Politics',         emoji: '🏛️',  group: 'Social & Narrative' },
    { id: 'crime',          label: 'Crime & Bounty',   emoji: '🦹',  group: 'Social & Narrative' },
    { id: 'investigation',  label: 'Investigation',    emoji: '🔍',  group: 'Social & Narrative' },
    { id: 'hacking',        label: 'Hacking',          emoji: '💻',  group: 'Social & Narrative' },
    { id: 'puzzle',         label: 'Puzzles',          emoji: '🧩',  group: 'Social & Narrative' },
    { id: 'minigames',      label: 'Minigames',        emoji: '🎲',  group: 'Social & Narrative' },
  ],
};

// ─── 2. WORLD MATRIX (36 phases) ─────────────────────────────────────
export const WORLD_MATRIX: MatrixConfig = {
  id: 'world',
  title: 'World Matrix',
  icon: 'globe',
  accent: '#10B981',
  hint: 'Every biome, region, dungeon, sky-realm and underdark, with full granularity.',
  axes: FIVE_AXES,
  phases: [
    { id: 'forest',     label: 'Forests',         emoji: '🌲', group: 'Biomes' },
    { id: 'jungle',     label: 'Jungles',         emoji: '🌴', group: 'Biomes' },
    { id: 'desert',     label: 'Deserts',         emoji: '🏜️', group: 'Biomes' },
    { id: 'tundra',     label: 'Tundra & Polar',  emoji: '❄️', group: 'Biomes' },
    { id: 'swamp',      label: 'Swamps & Bog',    emoji: '🐊', group: 'Biomes' },
    { id: 'mountain',   label: 'Mountains',       emoji: '⛰️', group: 'Biomes' },
    { id: 'plain',      label: 'Plains & Steppe', emoji: '🌾', group: 'Biomes' },
    { id: 'volcanic',   label: 'Volcanic',        emoji: '🌋', group: 'Biomes' },
    { id: 'coast',      label: 'Coast & Shore',   emoji: '🏖️', group: 'Biomes' },
    { id: 'ocean',      label: 'Ocean & Sea',     emoji: '🌊', group: 'Biomes' },
    { id: 'sky',        label: 'Sky Realms',      emoji: '☁️', group: 'Biomes' },
    { id: 'underdark',  label: 'Underdark',       emoji: '🕳️', group: 'Biomes' },
    { id: 'wasteland',  label: 'Wastelands',      emoji: '☢️', group: 'Biomes' },
    // Settlements
    { id: 'megacity',   label: 'Mega-City',       emoji: '🏙️', group: 'Settlements' },
    { id: 'city',       label: 'Cities',          emoji: '🏛️', group: 'Settlements' },
    { id: 'town',       label: 'Towns',           emoji: '🏘️', group: 'Settlements' },
    { id: 'village',    label: 'Villages',        emoji: '🏚️', group: 'Settlements' },
    { id: 'fortress',   label: 'Fortresses',      emoji: '🏯', group: 'Settlements' },
    { id: 'temple',     label: 'Temples',         emoji: '⛩️', group: 'Settlements' },
    { id: 'station',    label: 'Space Station',   emoji: '🛰️', group: 'Settlements' },
    // Dungeons / set-pieces
    { id: 'dungeon',    label: 'Dungeons',        emoji: '🗝️', group: 'Dungeons & Set Pieces' },
    { id: 'cave',       label: 'Caves',           emoji: '🦇', group: 'Dungeons & Set Pieces' },
    { id: 'ruin',       label: 'Ruins',           emoji: '🏚️', group: 'Dungeons & Set Pieces' },
    { id: 'tomb',       label: 'Tombs & Crypts',  emoji: '⚰️', group: 'Dungeons & Set Pieces' },
    { id: 'lair',       label: 'Boss Lairs',      emoji: '🐉', group: 'Dungeons & Set Pieces' },
    { id: 'raid',       label: 'Raid Arena',      emoji: '🏟️', group: 'Dungeons & Set Pieces' },
    { id: 'megastruct', label: 'Mega-Structure',  emoji: '🏗️', group: 'Dungeons & Set Pieces' },
    { id: 'planar',     label: 'Planar / Pocket', emoji: '🌌', group: 'Dungeons & Set Pieces' },
    // Systems
    { id: 'weather',    label: 'Weather Systems', emoji: '🌦️', group: 'World Systems' },
    { id: 'seasons',    label: 'Seasons',         emoji: '🍂', group: 'World Systems' },
    { id: 'daynight',   label: 'Day-Night Cycle', emoji: '🌗', group: 'World Systems' },
    { id: 'ecology',    label: 'Ecology & Food Web', emoji: '🦌', group: 'World Systems' },
    { id: 'geology',    label: 'Geology & Tectonics', emoji: '🪨', group: 'World Systems' },
    { id: 'hydrology',  label: 'Hydrology',       emoji: '💧', group: 'World Systems' },
    { id: 'history',    label: 'World History',   emoji: '📜', group: 'World Systems' },
    { id: 'religion',   label: 'Religion & Lore', emoji: '🕯️', group: 'World Systems' },
  ],
};

// ─── 3. ART MATRIX (28 phases) ───────────────────────────────────────
export const ART_MATRIX: MatrixConfig = {
  id: 'art',
  title: 'Art Matrix',
  icon: 'color-palette',
  accent: '#F59E0B',
  hint: 'Style, color, lighting, VFX, post — every art pipeline phase with 5 dials.',
  axes: PROD_AXES,
  phases: [
    { id: 'art_direction', label: 'Art Direction',   emoji: '🎨', group: 'Style' },
    { id: 'color_grade',   label: 'Color Grading',   emoji: '🎭', group: 'Style' },
    { id: 'typography',    label: 'Typography',      emoji: '🔠', group: 'Style' },
    { id: 'iconography',   label: 'Iconography',     emoji: '🪧', group: 'Style' },
    { id: 'ui_design',     label: 'UI Design',       emoji: '🖼️', group: 'Style' },
    { id: 'hud',           label: 'HUD',             emoji: '🎯', group: 'Style' },
    // Modeling & texturing
    { id: 'character',     label: 'Character Models', emoji: '🧍', group: 'Modeling & Texturing' },
    { id: 'environment',   label: 'Environment Art', emoji: '🏞️', group: 'Modeling & Texturing' },
    { id: 'props',         label: 'Prop Art',        emoji: '🪑', group: 'Modeling & Texturing' },
    { id: 'creatures',     label: 'Creatures',       emoji: '👹', group: 'Modeling & Texturing' },
    { id: 'foliage',       label: 'Foliage',         emoji: '🌿', group: 'Modeling & Texturing' },
    { id: 'texturing',     label: 'Texturing',       emoji: '🧱', group: 'Modeling & Texturing' },
    { id: 'shading',       label: 'Shading',         emoji: '🌑', group: 'Modeling & Texturing' },
    // Lighting & atmosphere
    { id: 'lighting',      label: 'Lighting',        emoji: '💡', group: 'Lighting & Atmosphere' },
    { id: 'shadows',       label: 'Shadows',         emoji: '🌚', group: 'Lighting & Atmosphere' },
    { id: 'gi',            label: 'Global Illum.',   emoji: '☀️', group: 'Lighting & Atmosphere' },
    { id: 'volumetrics',   label: 'Volumetrics',     emoji: '🌫️', group: 'Lighting & Atmosphere' },
    { id: 'reflections',   label: 'Reflections (RT)', emoji: '🪞', group: 'Lighting & Atmosphere' },
    { id: 'atmosphere',    label: 'Atmosphere',      emoji: '🌅', group: 'Lighting & Atmosphere' },
    // VFX & post
    { id: 'particles',     label: 'Particles',       emoji: '✨', group: 'VFX & Post' },
    { id: 'vfx',           label: 'VFX',             emoji: '💥', group: 'VFX & Post' },
    { id: 'postfx',        label: 'Post-Processing', emoji: '🎞️', group: 'VFX & Post' },
    { id: 'motion_blur',   label: 'Motion Blur',     emoji: '〰️', group: 'VFX & Post' },
    { id: 'dof',           label: 'Depth of Field',  emoji: '🔭', group: 'VFX & Post' },
    // Animation & cinematics
    { id: 'animation',     label: 'Animation',       emoji: '🎬', group: 'Animation & Cinematics' },
    { id: 'rigging',       label: 'Rigging',         emoji: '🦴', group: 'Animation & Cinematics' },
    { id: 'cinematics',    label: 'Cinematics',      emoji: '📽️', group: 'Animation & Cinematics' },
    { id: 'cutscenes',     label: 'Cutscenes',       emoji: '🎥', group: 'Animation & Cinematics' },
  ],
};

// ─── 4. AUDIO MATRIX (24 phases) ─────────────────────────────────────
export const AUDIO_MATRIX: MatrixConfig = {
  id: 'audio',
  title: 'Audio Matrix',
  icon: 'musical-notes',
  accent: '#EC4899',
  hint: 'Score → foley → mix → spatialisation, with the same 5 dials per phase.',
  axes: PROD_AXES,
  phases: [
    { id: 'score',         label: 'Music Score',     emoji: '🎼', group: 'Music' },
    { id: 'leitmotif',     label: 'Leitmotifs',      emoji: '🎶', group: 'Music' },
    { id: 'themes',        label: 'Themes',          emoji: '🎵', group: 'Music' },
    { id: 'ambient_music', label: 'Ambient Music',   emoji: '🎷', group: 'Music' },
    { id: 'combat_music',  label: 'Combat Music',    emoji: '🥁', group: 'Music' },
    { id: 'adaptive_music',label: 'Adaptive Music',  emoji: '🎚️', group: 'Music' },
    { id: 'sfx',           label: 'SFX',             emoji: '🔊', group: 'SFX & Foley' },
    { id: 'foley',         label: 'Foley',           emoji: '👞', group: 'SFX & Foley' },
    { id: 'footsteps',     label: 'Footsteps',       emoji: '👣', group: 'SFX & Foley' },
    { id: 'weapons',       label: 'Weapons SFX',     emoji: '💢', group: 'SFX & Foley' },
    { id: 'magic_sfx',     label: 'Magic SFX',       emoji: '🪄', group: 'SFX & Foley' },
    { id: 'creature_sfx',  label: 'Creatures SFX',   emoji: '🦁', group: 'SFX & Foley' },
    { id: 'vehicle_sfx',   label: 'Vehicle SFX',     emoji: '🚙', group: 'SFX & Foley' },
    { id: 'voice_lead',    label: 'Lead Voices',     emoji: '🎙️', group: 'Voice' },
    { id: 'voice_supp',    label: 'Supporting VO',   emoji: '🗣️', group: 'Voice' },
    { id: 'narration',     label: 'Narration',       emoji: '📖', group: 'Voice' },
    { id: 'barks',         label: 'NPC Barks',       emoji: '🐶', group: 'Voice' },
    { id: 'localisation_vo', label: 'Localised VO',  emoji: '🌐', group: 'Voice' },
    { id: 'ambience',      label: 'Ambience',        emoji: '🌳', group: 'Mix & Space' },
    { id: 'reverb',        label: 'Reverb',          emoji: '🕳️', group: 'Mix & Space' },
    { id: 'occlusion',     label: 'Occlusion',       emoji: '🚪', group: 'Mix & Space' },
    { id: 'spatial',       label: 'Spatial / 3D',    emoji: '🧊', group: 'Mix & Space' },
    { id: 'mix',           label: 'Mix Bus',         emoji: '🎛️', group: 'Mix & Space' },
    { id: 'master',        label: 'Mastering',       emoji: '🪞', group: 'Mix & Space' },
  ],
};

// ─── 5. TECH MATRIX (28 phases) ──────────────────────────────────────
export const TECH_MATRIX: MatrixConfig = {
  id: 'tech',
  title: 'Tech Matrix',
  icon: 'hardware-chip',
  accent: '#7C9CFF',
  hint: 'Engine, rendering, networking, persistence, modding, performance — five dials each.',
  axes: TECH_AXES,
  phases: [
    { id: 'rendering',     label: 'Rendering',        emoji: '🖼️', group: 'Engine' },
    { id: 'physics',       label: 'Physics Engine',   emoji: '⚙️', group: 'Engine' },
    { id: 'animation_sys', label: 'Animation Sys',    emoji: '🎞️', group: 'Engine' },
    { id: 'audio_engine',  label: 'Audio Engine',     emoji: '🔉', group: 'Engine' },
    { id: 'ai_engine',     label: 'AI Director',      emoji: '🧠', group: 'Engine' },
    { id: 'scripting',     label: 'Scripting Layer',  emoji: '📜', group: 'Engine' },
    { id: 'ecs',           label: 'ECS / DOTS',       emoji: '🧩', group: 'Engine' },
    { id: 'networking',    label: 'Netcode',          emoji: '🌐', group: 'Network & Persistence' },
    { id: 'replication',   label: 'Replication',      emoji: '🔁', group: 'Network & Persistence' },
    { id: 'lockstep',      label: 'Lockstep / Rollback', emoji: '⏪', group: 'Network & Persistence' },
    { id: 'save_system',   label: 'Save System',      emoji: '💾', group: 'Network & Persistence' },
    { id: 'cloud_save',    label: 'Cloud Save',       emoji: '☁️', group: 'Network & Persistence' },
    { id: 'streaming',     label: 'World Streaming',  emoji: '🛣️', group: 'Network & Persistence' },
    { id: 'modding',       label: 'Modding API',      emoji: '🧰', group: 'Network & Persistence' },
    { id: 'anti_cheat',    label: 'Anti-Cheat',       emoji: '🛡️', group: 'Security' },
    { id: 'drm',           label: 'DRM',              emoji: '🔐', group: 'Security' },
    { id: 'crypto',        label: 'Crypto / Hash',    emoji: '🔑', group: 'Security' },
    { id: 'telemetry',     label: 'Telemetry',        emoji: '📡', group: 'Ops & Performance' },
    { id: 'analytics',     label: 'Analytics',        emoji: '📊', group: 'Ops & Performance' },
    { id: 'crash_report',  label: 'Crash Reporting',  emoji: '💥', group: 'Ops & Performance' },
    { id: 'perf_budget',   label: 'Perf Budgets',     emoji: '🎚️', group: 'Ops & Performance' },
    { id: 'profiling',     label: 'Profiling',        emoji: '🧪', group: 'Ops & Performance' },
    { id: 'memory_mgmt',   label: 'Memory Manager',   emoji: '🧱', group: 'Ops & Performance' },
    { id: 'gpu_pipeline',  label: 'GPU Pipeline',     emoji: '🖥️', group: 'Ops & Performance' },
    { id: 'platform_port', label: 'Platform Ports',   emoji: '🎮', group: 'Platforms' },
    { id: 'crossplay',     label: 'Cross-Play',       emoji: '🤝', group: 'Platforms' },
    { id: 'accessibility', label: 'Accessibility',    emoji: '♿', group: 'Platforms' },
    { id: 'localisation',  label: 'Localisation',     emoji: '🈳', group: 'Platforms' },
  ],
};

// ─── 6. MONETISATION MATRIX (20 phases) ──────────────────────────────
export const MONETISATION_MATRIX: MatrixConfig = {
  id: 'monetisation',
  title: 'Monetisation Matrix',
  icon: 'cash',
  accent: '#34D399',
  hint: 'Premium, F2P, cosmetics, season-pass, ads — fairness vs aggressiveness for every channel.',
  axes: MONEY_AXES,
  phases: [
    { id: 'premium',        label: 'Premium Box',     emoji: '📦', group: 'Core Models' },
    { id: 'free_to_play',   label: 'Free-to-Play',    emoji: '🆓', group: 'Core Models' },
    { id: 'free_to_start',  label: 'Free-to-Start',   emoji: '🪙', group: 'Core Models' },
    { id: 'subscription',   label: 'Subscription',    emoji: '🔁', group: 'Core Models' },
    { id: 'early_access',   label: 'Early Access',    emoji: '🚀', group: 'Core Models' },
    { id: 'dlc',            label: 'DLC',             emoji: '🧩', group: 'Content Drops' },
    { id: 'expansions',     label: 'Expansions',      emoji: '🗺️', group: 'Content Drops' },
    { id: 'season_pass',    label: 'Season Pass',     emoji: '🎫', group: 'Content Drops' },
    { id: 'battle_pass',    label: 'Battle Pass',     emoji: '⚔️', group: 'Content Drops' },
    { id: 'cosmetics',      label: 'Cosmetics',       emoji: '👕', group: 'Cosmetics & MTX' },
    { id: 'mounts_pets',    label: 'Mounts / Pets',   emoji: '🐉', group: 'Cosmetics & MTX' },
    { id: 'emotes',         label: 'Emotes',          emoji: '💃', group: 'Cosmetics & MTX' },
    { id: 'currencies',     label: 'Soft Currency',   emoji: '🪙', group: 'Currencies' },
    { id: 'hard_currency',  label: 'Hard Currency',   emoji: '💎', group: 'Currencies' },
    { id: 'ads_reward',     label: 'Rewarded Ads',    emoji: '📺', group: 'Ads & Whales' },
    { id: 'ads_inter',      label: 'Interstitial Ads',emoji: '📺', group: 'Ads & Whales' },
    { id: 'gacha',          label: 'Gacha',           emoji: '🎰', group: 'Ads & Whales' },
    { id: 'lootbox',        label: 'Loot Boxes',      emoji: '🎁', group: 'Ads & Whales' },
    { id: 'referral',       label: 'Referrals',       emoji: '🔗', group: 'Retention' },
    { id: 'loyalty',        label: 'Loyalty Tier',    emoji: '🏅', group: 'Retention' },
  ],
};

// ─── 7. QA MATRIX (20 phases) ────────────────────────────────────────
export const QA_MATRIX: MatrixConfig = {
  id: 'qa',
  title: 'QA Matrix',
  icon: 'shield-checkmark',
  accent: '#A78BFA',
  hint: 'Coverage, severity, frequency, automation, human review for every test discipline.',
  axes: QA_AXES,
  phases: [
    { id: 'unit',           label: 'Unit Tests',       emoji: '🧪', group: 'Automated' },
    { id: 'integration',    label: 'Integration',      emoji: '🔗', group: 'Automated' },
    { id: 'regression',     label: 'Regression',       emoji: '🔁', group: 'Automated' },
    { id: 'smoke',          label: 'Smoke',            emoji: '💨', group: 'Automated' },
    { id: 'load',           label: 'Load / Stress',    emoji: '🏋️', group: 'Automated' },
    { id: 'soak',           label: 'Soak (24h+)',      emoji: '🛁', group: 'Automated' },
    { id: 'fuzz',           label: 'Fuzz / Property',  emoji: '🎲', group: 'Automated' },
    { id: 'replay',         label: 'Replay Determinism', emoji: '⏯️', group: 'Automated' },
    { id: 'save_load',      label: 'Save/Load Oracles',emoji: '💾', group: 'Oracles' },
    { id: 'invariants',     label: 'Invariants',       emoji: '📏', group: 'Oracles' },
    { id: 'balance',        label: 'Balance Audits',   emoji: '⚖️', group: 'Oracles' },
    { id: 'economy_sim',    label: 'Economy Sim',      emoji: '💱', group: 'Oracles' },
    { id: 'exploratory',    label: 'Exploratory',      emoji: '🔍', group: 'Human' },
    { id: 'playtest',       label: 'Playtest',         emoji: '🎮', group: 'Human' },
    { id: 'focus_test',     label: 'Focus Tests',      emoji: '👀', group: 'Human' },
    { id: 'beta_open',      label: 'Open Beta',        emoji: '🟢', group: 'Human' },
    { id: 'beta_closed',    label: 'Closed Beta',      emoji: '🔒', group: 'Human' },
    { id: 'accessibility',  label: 'Accessibility',    emoji: '♿', group: 'Compliance' },
    { id: 'localisation',   label: 'Localisation QA',  emoji: '🌍', group: 'Compliance' },
    { id: 'certification',  label: 'Platform Cert',    emoji: '🏛️', group: 'Compliance' },
  ],
};

// ─── 8. AGENT MATRIX (20 phases — ML configurations) ─────────────────
export const AGENT_MATRIX: MatrixConfig = {
  id: 'agent',
  title: 'Agent / ML Matrix',
  icon: 'rocket',
  accent: '#FACC15',
  hint: 'RAG depth, loss customisation, fine-tune intensity, log-probs, MCTS depth — wire the agents.',
  axes: ML_AXES,
  phases: [
    { id: 'rag_patch',      label: 'RAG · Patch Notes', emoji: '📜', group: 'RAG' },
    { id: 'rag_github',     label: 'RAG · GitHub Refs', emoji: '🐙', group: 'RAG' },
    { id: 'rag_templates',  label: 'RAG · Templates',   emoji: '🧬', group: 'RAG' },
    { id: 'rag_diagnostics',label: 'RAG · Diagnostics', emoji: '🩺', group: 'RAG' },
    { id: 'rag_design',     label: 'RAG · Design Patterns', emoji: '🧩', group: 'RAG' },
    { id: 'rag_legal',      label: 'RAG · Legal',       emoji: '⚖️', group: 'RAG' },
    { id: 'rag_stylometric',label: 'RAG · Stylometric', emoji: '✍️', group: 'RAG' },
    { id: 'rag_ast',        label: 'RAG · AST',         emoji: '🌳', group: 'RAG' },
    { id: 'loss_ce',        label: 'CE Loss',           emoji: '🧮', group: 'Loss' },
    { id: 'loss_label_smooth', label: 'Label Smoothing', emoji: '🌫️', group: 'Loss' },
    { id: 'loss_focal',     label: 'Focal CE',          emoji: '🎯', group: 'Loss' },
    { id: 'loss_mask',      label: 'Loss Masking',      emoji: '🎭', group: 'Loss' },
    { id: 'pref_dpo',       label: 'DPO',               emoji: '🆎', group: 'Preference' },
    { id: 'pref_orpo',      label: 'ORPO',              emoji: '🔀', group: 'Preference' },
    { id: 'pref_kto',       label: 'KTO',               emoji: '🧠', group: 'Preference' },
    { id: 'lora_r',         label: 'LoRA-r',            emoji: '🪡', group: 'Adapters' },
    { id: 'qlora_4bit',     label: 'QLoRA 4-bit',       emoji: '🧊', group: 'Adapters' },
    { id: 'icl_logprobs',   label: 'ICL log-probs',     emoji: '📈', group: 'In-Context' },
    { id: 'icl_self_consistency', label: 'Self-Consistency', emoji: '🔁', group: 'In-Context' },
    { id: 'icl_mcts',       label: 'MCTS Tree-Search',  emoji: '🌳', group: 'In-Context' },
  ],
};

// ─── Shared DB axes ──────────────────────────────────────────────────
const DB_AXES = [
  { id: 'priority',     label: 'priority',     min: 0, max: 100, default: 0 },
  { id: 'scale',        label: 'scale',        min: 0, max: 100, default: 0 },
  { id: 'consistency',  label: 'consistency',  min: 0, max: 100, default: 0 },
  { id: 'latency',      label: 'latency',      min: 0, max: 100, default: 0 },
  { id: 'cost',         label: 'cost',         min: 0, max: 100, default: 0 },
];

const DETECT_AXES = [
  { id: 'sensitivity',  label: 'sensitivity',  min: 0, max: 100, default: 0 },
  { id: 'specificity',  label: 'specificity',  min: 0, max: 100, default: 0 },
  { id: 'recall',       label: 'recall',       min: 0, max: 100, default: 0 },
  { id: 'audit_trail',  label: 'audit trail',  min: 0, max: 100, default: 0 },
  { id: 'autofix',      label: 'autofix',      min: 0, max: 100, default: 0 },
];

// Mutation amps content variation — always 1000 scale
const MUTATE_AXES = [
  { id: 'rate',         label: 'mutation rate', min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'magnitude',    label: 'magnitude',     min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'safety',       label: 'safety net',    min: 0, max: 100,  default: 0 },
  { id: 'novelty',      label: 'novelty',       min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'reversibility',label: 'reversibility', min: 0, max: 100,  default: 0 },
];

// Flair = quests / secrets / easter eggs — always 1000 scale
const FLAIR_AXES = [
  { id: 'rarity',       label: 'rarity',         min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'showmanship',  label: 'showmanship',    min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'lore_depth',   label: 'lore depth',     min: 0, max: 1000, default: 0, step: 1, impact: 'high' as const },
  { id: 'discovery',    label: 'discoverability',min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
  { id: 'replay_value', label: 'replay value',   min: 0, max: 1000, default: 0, step: 1, impact: 'critical' as const },
];

// ─── 9. VECTOR DATABASES MATRIX (AI / LLMs / Search Transformers) ────
export const VECTOR_DB_MATRIX: MatrixConfig = {
  id: 'vector_db',
  title: 'Vector DBs (AI · LLMs · Transformers)',
  icon: 'cube',
  accent: '#3B82F6',
  hint: 'Pinecone, Weaviate, Qdrant, Milvus, pgvector, FAISS, Chroma — five dials each.',
  axes: DB_AXES,
  phases: [
    { id: 'pinecone',     label: 'Pinecone',         emoji: '🌲', group: 'Managed' },
    { id: 'weaviate',     label: 'Weaviate',         emoji: '🕸️', group: 'Managed' },
    { id: 'qdrant',       label: 'Qdrant',           emoji: '🪐', group: 'Managed' },
    { id: 'vespa',        label: 'Vespa',            emoji: '🚀', group: 'Managed' },
    { id: 'turbopuffer',  label: 'Turbopuffer',      emoji: '🌀', group: 'Managed' },
    { id: 'milvus',       label: 'Milvus / Zilliz',  emoji: '🏯', group: 'Open Source' },
    { id: 'chroma',       label: 'Chroma',           emoji: '🎨', group: 'Open Source' },
    { id: 'faiss',        label: 'FAISS',            emoji: '🧮', group: 'Open Source' },
    { id: 'lancedb',      label: 'LanceDB',          emoji: '🛡️', group: 'Open Source' },
    { id: 'marqo',        label: 'Marqo',            emoji: '🐠', group: 'Open Source' },
    { id: 'pgvector',     label: 'pgvector',         emoji: '🐘', group: 'Hybrid SQL' },
    { id: 'redis_vec',    label: 'Redis Vector',     emoji: '🔴', group: 'Hybrid SQL' },
    { id: 'mongo_atlas',  label: 'Mongo Atlas Vec',  emoji: '🍃', group: 'Hybrid SQL' },
    { id: 'elastic_vec',  label: 'Elastic kNN',      emoji: '🔍', group: 'Hybrid SQL' },
    { id: 'opensearch_vec',label:'OpenSearch kNN',   emoji: '🔭', group: 'Hybrid SQL' },
    // Embeddings + transformers
    { id: 'emb_oai',      label: 'OpenAI text-emb',  emoji: '🅾️', group: 'Embeddings' },
    { id: 'emb_cohere',   label: 'Cohere embed',     emoji: '🅒', group: 'Embeddings' },
    { id: 'emb_voyage',   label: 'Voyage AI',        emoji: '⛵', group: 'Embeddings' },
    { id: 'emb_jina',     label: 'Jina AI',          emoji: '🧿', group: 'Embeddings' },
    { id: 'emb_e5',       label: 'E5 / Instructor',  emoji: '📐', group: 'Embeddings' },
    { id: 'emb_bge',      label: 'BGE / GTE',        emoji: '🧊', group: 'Embeddings' },
    // ANN algorithms
    { id: 'hnsw',         label: 'HNSW Index',       emoji: '🕸️', group: 'ANN Algorithms' },
    { id: 'ivf_pq',       label: 'IVF-PQ',           emoji: '🧱', group: 'ANN Algorithms' },
    { id: 'diskann',      label: 'DiskANN',          emoji: '💽', group: 'ANN Algorithms' },
    { id: 'scann',        label: 'ScaNN',            emoji: '📏', group: 'ANN Algorithms' },
    { id: 'annoy',        label: 'Annoy',            emoji: '🌳', group: 'ANN Algorithms' },
    { id: 'spann',        label: 'SPANN',            emoji: '🪜', group: 'ANN Algorithms' },
    // Reranking & retrieval transformers
    { id: 'colbert',      label: 'ColBERT v2',       emoji: '🎯', group: 'Rerankers' },
    { id: 'cross_encoder',label: 'Cross-Encoder',    emoji: '✖️', group: 'Rerankers' },
    { id: 'rrf',          label: 'Reciprocal RF',    emoji: '➕', group: 'Rerankers' },
    { id: 'splade',       label: 'SPLADE / Sparse',  emoji: '✨', group: 'Rerankers' },
    { id: 'bm25_hybrid',  label: 'BM25 Hybrid',      emoji: '🔡', group: 'Rerankers' },
  ],
};

// ─── 10. PLAGIARISM & STYLOMETRY MATRIX ─────────────────────────────
export const PLAGIARISM_MATRIX: MatrixConfig = {
  id: 'plagiarism',
  title: 'Plagiarism & Stylometry Tracking',
  icon: 'finger-print',
  accent: '#F472B6',
  hint: 'Moss, JPlag, CodeBERT, perceptual hashing, AST shape, stylometric prints — five dials each.',
  axes: DETECT_AXES,
  phases: [
    // Code similarity
    { id: 'moss',         label: 'MOSS (Stanford)',     emoji: '🌿', group: 'Code Similarity' },
    { id: 'jplag',        label: 'JPlag',               emoji: '☕', group: 'Code Similarity' },
    { id: 'copydetect',   label: 'CopyDetect',          emoji: '📋', group: 'Code Similarity' },
    { id: 'turnitin_code',label: 'Turnitin Code',       emoji: '🎓', group: 'Code Similarity' },
    { id: 'codeBERT',     label: 'CodeBERT embed',      emoji: '🧬', group: 'Code Similarity' },
    { id: 'unixcoder',    label: 'UnixCoder embed',     emoji: '🐧', group: 'Code Similarity' },
    { id: 'winnow',       label: 'Winnowing fingerprint',emoji:'🎐', group: 'Code Similarity' },
    { id: 'ncd',          label: 'Compression Dist.',   emoji: '🗜️', group: 'Code Similarity' },
    { id: 'sw_align',     label: 'Smith-Waterman',      emoji: '↔️', group: 'Code Similarity' },
    // AST / graph
    { id: 'ast_shape',    label: 'AST Shape Hash',      emoji: '🌳', group: 'AST & Graph' },
    { id: 'cpg_match',    label: 'Code-Property Graph', emoji: '🕸️', group: 'AST & Graph' },
    { id: 'cfg_hash',     label: 'CFG Node-Type Hash',  emoji: '🔁', group: 'AST & Graph' },
    { id: 'call_graph',   label: 'Call-Graph Match',    emoji: '📞', group: 'AST & Graph' },
    { id: 'datalog',      label: 'Datalog Shape Query', emoji: '🧠', group: 'AST & Graph' },
    // Stylometry
    { id: 'sty_camel',    label: 'camelCase Ratio',     emoji: '🐫', group: 'Stylometry' },
    { id: 'sty_snake',    label: 'snake_case Ratio',    emoji: '🐍', group: 'Stylometry' },
    { id: 'sty_brace',    label: 'Brace Style',         emoji: '🤜', group: 'Stylometry' },
    { id: 'sty_indent',   label: 'Indent / Tabs',       emoji: '⬇️', group: 'Stylometry' },
    { id: 'sty_cyclomatic',label:'Cyclomatic',          emoji: '🔄', group: 'Stylometry' },
    { id: 'sty_halstead', label: 'Halstead Volume',     emoji: '📊', group: 'Stylometry' },
    { id: 'sty_doc',      label: 'Docstring Density',   emoji: '📝', group: 'Stylometry' },
    { id: 'sty_typehint', label: 'Type-hint Density',   emoji: '🪧', group: 'Stylometry' },
    // Asset theft
    { id: 'phash',        label: 'pHash (textures)',    emoji: '🖼️', group: 'Asset Theft' },
    { id: 'mesh_hash',    label: 'Mesh Vertex Hash',    emoji: '🧊', group: 'Asset Theft' },
    { id: 'audio_finger', label: 'Audio Fingerprint',   emoji: '🎵', group: 'Asset Theft' },
    { id: 'shader_hash',  label: 'Shader Bytecode',     emoji: '💎', group: 'Asset Theft' },
    { id: 'anim_traj',    label: 'Animation Trajectory',emoji: '🏃', group: 'Asset Theft' },
    { id: 'engine_strings',label:'Engine String Tags',  emoji: '🏷️', group: 'Asset Theft' },
    { id: 'asset_store_id',label:'Asset Store GUID',    emoji: '🆔', group: 'Asset Theft' },
    // Legal / licensing
    { id: 'license_scan', label: 'License Scan (SBOM)', emoji: '📜', group: 'Licensing' },
    { id: 'cc_attribution',label:'CC-BY Attribution',   emoji: '🅒', group: 'Licensing' },
    { id: 'gpl_taint',    label: 'GPL Taint Check',     emoji: '☣️', group: 'Licensing' },
    { id: 'dmca_takedown',label: 'DMCA Watch',          emoji: '🚫', group: 'Licensing' },
  ],
};

// ─── 11. RELATIONAL DATABASES MATRIX (SQL / RDBMS) ──────────────────
export const RDBMS_MATRIX: MatrixConfig = {
  id: 'rdbms',
  title: 'Relational DBs (SQL / RDBMS)',
  icon: 'server',
  accent: '#FB923C',
  hint: 'Postgres, MySQL, SQLite, MariaDB, MSSQL, Oracle + normalization, indexing, sharding, replication.',
  axes: DB_AXES,
  phases: [
    // Engines
    { id: 'postgres',     label: 'PostgreSQL',          emoji: '🐘', group: 'Engines' },
    { id: 'mysql',        label: 'MySQL',               emoji: '🐬', group: 'Engines' },
    { id: 'mariadb',      label: 'MariaDB',             emoji: '🦭', group: 'Engines' },
    { id: 'sqlite',       label: 'SQLite',              emoji: '🪶', group: 'Engines' },
    { id: 'mssql',        label: 'SQL Server',          emoji: '🪟', group: 'Engines' },
    { id: 'oracle',       label: 'Oracle DB',           emoji: '🔮', group: 'Engines' },
    { id: 'cockroach',    label: 'CockroachDB',         emoji: '🪳', group: 'Engines' },
    { id: 'yugabyte',     label: 'YugabyteDB',          emoji: '🟣', group: 'Engines' },
    { id: 'tidb',         label: 'TiDB',                emoji: '🟦', group: 'Engines' },
    { id: 'duckdb',       label: 'DuckDB',              emoji: '🦆', group: 'Engines' },
    { id: 'clickhouse',   label: 'ClickHouse',          emoji: '🏠', group: 'Engines' },
    // Schema design
    { id: 'normalization',label: 'Normalization (1-5NF)',emoji:'📐', group: 'Schema Design' },
    { id: 'denorm',       label: 'Denormalization',     emoji: '📤', group: 'Schema Design' },
    { id: 'star_schema',  label: 'Star Schema',         emoji: '⭐', group: 'Schema Design' },
    { id: 'snowflake_s',  label: 'Snowflake Schema',    emoji: '❄️', group: 'Schema Design' },
    { id: 'temporal',     label: 'Temporal Tables',     emoji: '⏰', group: 'Schema Design' },
    { id: 'soft_delete',  label: 'Soft Delete',         emoji: '🗑️', group: 'Schema Design' },
    // Indexing & queries
    { id: 'btree',        label: 'B-Tree Index',        emoji: '🌲', group: 'Indexing' },
    { id: 'hash_idx',     label: 'Hash Index',          emoji: '#️⃣', group: 'Indexing' },
    { id: 'gin_gist',     label: 'GIN / GiST',          emoji: '🍸', group: 'Indexing' },
    { id: 'partial_idx',  label: 'Partial Index',       emoji: '🌗', group: 'Indexing' },
    { id: 'covering_idx', label: 'Covering Index',      emoji: '☂️', group: 'Indexing' },
    { id: 'query_plan',   label: 'Query Planner',       emoji: '🗺️', group: 'Indexing' },
    // Transactions
    { id: 'acid',         label: 'ACID',                emoji: '🧪', group: 'Transactions' },
    { id: 'isolation',    label: 'Isolation Levels',    emoji: '🔒', group: 'Transactions' },
    { id: 'mvcc',         label: 'MVCC',                emoji: '🌀', group: 'Transactions' },
    { id: 'savepoint',    label: 'Savepoints',          emoji: '📍', group: 'Transactions' },
    { id: 'two_phase',    label: '2-Phase Commit',      emoji: '🪀', group: 'Transactions' },
    // Scale & ops
    { id: 'replication',  label: 'Replication',         emoji: '🔁', group: 'Scale & Ops' },
    { id: 'sharding',     label: 'Sharding',            emoji: '🔪', group: 'Scale & Ops' },
    { id: 'partitioning', label: 'Partitioning',        emoji: '🧩', group: 'Scale & Ops' },
    { id: 'failover',     label: 'Failover',            emoji: '🛟', group: 'Scale & Ops' },
    { id: 'backup',       label: 'Backup / PITR',       emoji: '💾', group: 'Scale & Ops' },
    { id: 'migrations',   label: 'Migrations (Flyway)', emoji: '🛫', group: 'Scale & Ops' },
    // Game-specific
    { id: 'player_table', label: 'Player Table',        emoji: '🧍', group: 'Game Schemas' },
    { id: 'inventory_t',  label: 'Inventory Table',     emoji: '🎒', group: 'Game Schemas' },
    { id: 'leaderboard_t',label: 'Leaderboard Table',   emoji: '🏆', group: 'Game Schemas' },
    { id: 'telemetry_t',  label: 'Telemetry Table',     emoji: '📡', group: 'Game Schemas' },
    { id: 'audit_log_t',  label: 'Audit Log',           emoji: '🧾', group: 'Game Schemas' },
  ],
};

// ─── 12. STYLES MATRIX (every "style" picker as a tunable phase) ────
export const STYLES_MATRIX: MatrixConfig = {
  id: 'styles',
  title: 'Styles Matrix · All Style Pickers',
  icon: 'sparkles',
  accent: '#A855F7',
  hint: 'Every style picker — graphic, sound, music, design, cinematic, director, writing, animation tone — as a dial set.',
  axes: PROD_AXES,
  phases: [
    // Core 9 (mirroring legacy style_params)
    { id: 'graphic_style',    label: 'Graphic Style',     emoji: '🖌️', group: 'Visual' },
    { id: 'palette_style',    label: 'Palette',           emoji: '🎨', group: 'Visual' },
    { id: 'dimension_style',  label: 'Dimension (2D/3D)', emoji: '🧊', group: 'Visual' },
    { id: 'asset_style',      label: 'Asset Style',       emoji: '🪑', group: 'Visual' },
    { id: 'model_style',      label: 'Model Style',       emoji: '🧍', group: 'Visual' },
    { id: 'font_style',       label: 'Typography',        emoji: '🔠', group: 'Visual' },
    { id: 'icon_style',       label: 'Icon Style',        emoji: '🔣', group: 'Visual' },
    { id: 'hud_style',        label: 'HUD Style',         emoji: '🎯', group: 'Visual' },
    { id: 'menu_style',       label: 'Menu Style',        emoji: '📜', group: 'Visual' },
    // Audio
    { id: 'sound_style',      label: 'Sound Style',       emoji: '🔊', group: 'Audio' },
    { id: 'music_style',      label: 'Music Style',       emoji: '🎼', group: 'Audio' },
    { id: 'voice_style',      label: 'Voice Style',       emoji: '🎙️', group: 'Audio' },
    { id: 'foley_style',      label: 'Foley Style',       emoji: '👞', group: 'Audio' },
    // Cinematic & direction
    { id: 'cinematic_style',  label: 'Cinematic Style',   emoji: '🎬', group: 'Cinematic' },
    { id: 'director_style',   label: 'Director Style',    emoji: '🎥', group: 'Cinematic' },
    { id: 'camera_style',     label: 'Camera Style',      emoji: '📷', group: 'Cinematic' },
    { id: 'editing_style',    label: 'Editing Style',     emoji: '✂️', group: 'Cinematic' },
    { id: 'shot_style',       label: 'Shot Composition',  emoji: '🖼️', group: 'Cinematic' },
    // Writing & tone
    { id: 'writing_style',    label: 'Writing Style',     emoji: '✍️', group: 'Writing' },
    { id: 'narrative_voice',  label: 'Narrative Voice',   emoji: '🗣️', group: 'Writing' },
    { id: 'humor_style',      label: 'Humor Style',       emoji: '😂', group: 'Writing' },
    { id: 'dialogue_style',   label: 'Dialogue Style',    emoji: '💬', group: 'Writing' },
    { id: 'tone_style',       label: 'Tone',              emoji: '🌡️', group: 'Writing' },
    // Combat & movement
    { id: 'combat_style',     label: 'Combat Style',      emoji: '⚔️', group: 'Combat & Motion' },
    { id: 'weapon_style',     label: 'Weapon Style',      emoji: '🗡️', group: 'Combat & Motion' },
    { id: 'animation_style',  label: 'Animation Style',   emoji: '🏃', group: 'Combat & Motion' },
    { id: 'locomotion_style', label: 'Locomotion',        emoji: '🦿', group: 'Combat & Motion' },
    // Design
    { id: 'design_style',     label: 'Design Style',      emoji: '📐', group: 'Design' },
    { id: 'level_style',      label: 'Level Style',       emoji: '🗺️', group: 'Design' },
    { id: 'ui_style',         label: 'UI Style',          emoji: '🪟', group: 'Design' },
    { id: 'storefront_style', label: 'Storefront Style',  emoji: '🏪', group: 'Design' },
  ],
};

// ─── 13. MUTATION MATRIX (per-axis variation_mutation amplifier) ────
export const MUTATION_MATRIX: MatrixConfig = {
  id: 'mutation',
  title: 'Mutation Matrix · Variation Engine',
  icon: 'pulse',
  accent: '#F87171',
  hint: 'Per-axis mutation: drift, jitter, mutate, recombine — keep families diverse without breaking balance.',
  axes: MUTATE_AXES,
  phases: [
    // Procedural mutation
    { id: 'world_drift',      label: 'World Drift',       emoji: '🌍', group: 'Procedural' },
    { id: 'biome_drift',      label: 'Biome Drift',       emoji: '🌲', group: 'Procedural' },
    { id: 'weather_jitter',   label: 'Weather Jitter',    emoji: '🌦️', group: 'Procedural' },
    { id: 'palette_shift',    label: 'Palette Shift',     emoji: '🌈', group: 'Procedural' },
    { id: 'layout_mutation',  label: 'Layout Mutation',   emoji: '🧱', group: 'Procedural' },
    // Entity mutation
    { id: 'enemy_mutation',   label: 'Enemy Mutation',    emoji: '👾', group: 'Entities' },
    { id: 'npc_mutation',     label: 'NPC Mutation',      emoji: '🧑', group: 'Entities' },
    { id: 'boss_mutation',    label: 'Boss Mutation',     emoji: '🐲', group: 'Entities' },
    { id: 'pet_mutation',     label: 'Pet / Companion',   emoji: '🐶', group: 'Entities' },
    { id: 'flora_mutation',   label: 'Flora Mutation',    emoji: '🌱', group: 'Entities' },
    // Items & loot
    { id: 'weapon_mutation',  label: 'Weapon Mutation',   emoji: '🗡️', group: 'Items & Loot' },
    { id: 'armor_mutation',   label: 'Armor Mutation',    emoji: '🛡️', group: 'Items & Loot' },
    { id: 'loot_table_mutation',label:'Loot Table',       emoji: '🎰', group: 'Items & Loot' },
    { id: 'drop_rate_mutation',label:'Drop Rate',         emoji: '📉', group: 'Items & Loot' },
    { id: 'consumable_mutation',label:'Consumables',      emoji: '🍷', group: 'Items & Loot' },
    // Systems
    { id: 'balance_mutation', label: 'Balance Numbers',   emoji: '⚖️', group: 'Systems' },
    { id: 'formula_mutation', label: 'Formula Mutation',  emoji: '🧮', group: 'Systems' },
    { id: 'economy_mutation', label: 'Economy Curves',    emoji: '💱', group: 'Systems' },
    { id: 'ai_behavior_mutation',label:'AI Behavior',     emoji: '🧠', group: 'Systems' },
    { id: 'quest_branch_mutation',label:'Quest Branches', emoji: '🛤️', group: 'Systems' },
    // Narrative
    { id: 'dialogue_mutation',label: 'Dialogue Lines',    emoji: '💭', group: 'Narrative' },
    { id: 'rumor_mutation',   label: 'Rumor / Hearsay',   emoji: '🗨️', group: 'Narrative' },
    { id: 'lore_mutation',    label: 'Lore Variants',     emoji: '📚', group: 'Narrative' },
    // Asset mutation
    { id: 'mesh_mutation',    label: 'Mesh Mutation',     emoji: '🧊', group: 'Assets' },
    { id: 'texture_mutation', label: 'Texture Variants',  emoji: '🧱', group: 'Assets' },
    { id: 'sfx_mutation',     label: 'SFX Variation',     emoji: '🎧', group: 'Assets' },
    { id: 'music_mutation',   label: 'Music Variation',   emoji: '🎶', group: 'Assets' },
  ],
};

// ─── 14. UNIQUE FLAIR MATRIX (signature / surprise / hand-crafted) ──
export const UNIQUE_FLAIR_MATRIX: MatrixConfig = {
  id: 'unique_flair',
  title: 'Unique Flair · Signatures & Easter Eggs',
  icon: 'star',
  accent: '#FBBF24',
  hint: 'Signature moves, named NPCs, easter eggs, secret rooms — the hand-crafted moments that go viral.',
  axes: FLAIR_AXES,
  phases: [
    // Signature gameplay
    { id: 'signature_move',   label: 'Signature Moves',   emoji: '🥋', group: 'Signature Gameplay' },
    { id: 'ultimate_ability', label: 'Ultimate Abilities',emoji: '💥', group: 'Signature Gameplay' },
    { id: 'finisher',         label: 'Finishers',         emoji: '☠️', group: 'Signature Gameplay' },
    { id: 'parry_window',     label: 'Perfect Parry',     emoji: '🛡️', group: 'Signature Gameplay' },
    { id: 'execution_anim',   label: 'Execution Anim',    emoji: '🪓', group: 'Signature Gameplay' },
    // Named content
    { id: 'named_npc',        label: 'Named NPCs',        emoji: '👑', group: 'Named Content' },
    { id: 'named_item',       label: 'Named Items',       emoji: '⚔️', group: 'Named Content' },
    { id: 'named_location',   label: 'Named Locations',   emoji: '🏰', group: 'Named Content' },
    { id: 'named_boss',       label: 'Named Bosses',      emoji: '🐉', group: 'Named Content' },
    { id: 'named_mount',      label: 'Named Mounts',      emoji: '🦄', group: 'Named Content' },
    // Easter eggs
    { id: 'easter_egg_dev',   label: 'Dev Cameos',        emoji: '🥚', group: 'Easter Eggs' },
    { id: 'easter_egg_lore',  label: 'Lore Cameos',       emoji: '🪶', group: 'Easter Eggs' },
    { id: 'easter_egg_meta',  label: 'Meta References',   emoji: '🧠', group: 'Easter Eggs' },
    { id: 'easter_egg_holiday',label:'Holiday Events',    emoji: '🎄', group: 'Easter Eggs' },
    { id: 'achievement_secret',label:'Hidden Achievements',emoji:'🏅', group: 'Easter Eggs' },
    // Secrets
    { id: 'secret_room',      label: 'Secret Rooms',      emoji: '🚪', group: 'Secrets' },
    { id: 'secret_boss',      label: 'Secret Bosses',     emoji: '👹', group: 'Secrets' },
    { id: 'secret_ending',    label: 'Secret Endings',    emoji: '🌅', group: 'Secrets' },
    { id: 'secret_minigame',  label: 'Secret Minigames',  emoji: '🎮', group: 'Secrets' },
    { id: 'secret_class',     label: 'Secret Classes',    emoji: '🧙', group: 'Secrets' },
    // Hand-crafted moments
    { id: 'cinematic_moment', label: 'Cinematic Moments', emoji: '🎬', group: 'Hand-Crafted' },
    { id: 'one_off_set_piece',label:'One-Off Set Piece',  emoji: '🎆', group: 'Hand-Crafted' },
    { id: 'unique_death',     label: 'Unique Death Scene',emoji: '☠️', group: 'Hand-Crafted' },
    { id: 'unique_intro',     label: 'Unique Intros',     emoji: '🎭', group: 'Hand-Crafted' },
    { id: 'unique_outro',     label: 'Unique Outros',     emoji: '🎞️', group: 'Hand-Crafted' },
    // Emotes & social flair
    { id: 'custom_emote',     label: 'Custom Emotes',     emoji: '💃', group: 'Social Flair' },
    { id: 'custom_voice_line',label: 'Custom Voice Lines',emoji: '🗣️', group: 'Social Flair' },
    { id: 'custom_taunt',     label: 'Custom Taunts',     emoji: '🙄', group: 'Social Flair' },
    { id: 'callout_badge',    label: 'Callout Badges',    emoji: '🏆', group: 'Social Flair' },
  ],
};

// ─── Master export ───────────────────────────────────────────────────
export const ALL_MATRICES: MatrixConfig[] = [
  MECHANICS_MATRIX,
  WORLD_MATRIX,
  ART_MATRIX,
  AUDIO_MATRIX,
  TECH_MATRIX,
  MONETISATION_MATRIX,
  QA_MATRIX,
  AGENT_MATRIX,
  // ── 2026-05-15 second wave ─────────────────────────────────────────
  VECTOR_DB_MATRIX,
  PLAGIARISM_MATRIX,
  RDBMS_MATRIX,
  STYLES_MATRIX,
  MUTATION_MATRIX,
  UNIQUE_FLAIR_MATRIX,
];
