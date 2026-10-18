/**
 * Galaxy Studio — Production Sections (P3 from triage)
 * New questionnaire sections that add the missing "complete game builder" feel:
 *   • Asset Quality   (texture / model / audio / animation fidelity)
 *   • Art Direction   (visual school)
 *   • Audio Production
 *   • Platform Targets
 *   • Monetization
 *   • Live Ops
 *   • Localization   (multi-select)
 *   • Accessibility
 *   • Save System
 *   • Network / Online
 *
 * All numeric inputs use the new DeepSlider (0-100) for fine-grained control.
 * Values are surfaced as `extra_params` on the build payload — backend stores
 * them on the build object for downstream phase consumption (Phase 1 in triage).
 */
export interface ProductionParam {
  key: string;
  label: string;
  help?: string;
  max?: number;
  icon?: string;
  unit?: string;
  tierLabels?: string[];
}

export interface ProductionSection {
  id: string;
  title: string;
  icon: string;
  color: string;
  kind: 'slider' | 'multiSelect' | 'select';
  params?: ProductionParam[];
  options?: { value: string; label: string; sub?: string }[];
}

export const ART_DIRECTION_STYLES = [
  { value: 'photoreal', label: 'Photorealistic', sub: 'AAA next-gen, ray-traced realism' },
  { value: 'stylized', label: 'Stylized', sub: 'Painterly with bold silhouettes' },
  { value: 'cel_shaded', label: 'Cel-Shaded', sub: 'Anime / comic-book look' },
  { value: 'pixel_art', label: 'Pixel Art', sub: 'Retro 16/32-bit aesthetic' },
  { value: 'voxel', label: 'Voxel', sub: 'Blocky low-poly cube world' },
  { value: 'low_poly_flat', label: 'Low Poly Flat', sub: 'Minimal, faceted geometry' },
  { value: 'isometric', label: 'Isometric', sub: 'Diorama / city-builder feel' },
  { value: 'noir', label: 'Noir', sub: 'Monochrome high-contrast' },
  { value: 'cyberpunk', label: 'Cyberpunk', sub: 'Neon, chrome, dystopia' },
  { value: 'solarpunk', label: 'Solarpunk', sub: 'Lush eco-utopia, soft pastels' },
  { value: 'cosmic_horror', label: 'Cosmic Horror', sub: 'Lovecraftian dread, deep palette' },
  { value: 'high_fantasy', label: 'High Fantasy', sub: 'Tolkien-grade epic' },
  { value: 'dark_fantasy', label: 'Dark Fantasy', sub: 'Grim & grindcore (Souls-like)' },
  { value: 'mythic_norse', label: 'Mythic Norse', sub: 'Cold runes, ice, lore' },
  { value: 'feudal_japan', label: 'Feudal Japan', sub: 'Ink-wash bushido' },
  { value: 'pre_columbian', label: 'Pre-Columbian', sub: 'Mesoamerican / Andean motifs' },
  { value: 'art_deco', label: 'Art Deco', sub: 'Geometric 1920s glamour' },
  { value: 'bauhaus', label: 'Bauhaus', sub: 'Primary colours, modernist forms' },
  { value: 'gothic_horror', label: 'Gothic Horror', sub: 'Castles, decay, candle-light' },
  { value: 'biopunk', label: 'Biopunk', sub: 'Organic tech, fleshy machines' },
  { value: 'dieselpunk', label: 'Dieselpunk', sub: 'WWII alt-history, brass & oil' },
  { value: 'space_opera', label: 'Space Opera', sub: 'Galactic empires, big sci-fi' },
  { value: 'hard_scifi', label: 'Hard Sci-Fi', sub: 'Plausible near-future tech' },
  { value: 'vapour_y2k', label: 'Vapor Y2K', sub: 'Glossy chrome, magenta sky' },
  { value: 'comic_pulp', label: 'Comic Pulp', sub: 'Saturated halftone action' },
  { value: 'watercolor', label: 'Watercolor', sub: 'Soft washes, hand-painted' },
  { value: 'paper_craft', label: 'Paper Craft', sub: 'Origami / cardboard diorama' },
  { value: 'claymation', label: 'Claymation', sub: 'Stop-motion clay puppets' },
  { value: 'glitch_core', label: 'Glitch Core', sub: 'Datamosh, vaporwave decay' },
  { value: 'bioluminescent', label: 'Bioluminescent', sub: 'Deep-sea glow palette' },
];

export const GAME_TONE_STYLES = [
  { value: 'heroic', label: 'Heroic' },
  { value: 'whimsical', label: 'Whimsical' },
  { value: 'comedic', label: 'Comedic' },
  { value: 'satirical', label: 'Satirical' },
  { value: 'melancholic', label: 'Melancholic' },
  { value: 'tragic', label: 'Tragic' },
  { value: 'absurdist', label: 'Absurdist' },
  { value: 'philosophical', label: 'Philosophical' },
  { value: 'meditative', label: 'Meditative' },
  { value: 'horror', label: 'Horror' },
  { value: 'thriller', label: 'Thriller' },
  { value: 'romantic', label: 'Romantic' },
  { value: 'coming_of_age', label: 'Coming-of-Age' },
  { value: 'mystery', label: 'Mystery' },
  { value: 'political', label: 'Political' },
  { value: 'survival_grim', label: 'Survival Grim' },
];

