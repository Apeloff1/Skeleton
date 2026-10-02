/**
 * Pure view-model for the Skeleton Forge cockpit screen: tab navigation,
 * deep links, per-tab status badges, console history recall and the
 * cross-panel handoffs (era → questionnaire, run → run tab).
 *
 * Kept free of React / network imports so it is trivially testable.
 */
import type { RunPhase } from './hooks';
import type { Tone } from './run';
import type { ComposeResult } from './types';

export const COCKPIT_TABS = ['build', 'compose', 'run', 'eras', 'console'] as const;
export type CockpitTab = typeof COCKPIT_TABS[number];

export const COCKPIT_TAB_LABELS: Record<CockpitTab, string> = {
  build: 'Questionnaire',
  compose: 'Compose graph',
  run: 'Forge run',
  eras: 'Eras',
  console: 'Console',
};

export const COCKPIT_TAB_HINTS: Record<CockpitTab, string> = {
  build: 'Answer the guided brief and forge a game.',
  compose: 'See which systems your vision composes, live.',
  run: 'Follow the ten-stage forge pipeline and its verify/repair loop.',
  eras: 'Browse and compare design eras; pin one into the forge.',
  console: 'Talk to the cockpit directly with verbs like STATUS or COMPOSE.',
};

/** Resolve a deep-link `?tab=` value (case/alias tolerant). */
const TAB_ALIASES: Record<string, CockpitTab> = {
  build: 'build', questionnaire: 'build', brief: 'build', q: 'build',
  compose: 'compose', graph: 'compose', blueprint: 'compose',
  run: 'run', forge: 'run', 'forge-run': 'run', pipeline: 'run',
  eras: 'eras', era: 'eras', viewer: 'eras',
  console: 'console', cockpit: 'console', cli: 'console',
};

export function parseTabParam(raw: unknown): CockpitTab | null {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (typeof v !== 'string') return null;
  const key = v.trim().toLowerCase();
  return TAB_ALIASES[key] ?? null;
}

export interface CockpitScreenState {
  tab: CockpitTab;
  /** Era highlighted in the era viewer. */
  selectedEra: string | null;
  /** Tabs the user has opened at least once (for "new" dots). */
  visited: CockpitTab[];
  /** Run generation counter — bumps on each forge start. */
  runSeq: number;
  /** Last run generation the user has looked at on the run tab. */
  runSeen: number;
}

export type CockpitScreenAction =
  | { type: 'tab'; tab: CockpitTab }
  | { type: 'selectEra'; era: string | null }
  | { type: 'runStarted' }
  | { type: 'useEra'; era: string }
  | { type: 'viewEra'; era: string }
  | { type: 'nextTab'; dir: 1 | -1 };

export function initialScreenState(tab: CockpitTab | null = null): CockpitScreenState {
  const t = tab ?? 'build';
  return { tab: t, selectedEra: null, visited: [t], runSeq: 0, runSeen: 0 };
}

function visit(state: CockpitScreenState, tab: CockpitTab): CockpitScreenState {
  const visited = state.visited.includes(tab) ? state.visited : [...state.visited, tab];
  const runSeen = tab === 'run' ? state.runSeq : state.runSeen;
  return { ...state, tab, visited, runSeen };
}

export function cockpitScreenReducer(state: CockpitScreenState, action: CockpitScreenAction): CockpitScreenState {
  switch (action.type) {
    case 'tab':
      return COCKPIT_TABS.includes(action.tab) ? visit(state, action.tab) : state;
    case 'nextTab': {
      const i = COCKPIT_TABS.indexOf(state.tab);
      const n = COCKPIT_TABS.length;
      return visit(state, COCKPIT_TABS[(i + action.dir + n) % n]);
    }
    case 'selectEra':
      return { ...state, selectedEra: action.era };
    case 'runStarted': {
      const next = { ...state, runSeq: state.runSeq + 1 };
      return visit(next, 'run');
    }
    case 'useEra':
      // Pinning happens in the questionnaire reducer; here we jump back to it.
      return visit({ ...state, selectedEra: action.era }, 'build');
    case 'viewEra':
      return visit({ ...state, selectedEra: action.era }, 'eras');
    default:
      return state;
  }
}

