/**
 * Global app settings — persists to AsyncStorage.
 * Covers Jeeves, Academy (TTS), and Galaxy Studio (phase weights +
 * 500-slider Narrative DNA cockpit).
 *
 * Usage:  const rate = useSettings(s => s.academy.ttsRate);
 *         useSettings.setState(s => { s.academy.ttsRate = 1.2 })
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  NARRATIVE_DNA_GROUPS_DATA,
  NARRATIVE_DNA_KEYS as DNA_KEYS_FROM_DATA,
  NARRATIVE_DNA_TOTAL,
  DnaGroup,
  DnaTuple,
} from './narrativeDnaData';
import { JEEVES_DNA_GROUPS_DATA, JEEVES_DNA_KEYS, JEEVES_DNA_TOTAL } from './jeevesDnaData';
import { ACADEMY_DNA_GROUPS_DATA, ACADEMY_DNA_KEYS, ACADEMY_DNA_TOTAL } from './academyDnaData';
import {
  BUILDER_CATEGORIES, BUILDER_DNA_BY_CATEGORY, BUILDER_DNA_KEYS_BY_CATEGORY,
  BUILDER_DNA_TOTAL_PER_CATEGORY, BUILDER_DNA_TOTAL_ALL,
} from './builderDnaData';

// ── Coding (editor + metronome) ──────────────────────────────────────
export interface CodingSettings {
  metronomeEnabled: boolean;
  metronomeBpm: number;
  metronomeSound: 'click' | 'tick' | 'beep' | 'silent';
  metronomeBeatsPerBar: 3 | 4 | 6 | 7 | 8;
  metronomeVisual: boolean;
  metronomeVolume: number;
  metronomeAccentDownbeat: boolean;
  metronomeAutoStopMin: number;
  bracketPairColors: boolean;
  autoIndent: boolean;
  showSnippetsPalette: boolean;
  aiExplainEnabled: boolean;
  showLineNumbers: boolean;
  tabSize: 2 | 4;
}

// ── Jeeves ────────────────────────────────────────────────────────────
export interface JeevesSettings {
  blurbVision: string;
  blurbStyle: string;
  blurbRules: string;
  enforceOnEveryRequest: boolean;
  bulkOrders: string[];
  agentPersona: 'precise' | 'creative' | 'educator' | 'debugger' | 'strict';
  creativity: number;
  verbosity: number;
  /** 100-slider mastery cockpit (key → 0.0..3.0, default 1.0). */
  masteryDna: Record<string, number>;
}

// ── Academy (audiobook TTS) ──────────────────────────────────────────
export interface AcademySettings {
  ttsEnabled: boolean;
  audiobookMode: boolean;
  ttsRate: number;
  ttsPitch: number;
  autoAdvance: boolean;
  readCodeBlocks: boolean;
  voiceLang: string;
  voiceIdentifier: string;
  voiceGender: 'male' | 'female' | 'any';
  fontSize: number;
  lineHeight: number;
  highContrast: boolean;
  jeevesPersonaEnabled?: boolean;
  /** 🎙️ Cinematic HD voice — routes Jeeves & narration through the immersive
   *  tts-1-hd backend (storyteller cadence + tone control) instead of the
   *  robotic on-device voice. Default ON for "innlevelse". */
  cinematicVoice?: boolean;
  /** Active expressive tone preset for Jeeves (butler/storyteller/dramatic/…). */
  jeevesTone?: string;
  /** 100-slider mastery cockpit (key → 0.0..3.0, default 1.0). */
  masteryDna: Record<string, number>;
}

// ── Galaxy Studio (phase weights + 500-slider Narrative DNA) ─────────
export interface GalaxyStudioSettings {
  /**
   * 10 per-category emphasis sliders (0.0-3.0).
   * 0 = skip the batch entirely, 1 = default, 2 = 2×, 3 = 3×.
   */
  phaseWeights: {
    foundation: number;
    core_mechanics: number;
    world_environment: number;
    audio_visual: number;
    ai_behavior: number;
    systems_network: number;
    content_depth: number;
    polish_quality: number;
    testing_security: number;
    final_assembly: number;
  };
  fileSizePreferenceKb: number;
  autoArchiveAfterMin: number;
  confirmDestructive: boolean;
  /**
   * Narrative DNA — 500 sliders steering the *story* of a generated build.
   * Each runs 0.0 (skip / absent) → 3.0 (saturate). 1.0 = default.
   * Grouped into 30 categories by /state/narrativeDnaData.ts.
   * Sent to the build pipeline as a flat `narrative_dna` object
   * alongside `phase_weights`.
   *
   * Stored as Record<string, number> so adding new keys never breaks
   * existing persisted snapshots — missing keys back-fill to 1.0 on read.
   */
  narrativeDNA: Record<string, number>;
}

