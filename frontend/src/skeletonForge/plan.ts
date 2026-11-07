/**
 * Build-plan viewer view-model over the `build_plan` block of
 * POST /api/skeleton/run (skeleton/jeeves/builder.py `BuildPlan.to_dict`).
 *
 * The plan is what Jeeves hands the forge: era, seed, room bias, spawn kit,
 * extraction timing, enemy mix and recipes, plus free-form notes the builder
 * emits from its left-brain veto (`left-veto thermal_span=…`) and cortex
 * adaptation (`cortex: slack=… — …`). This module turns that loosely typed
 * block into something the UI can render and screen readers can announce,
 * and links the plan back to the era catalogue (GET /api/skeleton/eras).
 *
 * Everything is defensive: older servers omit fields, and notes are
 * human strings, so parsing never throws and unknown notes pass through.
 */
import { baseEra, eraViews, type EraView } from './eras';
import { humanize } from './graph';
import type { Tone } from './run';
import type { EraRow, RunPayload, StageRow } from './types';

/** Server-side shape (BuildPlan.to_dict). All optional on the wire. */
export interface BuildPlanWire {
  era?: string;
  seed?: string;
  tensor_fp?: string;
  oracle_index?: number;
  oracle_text?: string;
  briefing?: string;
  room_bias?: string;
  spawn_weapon?: boolean;
  extract_late?: boolean;
  enemy_mix?: Record<string, number>;
  recipes?: string[];
  notes?: string[];
  adapt?: string;
  slack?: number;
  authored?: string;
  [k: string]: unknown;
}

export type EnemyTier = 'trash' | 'elite' | 'boss';
export const ENEMY_TIERS: readonly EnemyTier[] = ['trash', 'elite', 'boss'];

/** Room bias copy (builder `_bias_of`: loot | heat | combat | balanced). */
export const BIAS_COPY: Record<string, { label: string; glyph: string; detail: string }> = {
  loot: { label: 'Loot', glyph: '◆', detail: 'Rooms lean toward caches and salvage.' },
  heat: { label: 'Heat', glyph: '▲', detail: 'Rooms lean toward pressure and the collapse timer.' },
  combat: { label: 'Combat', glyph: '✦', detail: 'Rooms lean toward fights.' },
  balanced: { label: 'Balanced', glyph: '●', detail: 'No room type is favoured.' },
};

/** Cortex adaptation tags (builder `adapt_from_walk`). */
export const ADAPT_COPY: Record<string, { label: string; tone: Tone; detail: string }> = {
  none: { label: 'No adaptation', tone: 'idle', detail: 'No prior walk was available, so the plan is first-principles.' },
  ease: { label: 'Eased', tone: 'warn', detail: 'The last walk failed to extract, so the plan arms the spawn and drops the late extract.' },
  tighten: { label: 'Tightened', tone: 'warn', detail: 'The last walk extracted with little time to spare, so the late extract was dropped.' },
  harden: { label: 'Hardened', tone: 'ok', detail: 'The last walk was comfortable, so the enemy mix was raised.' },
  hold: { label: 'Held', tone: 'ok', detail: 'The last walk was in the target band, so the plan keeps its shape.' },
};

export type NoteKind = 'veto' | 'cortex' | 'invented' | 'fact' | 'other';

export interface PlanNote {
  kind: NoteKind;
  text: string;
  /** For `key=value` facts. */
  key?: string;
  value?: string;
}

export interface VetoView {
  /** fits: mix fits the thermal budget unchanged; pruned: tiers dropped; irreducible: still over budget. */
  state: 'fits' | 'pruned' | 'irreducible' | 'unknown';
  tone: Tone;
  label: string;
  /** Sequential thermal kill time in seconds. */
  spanS: number | null;
  /** 70% of collapse_max, when the note carries it. */
  budgetS: number | null;
  dropped: EnemyTier[];
}