export interface TabSignals {
  runPhase: RunPhase;
  composeLoading?: boolean;
  composeError?: string | null;
  composeSystems?: number;
  erasCount?: number;
  erasError?: string | null;
  consoleErrors?: number;
  questionnaireStep?: number;
  questionnaireSteps?: number;
}

export interface TabBadge {
  text: string | null;
  tone: Tone;
  /** Screen-reader suffix for the tab label. */
  a11y: string;
}

/** Status badge per tab (text + tone + accessible suffix). */
export function tabBadges(state: CockpitScreenState, s: TabSignals): Record<CockpitTab, TabBadge> {
  const none: TabBadge = { text: null, tone: 'idle', a11y: '' };
  const runUnseen = state.runSeq > state.runSeen && state.tab !== 'run';
  const run: TabBadge =
    s.runPhase === 'running'
      ? { text: '…', tone: 'warn', a11y: 'forging' }
      : s.runPhase === 'error'
        ? { text: '!', tone: 'bad', a11y: 'run failed' }
        : s.runPhase === 'done'
          ? { text: runUnseen ? '●' : '✓', tone: 'ok', a11y: runUnseen ? 'new result' : 'run finished' }
          : none;
  const compose: TabBadge = s.composeError
    ? { text: '!', tone: 'bad', a11y: 'compose error' }
    : s.composeLoading
      ? { text: '…', tone: 'warn', a11y: 'composing' }
      : s.composeSystems
        ? { text: String(s.composeSystems), tone: 'ok', a11y: `${s.composeSystems} systems` }
        : none;
  const eras: TabBadge = s.erasError
    ? { text: '!', tone: 'bad', a11y: 'eras unavailable' }
    : s.erasCount
      ? { text: String(s.erasCount), tone: 'idle', a11y: `${s.erasCount} eras` }
      : none;
  const total = s.questionnaireSteps ?? 0;
  const build: TabBadge = total
    ? { text: `${Math.min((s.questionnaireStep ?? 0) + 1, total)}/${total}`, tone: 'idle', a11y: `step ${Math.min((s.questionnaireStep ?? 0) + 1, total)} of ${total}` }
    : none;
  const console_: TabBadge = s.consoleErrors
    ? { text: String(s.consoleErrors), tone: 'bad', a11y: `${s.consoleErrors} failed commands` }
    : none;
  return { build, compose, run, eras, console: console_ };
}

/** Accessible tab label: "Forge run, tab 3 of 5, forging". */
export function tabA11yLabel(tab: CockpitTab, badge: TabBadge): string {
  const i = COCKPIT_TABS.indexOf(tab) + 1;
  const base = `${COCKPIT_TAB_LABELS[tab]}, tab ${i} of ${COCKPIT_TABS.length}`;
  return badge.a11y ? `${base}, ${badge.a11y}` : base;
}

/**
 * Shell-style history recall over console commands (newest-first list).
 * `cursor` is -1 when editing a fresh line; ↑ is dir=+1 (older), ↓ is dir=-1.
 */
export function recallCommand(history: readonly string[], cursor: number, dir: 1 | -1): { cursor: number; command: string } {
  const unique: string[] = [];
  for (const c of history) if (c && !unique.includes(c)) unique.push(c);
  if (!unique.length) return { cursor: -1, command: '' };
  const next = Math.max(-1, Math.min(unique.length - 1, cursor + dir));
  return { cursor: next, command: next < 0 ? '' : unique[next] };
}

/** Count failed entries in a console transcript. */
export function consoleFailures(entries: readonly { ok: boolean }[]): number {
  return entries.reduce((n, e) => n + (e.ok ? 0 : 1), 0);
}

/** One-line summary of a composition for the questionnaire review step. */
export function composeSummaryOf(result: ComposeResult | null | undefined): string | null {
  if (!result || typeof result !== 'object') return null;
  if (typeof result.summary === 'string' && result.summary.trim()) return result.summary.trim();
  const comps = Array.isArray(result.components) ? result.components : [];
  const names = Array.from(new Set(comps.map((x) => x?.feature || x?.kind || x?.instance_id).filter(Boolean)));
  if (!names.length) return null;
  return `Composes ${names.length} system${names.length === 1 ? '' : 's'}: ${names.slice(0, 6).join(', ')}${names.length > 6 ? '…' : ''}`;
}