/** Alias kept for backwards compatibility with older imports. */
export type NarrativeDnaKey = string;

// ── Builder (CodeToApp / AI Game Gen — 100 sliders × 6 categories) ───
export interface BuilderSettings {
  /** Per-category map of slider key → 0.0..3.0 (default 1.0). */
  dnaByCategory: Record<string, Record<string, number>>;
}

// ── Combined store ───────────────────────────────────────────────────
export interface SettingsState {
  jeeves: JeevesSettings;
  academy: AcademySettings;
  galaxyStudio: GalaxyStudioSettings;
  coding: CodingSettings;
  builder: BuilderSettings;
  resetAll: () => void;
  resetJeeves: () => void;
  resetAcademy: () => void;
  resetGalaxyStudio: () => void;
  resetCoding: () => void;
  setJeeves: (patch: Partial<JeevesSettings>) => void;
  setAcademy: (patch: Partial<AcademySettings>) => void;
  setGalaxyStudio: (patch: Partial<GalaxyStudioSettings>) => void;
  setCoding: (patch: Partial<CodingSettings>) => void;
  setPhaseWeight: (key: keyof GalaxyStudioSettings['phaseWeights'], v: number) => void;
  setNarrativeDna: (key: string, v: number) => void;
  resetNarrativeDna: () => void;
  resetNarrativeDnaGroup: (groupId: string) => void;
  addBulkOrder: (order: string) => void;
  removeBulkOrder: (index: number) => void;
  clearBulkOrders: () => void;
  setJeevesDna: (key: string, v: number) => void;
  resetJeevesDna: () => void;
  resetJeevesDnaGroup: (groupId: string) => void;
  setAcademyDna: (key: string, v: number) => void;
  resetAcademyDna: () => void;
  resetAcademyDnaGroup: (groupId: string) => void;
  setBuilderDna: (category: string, key: string, v: number) => void;
  resetBuilderDnaCategory: (category: string) => void;
  resetBuilderDnaGroup: (category: string, groupId: string) => void;
  resetBuilderDnaAll: () => void;
}

const DEFAULT_JEEVES_DNA: Record<string, number> =
  JEEVES_DNA_KEYS.reduce((acc, k) => { acc[k] = 1.0; return acc; }, {} as Record<string, number>);
const DEFAULT_ACADEMY_DNA: Record<string, number> =
  ACADEMY_DNA_KEYS.reduce((acc, k) => { acc[k] = 1.0; return acc; }, {} as Record<string, number>);

const DEFAULT_BUILDER_DNA_BY_CAT: Record<string, Record<string, number>> =
  Object.keys(BUILDER_DNA_KEYS_BY_CATEGORY).reduce((acc, catKey) => {
    acc[catKey] = BUILDER_DNA_KEYS_BY_CATEGORY[catKey].reduce(
      (m, k) => { m[k] = 1.0; return m; },
      {} as Record<string, number>,
    );
    return acc;
  }, {} as Record<string, Record<string, number>>);

const DEFAULT_BUILDER: BuilderSettings = {
  dnaByCategory: Object.fromEntries(
    Object.entries(DEFAULT_BUILDER_DNA_BY_CAT).map(([k, v]) => [k, { ...v }]),
  ),
};

const DEFAULT_JEEVES: JeevesSettings = {
  blurbVision: '',
  blurbStyle: '',
  blurbRules: '',
  enforceOnEveryRequest: false,
  bulkOrders: [],
  agentPersona: 'precise',
  creativity: 0.4,
  verbosity: 3,
  masteryDna: { ...DEFAULT_JEEVES_DNA },
};