export interface MixRow {
  tier: EnemyTier;
  label: string;
  count: number;
  /** Per-kill TTK from the linked era, seconds. */
  ttkS: number | null;
  /** count × ttk (naive, ignores heat carry-over). */
  subtotalS: number | null;
}

export interface EraLink {
  /** match: plan era == run era; blend: run era is a blend whose base is the plan era; drift: they differ; unknown: missing. */
  relation: 'match' | 'blend' | 'drift' | 'unknown';
  tone: Tone;
  label: string;
  planEra: string | null;
  runEra: string | null;
  pinnedEra: string | null;
  /** Plan era honours the era pinned in the questionnaire (null when none pinned). */
  honoursPin: boolean | null;
  /** Catalogue row for the plan era, when the catalogue is loaded. */
  era: EraView | null;
}

export interface PlanView {
  present: boolean;
  era: string | null;
  eraLabel: string;
  seed: string | null;
  tensorFp: string | null;
  oracleIndex: number | null;
  oracleText: string | null;
  briefing: string | null;
  bias: string;
  biasLabel: string;
  biasGlyph: string;
  biasDetail: string;
  armed: boolean | null;
  extractLate: boolean | null;
  mix: MixRow[];
  totalEnemies: number;
  /** Sum of per-tier subtotals; null when the era TTK is unknown. */
  naiveCombatS: number | null;
  recipes: string[];
  notes: PlanNote[];
  adapt: string;
  adaptLabel: string;
  adaptTone: Tone;
  adaptDetail: string;
  /** 0..1 share of collapse time left on the last walk. */
  slack: number | null;
  authored: string | null;
  veto: VetoView;
  link: EraLink;
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);
const bool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);

/** Classify one builder note. Never throws. */
export function classifyNote(raw: unknown): PlanNote {
  const text = String(raw ?? '').trim();
  if (/^left-veto\b/.test(text)) return { kind: 'veto', text };
  if (/^cortex:/.test(text)) return { kind: 'cortex', text };
  if (/^(invented|improved)\b/.test(text)) return { kind: 'invented', text };
  const kv = /^([a-z_]+)=(\S.*)$/i.exec(text);
  if (kv && !kv[2].includes('=')) return { kind: 'fact', text, key: kv[1], value: kv[2] };
  return { kind: 'other', text };
}

const TIER_SET = new Set<string>(ENEMY_TIERS);

/** Read the left-brain veto verdict from the notes (builder `_prune_mix`). */
export function vetoFromNotes(notes: PlanNote[]): VetoView {
  const veto = notes.filter((n) => n.kind === 'veto');
  for (let i = veto.length - 1; i >= 0; i--) {
    const t = veto[i].text;
    const span = /thermal_span=([\d.]+)s/.exec(t);
    const spanS = span ? Number(span[1]) : null;
    if (/mix irreducible/.test(t)) {
      return { state: 'irreducible', tone: 'bad', label: 'Mix still over the thermal budget', spanS, budgetS: null, dropped: [] };
    }
    const dropped = /dropped ([a-z,]+)/.exec(t);
    if (dropped) {
      const tiers = dropped[1].split(',').filter((x): x is EnemyTier => TIER_SET.has(x));
      return { state: 'pruned', tone: 'warn', label: `Veto dropped ${tiers.length} ${tiers.length === 1 ? 'enemy' : 'enemies'} to fit`, spanS, budgetS: null, dropped: tiers };
    }
    const budget = /thermal_span=([\d.]+)s\/([\d.]+)s/.exec(t);
    if (budget) {
      return { state: 'fits', tone: 'ok', label: 'Mix fits the thermal budget', spanS: Number(budget[1]), budgetS: Number(budget[2]), dropped: [] };
    }
  }
  return { state: 'unknown', tone: 'idle', label: 'No veto verdict reported', spanS: null, budgetS: null, dropped: [] };
}