export const NARRATIVE_STRUCTURES = [
  { value: 'linear', label: 'Linear' },
  { value: 'branching', label: 'Branching' },
  { value: 'hub_and_spoke', label: 'Hub & Spoke' },
  { value: 'parallel', label: 'Parallel Threads' },
  { value: 'looping', label: 'Time Loop' },
  { value: 'rashomon', label: 'Rashomon (multi-POV)' },
  { value: 'emergent', label: 'Emergent / Sandbox' },
  { value: 'episodic', label: 'Episodic Anthology' },
  { value: 'roguelite_meta', label: 'Roguelite Meta-Narrative' },
];

export const PERSPECTIVES = [
  { value: 'first_person', label: 'First Person' },
  { value: 'third_person_close', label: 'Third Person (close)' },
  { value: 'third_person_action', label: 'Third Person Action' },
  { value: 'isometric', label: 'Isometric' },
  { value: 'topdown', label: 'Top-Down' },
  { value: 'sidescroll', label: '2.5D Sidescroll' },
  { value: 'platformer', label: 'Pure 2D Platformer' },
  { value: 'cinematic_cam', label: 'Cinematic Camera' },
  { value: 'vr_immersive', label: 'VR Immersive' },
  { value: 'rts_overview', label: 'RTS Overview' },
];