const DEFAULT_ACADEMY: AcademySettings = {
  ttsEnabled: false,
  audiobookMode: false,
  ttsRate: 0.95,
  ttsPitch: 0.9,
  autoAdvance: true,
  readCodeBlocks: false,
  voiceLang: 'en-US',
  voiceIdentifier: '',
  voiceGender: 'male',
  fontSize: 15,
  lineHeight: 1.5,
  highContrast: false,
  jeevesPersonaEnabled: true,
  cinematicVoice: true,
  jeevesTone: 'butler',
  masteryDna: { ...DEFAULT_ACADEMY_DNA },
};

const DEFAULT_NARRATIVE_DNA: Record<string, number> =
  DNA_KEYS_FROM_DATA.reduce((acc, k) => { acc[k] = 1.0; return acc; }, {} as Record<string, number>);

const DEFAULT_GALAXY: GalaxyStudioSettings = {
  phaseWeights: {
    foundation: 1.0,
    core_mechanics: 1.0,
    world_environment: 1.0,
    audio_visual: 1.0,
    ai_behavior: 1.0,
    systems_network: 1.0,
    content_depth: 1.0,
    polish_quality: 1.0,
    testing_security: 1.0,
    final_assembly: 1.0,
  },
  fileSizePreferenceKb: 160,
  autoArchiveAfterMin: 60,
  confirmDestructive: true,
  narrativeDNA: { ...DEFAULT_NARRATIVE_DNA },
};

const DEFAULT_CODING: CodingSettings = {
  metronomeEnabled: false,
  metronomeBpm: 90,
  metronomeSound: 'click',
  metronomeBeatsPerBar: 4,
  metronomeVisual: true,
  metronomeVolume: 0.6,
  metronomeAccentDownbeat: true,
  metronomeAutoStopMin: 0,
  bracketPairColors: true,
  autoIndent: true,
  showSnippetsPalette: true,
  aiExplainEnabled: true,
  showLineNumbers: true,
  tabSize: 2,
};