/** Per-tier rows, canonical order first, then any extra tiers the server sent. */
function mixRows(mix: Record<string, unknown> | undefined, era: EraView | null, eraRow: EraRow | undefined): MixRow[] {
  const rows: MixRow[] = [];
  const seen = new Set<string>();
  const ttkFor = (tier: string): number | null => {
    if (tier === 'trash') return era?.ttkTrash ?? null;
    if (tier === 'elite') return era?.ttkElite ?? null;
    if (tier === 'boss') return era?.ttkBoss ?? null;
    return num(eraRow?.ttk?.[tier]);
  };
  const push = (tier: string) => {
    seen.add(tier);
    const count = Math.max(0, Math.round(num(mix?.[tier]) ?? 0));
    const ttkS = ttkFor(tier);
    rows.push({ tier: tier as EnemyTier, label: humanize(tier), count, ttkS, subtotalS: ttkS === null ? null : round1(count * ttkS) });
  };
  for (const t of ENEMY_TIERS) push(t);
  for (const k of Object.keys(mix ?? {})) if (!seen.has(k) && num(mix?.[k]) !== null) push(k);
  return rows;
}

function round1(v: number): number {
  return Math.round(v * 10) / 10;
}

/** How the plan's era relates to the run's era and the questionnaire pin. */
export function eraLink(planEra: string | null, runEra: string | null, pinnedEra: string | null, era: EraView | null): EraLink {
  const pinBase = baseEra(pinnedEra);
  const honoursPin = pinBase ? baseEra(planEra) === pinBase : null;
  const common = { planEra, runEra, pinnedEra, honoursPin, era };
  if (!planEra || !runEra) {
    return { ...common, relation: 'unknown', tone: 'idle', label: planEra ? `Plan era ${humanize(planEra)}` : 'Plan era not reported' };
  }
  if (planEra === runEra) return { ...common, relation: 'match', tone: 'ok', label: `Plan built for ${humanize(planEra)}` };
  if (baseEra(runEra) === baseEra(planEra)) {
    return { ...common, relation: 'blend', tone: 'ok', label: `Plan built for ${humanize(planEra)}; run blended to ${humanize(runEra)}` };
  }
  return { ...common, relation: 'drift', tone: 'warn', label: `Plan era ${humanize(planEra)} differs from run era ${humanize(runEra)}` };
}

/** Full plan view. `eras` links the plan to the catalogue for TTK estimates. */
export function planView(payload: RunPayload | null | undefined, eras: EraRow[] = [], pinnedEra: string | null = null): PlanView {
  const raw = (payload?.build_plan ?? null) as BuildPlanWire | null;
  const present = !!raw && typeof raw === 'object';
  const p: BuildPlanWire = present ? (raw as BuildPlanWire) : {};
  const eraId = str(p.era) ?? str(payload?.era) ?? null;
  const base = baseEra(eraId);
  const views = eraViews(eras);
  const eraV = views.find((v) => v.id === eraId) ?? views.find((v) => v.id === base) ?? null;
  const eraRow = eras.find((r) => r.id === eraV?.id);
  const notes = (Array.isArray(p.notes) ? p.notes : []).map(classifyNote).filter((n) => n.text);
  const mix = mixRows(p.enemy_mix && typeof p.enemy_mix === 'object' ? p.enemy_mix : undefined, eraV, eraRow);
  const withCount = mix.filter((m) => m.count > 0);
  const naive = withCount.length && withCount.every((m) => m.subtotalS !== null)
    ? round1(withCount.reduce((a, m) => a + (m.subtotalS as number), 0))
    : withCount.length ? null : 0;
  const bias = str(p.room_bias) ?? 'balanced';
  const biasMeta = BIAS_COPY[bias] ?? { label: humanize(bias), glyph: '●', detail: 'Custom room bias.' };
  const adapt = str(p.adapt) ?? 'none';
  const adaptMeta = ADAPT_COPY[adapt] ?? { label: humanize(adapt), tone: 'idle' as Tone, detail: 'Custom adaptation tag.' };
  const slack = num(p.slack);
  return {
    present,
    era: eraId,
    eraLabel: eraId ? humanize(eraId) : '—',
    seed: str(p.seed),
    tensorFp: str(p.tensor_fp),
    oracleIndex: num(p.oracle_index),
    oracleText: str(p.oracle_text),
    briefing: str(p.briefing),
    bias,
    biasLabel: biasMeta.label,
    biasGlyph: biasMeta.glyph,
    biasDetail: biasMeta.detail,
    armed: bool(p.spawn_weapon),
    extractLate: bool(p.extract_late),
    mix,
    totalEnemies: mix.reduce((a, m) => a + m.count, 0),
    naiveCombatS: naive,
    recipes: (Array.isArray(p.recipes) ? p.recipes : []).map((r) => String(r)).filter(Boolean),
    notes,
    adapt,
    adaptLabel: adaptMeta.label,
    adaptTone: adaptMeta.tone,
    adaptDetail: adaptMeta.detail,
    slack: slack === null ? null : Math.max(0, Math.min(1, slack)),
    authored: str(p.authored),
    veto: vetoFromNotes(notes),
    link: eraLink(str(p.era), str(payload?.era), pinnedEra, eraV),
  };
}