export const PRODUCTION_SECTIONS: ProductionSection[] = [
  {
    id: 'asset_quality',
    title: 'Asset Quality',
    icon: 'images',
    color: '#2563EB',
    kind: 'slider',
    params: [
      { key: 'texture_resolution', label: 'Texture Resolution', help: '0 = 256px • 100 = 8K PBR', icon: 'grid' },
      { key: 'model_poly_count', label: 'Model Poly Count', help: 'Low-poly → cinematic mesh density' },
      { key: 'shader_complexity', label: 'Shader Complexity', help: 'Flat-shaded → fully procedural PBR + RT' },
      { key: 'particle_density', label: 'Particle Density', help: 'How rich the FX systems are' },
      { key: 'foliage_detail', label: 'Foliage Detail', help: 'Sparse → forest-floor coverage' },
      { key: 'reflection_quality', label: 'Reflection Quality', help: 'Cubemaps → screen-space → ray-traced' },
      { key: 'lod_aggressiveness', label: 'LOD Aggressiveness', help: 'Distant detail preservation' },
    ],
  },
  {
    id: 'audio_production',
    title: 'Audio Production',
    icon: 'musical-notes',
    color: '#A855F7',
    kind: 'slider',
    params: [
      { key: 'music_variety', label: 'Music Track Variety' },
      { key: 'instrument_palette', label: 'Instrument Palette' },
      { key: 'voice_acting_depth', label: 'Voice-Acting Depth' },
      { key: 'sfx_layering', label: 'SFX Layering' },
      { key: 'audio_bitrate', label: 'Audio Bitrate', help: '0 = 64 kbps • 100 = lossless' },
      { key: 'dynamic_mix', label: 'Dynamic Mix Adapter', help: 'Combat / explore / cutscene blends' },
      { key: 'binaural_3d_audio', label: 'Binaural / 3D Audio' },
    ],
  },
  {
    id: 'platform_targets',
    title: 'Platform Targets',
    icon: 'phone-portrait',
    color: '#10B981',
    kind: 'multiSelect',
    options: [
      { value: 'ios', label: 'iOS' },
      { value: 'android', label: 'Android' },
      { value: 'steam', label: 'Steam (Windows)' },
      { value: 'macos', label: 'macOS' },
      { value: 'linux', label: 'Linux' },
      { value: 'switch', label: 'Nintendo Switch' },
      { value: 'ps5', label: 'PlayStation 5' },
      { value: 'xbox_series', label: 'Xbox Series X|S' },
      { value: 'web_html5', label: 'Web (HTML5)' },
      { value: 'vr_quest', label: 'Meta Quest (VR)' },
      { value: 'vr_psvr2', label: 'PSVR2' },
      { value: 'cloud_streaming', label: 'Cloud Streaming' },
    ],
  },
  {
    id: 'monetization',
    title: 'Monetization Model',
    icon: 'cash',
    color: '#F59E0B',
    kind: 'select',
    options: [
      { value: 'premium', label: 'Premium ($)', sub: 'One-time purchase, no IAP' },
      { value: 'premium_dlc', label: 'Premium + DLC', sub: 'Expansion packs / season pass' },
      { value: 'free_with_ads', label: 'Free + Ads', sub: 'Rewarded video, banner' },
      { value: 'free_with_iap', label: 'Free + IAP', sub: 'Cosmetics & convenience' },
      { value: 'freemium_hard', label: 'Freemium (hard paywall)', sub: 'Early game free, gate later' },
      { value: 'battle_pass', label: 'Battle Pass', sub: 'Seasonal progression tier' },
      { value: 'subscription', label: 'Subscription', sub: 'Monthly access' },
      { value: 'kickstarter_early', label: 'Crowdfunded / Early Access', sub: 'Iterative paid betas' },
      { value: 'no_monetization', label: 'No Monetization', sub: 'Educational / passion project' },
    ],
  },
  {
    id: 'live_ops',
    title: 'Live Ops & Content Cadence',
    icon: 'pulse',
    color: '#EC4899',
    kind: 'slider',
    params: [
      { key: 'seasonal_events_count', label: 'Seasonal Events / yr', help: '0 = none • 100 = continuous' },
      { key: 'patch_cadence', label: 'Patch Cadence', help: 'Annual → daily hotfixes' },
      { key: 'community_features', label: 'Community Features', help: 'Forums, leaderboards, clans' },
      { key: 'creator_tools_depth', label: 'Creator Tools Depth', help: 'Level editor, modding API' },
      { key: 'esports_readiness', label: 'Esports Readiness', help: 'Spectator UI, replays, brackets' },
    ],
  },
  {
    id: 'accessibility',
    title: 'Accessibility',
    icon: 'accessibility',
    color: '#3B82F6',
    kind: 'slider',
    params: [
      { key: 'subtitle_support', label: 'Subtitle Support' },
      { key: 'colorblind_modes', label: 'Color-blind Modes' },
      { key: 'remap_controls', label: 'Remappable Controls' },
      { key: 'difficulty_assist', label: 'Difficulty Assist' },
      { key: 'screen_reader_support', label: 'Screen Reader Support' },
      { key: 'photo_sensitivity_safe', label: 'Photo-sensitivity Safety' },
      { key: 'audio_visual_cues', label: 'Audio→Visual Cues' },
    ],
  },
  {
    id: 'save_system',
    title: 'Save System',
    icon: 'save',
    color: '#22C55E',
    kind: 'select',
    options: [
      { value: 'auto_continuous', label: 'Continuous Autosave' },
      { value: 'checkpoint', label: 'Checkpoints' },
      { value: 'manual_slots', label: 'Manual Multi-slot' },
      { value: 'cloud_sync', label: 'Cloud Sync' },
      { value: 'permadeath', label: 'Permadeath (roguelike)' },
      { value: 'ironman', label: 'Ironman (single save)' },
    ],
  },
  {
    id: 'network_mode',
    title: 'Network / Online Mode',
    icon: 'wifi',
    color: '#6366F1',
    kind: 'select',
    options: [
      { value: 'offline_only', label: 'Offline Only' },
      { value: 'async_multi', label: 'Async Multiplayer' },
      { value: 'co_op_local', label: 'Local Co-op' },
      { value: 'co_op_online', label: 'Online Co-op' },
      { value: 'pvp_competitive', label: 'PvP Competitive' },
      { value: 'mmo_persistent', label: 'MMO Persistent World' },
      { value: 'p2p_loose', label: 'P2P Lobby' },
      { value: 'dedicated_servers', label: 'Dedicated Servers' },
    ],
  },
  {
    id: 'localization',
    title: 'Localization Languages',
    icon: 'language',
    color: '#F472B6',
    kind: 'multiSelect',
    options: [
      { value: 'en', label: 'English' },
      { value: 'es', label: 'Spanish' },
      { value: 'pt_br', label: 'Portuguese (BR)' },
      { value: 'fr', label: 'French' },
      { value: 'de', label: 'German' },
      { value: 'it', label: 'Italian' },
      { value: 'ru', label: 'Russian' },
      { value: 'tr', label: 'Turkish' },
      { value: 'pl', label: 'Polish' },
      { value: 'nl', label: 'Dutch' },
      { value: 'ja', label: 'Japanese' },
      { value: 'ko', label: 'Korean' },
      { value: 'zh_cn', label: 'Chinese (Simplified)' },
      { value: 'zh_tw', label: 'Chinese (Traditional)' },
      { value: 'ar', label: 'Arabic' },
      { value: 'hi', label: 'Hindi' },
      { value: 'id', label: 'Indonesian' },
      { value: 'th', label: 'Thai' },
      { value: 'vi', label: 'Vietnamese' },
    ],
  },
];

/** Default state shape for the new production sections. */
export interface ProductionState {
  // slider params (0..100)
  sliders: Record<string, number>;
  // multi-select sets
  platforms: string[];
  languages: string[];
  // single select
  monetization: string;
  saveSystem: string;
  networkMode: string;
  artDirection: string;
  gameTone: string;
  narrativeStructure: string;
  perspective: string;
}

export const DEFAULT_PRODUCTION_STATE: ProductionState = {
  sliders: {},
  platforms: ['ios', 'android', 'steam', 'web_html5'],
  languages: ['en'],
  monetization: 'premium',
  saveSystem: 'auto_continuous',
  networkMode: 'offline_only',
  artDirection: 'stylized',
  gameTone: 'heroic',
  narrativeStructure: 'branching',
  perspective: 'third_person_close',
};