/** Back-fill missing keys with 1.0 so additions to the cockpit don't blank existing snapshots. */
function hydrateNarrativeDna(stored: Partial<Record<string, number>> | undefined): Record<string, number> {
  const out: Record<string, number> = { ...DEFAULT_NARRATIVE_DNA };
  if (stored) {
    for (const k of Object.keys(stored)) {
      const v = stored[k];
      if (typeof v === 'number' && Number.isFinite(v)) out[k] = v;
    }
  }
  return out;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      jeeves: DEFAULT_JEEVES,
      academy: DEFAULT_ACADEMY,
      galaxyStudio: DEFAULT_GALAXY,
      coding: DEFAULT_CODING,
      builder: DEFAULT_BUILDER,

      resetAll: () => set({
        jeeves: DEFAULT_JEEVES,
        academy: DEFAULT_ACADEMY,
        galaxyStudio: DEFAULT_GALAXY,
        coding: DEFAULT_CODING,
        builder: DEFAULT_BUILDER,
      }),
      resetJeeves: () => set({ jeeves: DEFAULT_JEEVES }),
      resetAcademy: () => set({ academy: DEFAULT_ACADEMY }),
      resetGalaxyStudio: () => set({ galaxyStudio: DEFAULT_GALAXY }),
      resetCoding: () => set({ coding: DEFAULT_CODING }),

      setJeeves: (patch) => set(s => ({ jeeves: { ...s.jeeves, ...patch } })),
      setAcademy: (patch) => set(s => ({ academy: { ...s.academy, ...patch } })),
      setGalaxyStudio: (patch) => set(s => ({ galaxyStudio: { ...s.galaxyStudio, ...patch } })),
      setCoding: (patch) => set(s => ({ coding: { ...s.coding, ...patch } })),
      setPhaseWeight: (key, v) => set(s => ({
        galaxyStudio: { ...s.galaxyStudio, phaseWeights: { ...s.galaxyStudio.phaseWeights, [key]: v } },
      })),
      setNarrativeDna: (key, v) => set(s => ({
        galaxyStudio: { ...s.galaxyStudio, narrativeDNA: { ...s.galaxyStudio.narrativeDNA, [key]: v } },
      })),
      resetNarrativeDna: () => set(s => ({
        galaxyStudio: { ...s.galaxyStudio, narrativeDNA: { ...DEFAULT_NARRATIVE_DNA } },
      })),
      resetNarrativeDnaGroup: (groupId) => set(s => {
        const grp = NARRATIVE_DNA_GROUPS_DATA.find(g => g.id === groupId);
        if (!grp) return s;
        const dna = { ...s.galaxyStudio.narrativeDNA };
        for (const it of grp.items) dna[it[0]] = 1.0;
        return { galaxyStudio: { ...s.galaxyStudio, narrativeDNA: dna } };
      }),
      addBulkOrder: (order) => set(s => ({ jeeves: { ...s.jeeves, bulkOrders: [...s.jeeves.bulkOrders, order] } })),
      removeBulkOrder: (index) => set(s => ({
        jeeves: { ...s.jeeves, bulkOrders: s.jeeves.bulkOrders.filter((_, i) => i !== index) },
      })),
      clearBulkOrders: () => set(s => ({ jeeves: { ...s.jeeves, bulkOrders: [] } })),
      // ── 100-slider mastery cockpits (Jeeves / Academy) ──────────────
      setJeevesDna: (key: string, v: number) => set(s => ({
        jeeves: { ...s.jeeves, masteryDna: { ...s.jeeves.masteryDna, [key]: v } },
      })),
      resetJeevesDna: () => set(s => ({ jeeves: { ...s.jeeves, masteryDna: { ...DEFAULT_JEEVES_DNA } } })),
      resetJeevesDnaGroup: (groupId: string) => set(s => {
        const grp = JEEVES_DNA_GROUPS_DATA.find(g => g.id === groupId);
        if (!grp) return s;
        const dna = { ...s.jeeves.masteryDna };
        for (const it of grp.items) dna[it[0]] = 1.0;
        return { jeeves: { ...s.jeeves, masteryDna: dna } };
      }),
      setAcademyDna: (key: string, v: number) => set(s => ({
        academy: { ...s.academy, masteryDna: { ...s.academy.masteryDna, [key]: v } },
      })),
      resetAcademyDna: () => set(s => ({ academy: { ...s.academy, masteryDna: { ...DEFAULT_ACADEMY_DNA } } })),
      resetAcademyDnaGroup: (groupId: string) => set(s => {
        const grp = ACADEMY_DNA_GROUPS_DATA.find(g => g.id === groupId);
        if (!grp) return s;
        const dna = { ...s.academy.masteryDna };
        for (const it of grp.items) dna[it[0]] = 1.0;
        return { academy: { ...s.academy, masteryDna: dna } };
      }),
      // ── Builder (100 sliders × N categories) ────────────────────────
      setBuilderDna: (category: string, key: string, v: number) => set(s => {
        const cat = s.builder.dnaByCategory[category] || {};
        return {
          builder: {
            ...s.builder,
            dnaByCategory: {
              ...s.builder.dnaByCategory,
              [category]: { ...cat, [key]: v },
            },
          },
        };
      }),
      resetBuilderDnaCategory: (category: string) => set(s => {
        const fresh = { ...(DEFAULT_BUILDER_DNA_BY_CAT[category] || {}) };
        return {
          builder: {
            ...s.builder,
            dnaByCategory: { ...s.builder.dnaByCategory, [category]: fresh },
          },
        };
      }),
      resetBuilderDnaGroup: (category: string, groupId: string) => set(s => {
        const groups = BUILDER_DNA_BY_CATEGORY[category] || [];
        const grp = groups.find(g => g.id === groupId);
        if (!grp) return s;
        const cat = { ...(s.builder.dnaByCategory[category] || {}) };
        for (const it of grp.items) cat[it[0]] = 1.0;
        return {
          builder: {
            ...s.builder,
            dnaByCategory: { ...s.builder.dnaByCategory, [category]: cat },
          },
        };
      }),
      resetBuilderDnaAll: () => set({ builder: DEFAULT_BUILDER }),
    }),
    {
      name: 'codedock-settings-v1',
      storage: createJSONStorage(() => AsyncStorage),
      // After rehydration, back-fill the Narrative DNA map so newly-added
      // slider keys land on their 1.0 default instead of `undefined`.
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        state.galaxyStudio = {
          ...state.galaxyStudio,
          narrativeDNA: hydrateNarrativeDna(state.galaxyStudio?.narrativeDNA),
        };
        // Back-fill the 100-slider Jeeves & Academy cockpits so newly added
        // keys land on their 1.0 default instead of `undefined`.
        const hydrateMap = (defaults: Record<string, number>, stored: any): Record<string, number> => {
          const out = { ...defaults };
          if (stored && typeof stored === 'object') {
            for (const k of Object.keys(stored)) {
              const v = stored[k];
              if (typeof v === 'number' && Number.isFinite(v)) out[k] = v;
            }
          }
          return out;
        };
        state.jeeves = { ...state.jeeves, masteryDna: hydrateMap(DEFAULT_JEEVES_DNA, state.jeeves?.masteryDna) };
        state.academy = { ...state.academy, masteryDna: hydrateMap(DEFAULT_ACADEMY_DNA, state.academy?.masteryDna) };
        // Builder — backfill each per-category cockpit so new sliders land
        // on their 1.0 default without wiping the user's prior overrides.
        const builderCats: Record<string, Record<string, number>> = {};
        for (const catKey of Object.keys(DEFAULT_BUILDER_DNA_BY_CAT)) {
          const stored = state.builder?.dnaByCategory?.[catKey];
          builderCats[catKey] = hydrateMap(DEFAULT_BUILDER_DNA_BY_CAT[catKey], stored);
        }
        state.builder = { ...(state.builder || {}), dnaByCategory: builderCats };
      },
    }
  )
);