/** Stages that produce or consume the plan (skeleton/context/pipeline.py). */
export const PLAN_STAGES = ['oracle', 'jeeves', 'sim'] as const;

export interface PlanStatus {
  state: 'empty' | 'planning' | 'ready' | 'degraded' | 'failed';
  tone: Tone;
  label: string;
  /** Stage-by-stage readout for the plan's producing stages. */
  stages: { name: string; status: string }[];
}

/**
 * Plan lifecycle: `planning` while a run is in flight, `failed` when a plan
 * stage failed, `degraded` when the plan exists but sim failed or the veto
 * could not fit the mix, otherwise `ready`.
 */
export function planStatus(payload: RunPayload | null | undefined, running = false, plan: PlanView = planView(payload)): PlanStatus {
  const rows: StageRow[] = payload?.run?.stages ?? [];
  const stages = PLAN_STAGES.map((name) => {
    const r = rows.find((x) => x.name === name);
    return { name, status: String(r?.status ?? (running ? 'queued' : 'not run')).toLowerCase() };
  });
  if (running) return { state: 'planning', tone: 'idle', label: 'Jeeves is drafting the plan…', stages };
  if (!payload) return { state: 'empty', tone: 'idle', label: 'No plan yet', stages };
  const failed = stages.find((s) => s.status === 'failed');
  if (failed && failed.name !== 'sim') return { state: 'failed', tone: 'bad', label: `Plan stage “${failed.name}” failed`, stages };
  if (!plan.present) return { state: 'empty', tone: 'idle', label: 'This run returned no build plan', stages };
  if (failed || payload.sim?.passed === false) return { state: 'degraded', tone: 'warn', label: 'Plan drafted, encounter simulation failed', stages };
  if (plan.veto.state === 'irreducible') return { state: 'degraded', tone: 'warn', label: 'Plan drafted, mix exceeds the thermal budget', stages };
  return { state: 'ready', tone: 'ok', label: 'Plan ready', stages };
}

export function formatSeconds(v: number | null): string {
  if (v === null) return '—';
  return v >= 60 ? `${Math.floor(v / 60)}m ${String(Math.round(v % 60)).padStart(2, '0')}s` : `${round1(v)}s`;
}

/** One-sentence screen-reader summary of the plan. */
export function describePlan(v: PlanView): string {
  if (!v.present) return 'No build plan.';
  const mix = v.mix.filter((m) => m.count > 0).map((m) => `${m.count} ${m.label.toLowerCase()}`).join(', ') || 'no enemies';
  const kit = v.armed === null ? '' : v.armed ? ' Spawn armed.' : ' Spawn unarmed.';
  const ext = v.extractLate === null ? '' : v.extractLate ? ' Late extraction.' : ' Early extraction.';
  return `Build plan for ${v.eraLabel}: ${v.biasLabel.toLowerCase()} room bias, enemy mix ${mix}.${kit}${ext} ${v.veto.label}.`;
}
