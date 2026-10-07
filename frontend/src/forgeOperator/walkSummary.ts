/**
 * Pure walk-preview view-model helpers for WalkPanel / tests.
 * Shapes match WalkPreview / WalkResult / BuildPlan in types.ts.
 */
import type { BuildPlan, WalkPreview, WalkResult, WalkStep } from './types';

export type WalkVerdict = 'passed' | 'collapsed' | 'failed' | 'unknown';

export interface WalkSummary {
  verdict: WalkVerdict;
  label: string;
  detail: string;
  mode: string;
  elapsed: string;
  bound: string;
  hops: number;
  fights: number;
  cores: string;
  heatPeak: string;
  vents: number;
  pathLabel: string;
  notes: string[];
  stepCount: number;
  stepsPreview: string[];
  planEra: string;
  planSeed: string;
  planBriefing: string;
  planBias: string;
  planOracle: string;
}

function num(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return Number(n).toFixed(digits);
}

export function walkVerdict(walk: WalkResult | null | undefined): WalkVerdict {
  if (!walk) return 'unknown';
  if (walk.passed) return 'passed';
  if (walk.collapsed) return 'collapsed';
  if (!walk.extracted) return 'failed';
  return 'failed';
}

export function walkVerdictLabel(v: WalkVerdict): string {
  switch (v) {
    case 'passed':
      return 'EXTRACTED';
    case 'collapsed':
      return 'COLLAPSED';
    case 'failed':
      return 'INCOMPLETE';
    default:
      return 'NO WALK';
  }
}

export function formatWalkPath(path: string[] | null | undefined, max = 8): string {
  if (!path?.length) return '—';
  if (path.length <= max) return path.join(' → ');
  const head = path.slice(0, max - 1);
  return `${head.join(' → ')} → … → ${path[path.length - 1]} (${path.length} rooms)`;
}

export function formatWalkStep(step: WalkStep): string {
  const t = num(step.t, 2);
  const detail = step.detail ? ` · ${step.detail}` : '';
  return `t=${t}s  [${step.room}] ${step.action}${detail}`;
}

export function summarizePlanBrief(plan: BuildPlan | null | undefined): Pick<
  WalkSummary,
  'planEra' | 'planSeed' | 'planBriefing' | 'planBias' | 'planOracle'
> {
  if (!plan) {
    return {
      planEra: '—',
      planSeed: '—',
      planBriefing: '—',
      planBias: '—',
      planOracle: '—',
    };
  }
  const oracle =
    plan.oracle_text ||
    (plan.oracle_index != null ? `#${plan.oracle_index}` : '—');
  return {
    planEra: plan.era || '—',
    planSeed: plan.seed || '—',
    planBriefing: plan.briefing || '—',
    planBias: plan.room_bias || '—',
    planOracle: oracle,
  };
}

/** Flatten a WalkPreview into operator-facing readout fields. */
export function summarizeWalk(preview: WalkPreview | null | undefined): WalkSummary | null {
  if (!preview?.walk) return null;
  const walk = preview.walk;
  const verdict = walkVerdict(walk);
  const planBits = summarizePlanBrief(preview.plan);
  const notes = Array.isArray(walk.notes) ? walk.notes.filter(Boolean).slice(0, 8) : [];
  const steps = Array.isArray(walk.steps) ? walk.steps : [];
  let detail: string;
  if (verdict === 'passed') {
    detail = `Extracted in ${num(walk.t)}s with ${walk.cores ?? 0}/${walk.required_cores ?? 0} cores.`;
  } else if (verdict === 'collapsed') {
    detail = `Collapsed at t=${num(walk.t)}s before extract.`;
  } else if (verdict === 'failed') {
    detail = `Did not extract (cores ${walk.cores ?? 0}/${walk.required_cores ?? 0}).`;
  } else {
    detail = 'No walk result.';
  }
  return {
    verdict,
    label: walkVerdictLabel(verdict),
    detail,
    mode: walk.mode || '—',
    elapsed: `${num(walk.t)}s`,
    bound: `${num(walk.bound)}s`,
    hops: walk.hops ?? 0,
    fights: walk.fights ?? 0,
    cores: `${walk.cores ?? 0}/${walk.required_cores ?? 0}`,
    heatPeak: num(walk.heat_peak),
    vents: walk.vents ?? 0,
    pathLabel: formatWalkPath(walk.path),
    notes,
    stepCount: steps.length,
    stepsPreview: steps.slice(0, 8).map(formatWalkStep),
    ...planBits,
  };
}