/** Convenience selector — get the backend-shaped phase_weights payload. */
export function getPhaseWeightsPayload(): Record<string, number> {
  const pw = useSettings.getState().galaxyStudio.phaseWeights;
  return {
    foundation: pw.foundation,
    core_mechanics: pw.core_mechanics,
    'world_&_environment': pw.world_environment,
    'audio_&_visual': pw.audio_visual,
    'ai_&_behavior': pw.ai_behavior,
    'systems_&_network': pw.systems_network,
    'content_&_depth': pw.content_depth,
    'polish_&_quality': pw.polish_quality,
    'testing_&_security': pw.testing_security,
    final_assembly: pw.final_assembly,
  };
}

/**
 * Convenience selector — get the backend-shaped narrative_dna payload.
 * Only includes sliders whose value has drifted from the default 1.0
 * (keeps the request body small; server defaults anything missing).
 */
export function getNarrativeDnaPayload(): Record<string, number> {
  const dna = useSettings.getState().galaxyStudio.narrativeDNA || {};
  const out: Record<string, number> = {};
  for (const k of DNA_KEYS_FROM_DATA) {
    const v = dna[k];
    if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) out[k] = v;
  }
  return out;
}

/** How many sliders are non-default — used by the cockpit "drift" badge. */
export function getNarrativeDnaDriftCount(): number {
  const dna = useSettings.getState().galaxyStudio.narrativeDNA || {};
  let n = 0;
  for (const k of DNA_KEYS_FROM_DATA) {
    const v = dna[k];
    if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) n += 1;
  }
  return n;
}

/** Build a concatenated system-prompt prefix from the 3 Jeeves blurbs. */
export function getJeevesSystemPrefix(): string {
  const j = useSettings.getState().jeeves;
  if (!j.enforceOnEveryRequest) return '';
  const parts: string[] = [];
  if (j.blurbVision.trim()) parts.push(`VISION: ${j.blurbVision.trim()}`);
  if (j.blurbStyle.trim()) parts.push(`STYLE: ${j.blurbStyle.trim()}`);
  if (j.blurbRules.trim()) parts.push(`RULES (MUST OBEY): ${j.blurbRules.trim()}`);
  if (j.bulkOrders.length > 0)
    parts.push(`BULK ORDERS:\n${j.bulkOrders.map((o, i) => `${i + 1}. ${o}`).join('\n')}`);
  parts.push(`PERSONA: ${j.agentPersona} | creativity=${j.creativity.toFixed(2)} | verbosity=${j.verbosity}/5`);
  return parts.join('\n\n');
}

export const BATCH_LABELS: Record<keyof GalaxyStudioSettings['phaseWeights'], { label: string; icon: string; color: string; hint: string }> = {
  foundation:        { label: 'Foundation',       icon: 'layers',       color: '#3B82F6', hint: 'Architecture, scaffolding, base systems' },
  core_mechanics:    { label: 'Core Mechanics',   icon: 'game-controller', color: '#10B981', hint: 'Gameplay loops, controls, progression' },
  world_environment: { label: 'World & Environment', icon: 'earth',    color: '#F59E0B', hint: 'Levels, biomes, weather, terrain' },
  audio_visual:      { label: 'Audio & Visual',   icon: 'color-palette', color: '#EC4899', hint: 'Graphics, VFX, music, SFX' },
  ai_behavior:       { label: 'AI & Behavior',    icon: 'bulb',         color: '#8B5CF6', hint: 'NPC intel, decision trees, dialogue' },
  systems_network:   { label: 'Systems & Network', icon: 'git-network',  color: '#06B6D4', hint: 'Multiplayer, saves, backend, cloud' },
  content_depth:     { label: 'Content & Depth',  icon: 'albums',       color: '#0EA5E9', hint: 'Quests, lore, collectibles, endgame' },
  polish_quality:    { label: 'Polish & Quality', icon: 'sparkles',     color: '#F97316', hint: 'UX polish, juice, feedback loops' },
  testing_security:  { label: 'Testing & Security', icon: 'shield-checkmark', color: '#EF4444', hint: 'QA suites, exploits, anti-cheat' },
  final_assembly:    { label: 'Final Assembly',   icon: 'cube',         color: '#14B8A6', hint: 'Packaging, optimize, ship' },
};

/** Re-export the cockpit data for /settings/galaxy-studio to render. */
export const NARRATIVE_DNA_GROUPS = NARRATIVE_DNA_GROUPS_DATA;
export const NARRATIVE_DNA_KEYS = DNA_KEYS_FROM_DATA;
export { NARRATIVE_DNA_TOTAL };
export type { DnaGroup, DnaTuple };

/** Re-export 100-slider cockpit data for Jeeves + Academy settings to render. */
export const JEEVES_DNA_GROUPS = JEEVES_DNA_GROUPS_DATA;
export const ACADEMY_DNA_GROUPS = ACADEMY_DNA_GROUPS_DATA;
export { JEEVES_DNA_TOTAL, ACADEMY_DNA_TOTAL, JEEVES_DNA_KEYS, ACADEMY_DNA_KEYS };

/** Drift counters for the cockpit banners. */
export function getJeevesDnaDriftCount(): number {
  const dna = useSettings.getState().jeeves.masteryDna || {};
  let n = 0;
  for (const k of JEEVES_DNA_KEYS) {
    const v = dna[k];
    if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) n += 1;
  }
  return n;
}
export function getAcademyDnaDriftCount(): number {
  const dna = useSettings.getState().academy.masteryDna || {};
  let n = 0;
  for (const k of ACADEMY_DNA_KEYS) {
    const v = dna[k];
    if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) n += 1;
  }
  return n;
}

/** Builder DNA cockpit re-exports (used by CodeToAppModal). */
export {
  BUILDER_CATEGORIES,
  BUILDER_DNA_BY_CATEGORY,
  BUILDER_DNA_KEYS_BY_CATEGORY,
  BUILDER_DNA_TOTAL_PER_CATEGORY,
  BUILDER_DNA_TOTAL_ALL,
};
export function getBuilderDnaDriftCount(category?: string): number {
  const map = useSettings.getState().builder.dnaByCategory || {};
  let n = 0;
  if (category) {
    const cat = map[category] || {};
    for (const k of (BUILDER_DNA_KEYS_BY_CATEGORY[category] || [])) {
      const v = cat[k];
      if (typeof v === 'number' && Math.abs(v - 1.0) > 0.001) n += 1;
    }
    return n;
  }
  for (const c of Object.keys(BUILDER_DNA_KEYS_BY_CATEGORY)) {
    n += getBuilderDnaDriftCount(c);
  }
  return n;
}
