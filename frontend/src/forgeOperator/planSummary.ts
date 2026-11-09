/**
 * Pure build-plan view-model helpers for PlansPanel / tests.
 * Shapes match BuildPlan in types.ts. Mirrors walkSummary style.
 */
import type { BuildPlan } from './types';

export type PlanFlag = 'spawn_weapon' | 'extract_late' | 'adapt' | 'authored' | 'slack';

export interface PlanSummary {
  era: string;
  seed: string;
  tensorFp: string;
  oracle: string;
  briefing: string;
  roomBias: string;
  adapt: string;
  slack: string;
  authored: string;
  spawnWeapon: boolean;
  extractLate: boolean;
  enemyMixLabel: string;
  recipesLabel: string;
  notes: string[];
  flags: PlanFlag[];
  flagLabels: string[];
}

function num(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return Number(n).toFixed(digits);
}

const FLAG_CHIP: Record<PlanFlag, string> = {
  spawn_weapon: 'spawn weapon',
  extract_late: 'late extract',
  adapt: 'adapt',
  authored: 'authored',
  slack: 'slack',
};

/** Collect noteworthy plan flags as stable ids + short chip labels. */
export function collectPlanFlags(plan: BuildPlan): { flags: PlanFlag[]; flagLabels: string[] } {
  const flags: PlanFlag[] = [];
  const flagLabels: string[] = [];
  if (plan.spawn_weapon) {
    flags.push('spawn_weapon');
    flagLabels.push(FLAG_CHIP.spawn_weapon);
  }
  if (plan.extract_late) {
    flags.push('extract_late');
    flagLabels.push(FLAG_CHIP.extract_late);
  }
  if (plan.adapt && plan.adapt !== 'none') {
    flags.push('adapt');
    flagLabels.push(`${FLAG_CHIP.adapt} ${plan.adapt}`);
  }
  if (plan.authored) {
    flags.push('authored');
    flagLabels.push(`${FLAG_CHIP.authored} ${plan.authored}`);
  }
  if (plan.slack != null && Number.isFinite(plan.slack) && plan.slack !== 0) {
    flags.push('slack');
    flagLabels.push(`${FLAG_CHIP.slack} ${num(plan.slack)}`);
  }
  return { flags, flagLabels };
}

export function planFlagLabel(flag: PlanFlag): string {
  return FLAG_CHIP[flag] ?? flag;
}

/** e.g. "trash×2 · elite×2" (zeros omitted). */
export function formatEnemyMix(mix: Record<string, number> | null | undefined): string {
  if (!mix || typeof mix !== 'object') return '—';
  const parts = Object.entries(mix)
    .filter(([, n]) => typeof n === 'number' && Number.isFinite(n) && n > 0)
    .map(([k, n]) => `${k}×${n}`);
  return parts.length ? parts.join(' · ') : '—';
}

/** Joined recipe ids with optional truncation. */
export function formatRecipes(recipes: string[] | null | undefined, max = 6): string {
  if (!recipes?.length) return '—';
  if (recipes.length <= max) return recipes.join(', ');
  const head = recipes.slice(0, max);
  return `${head.join(', ')} … (+${recipes.length - max})`;
}

/** Flatten a BuildPlan into operator-facing readout fields. */
export function summarizePlan(plan: BuildPlan | null | undefined): PlanSummary | null {
  if (!plan) return null;
  const oracle =
    plan.oracle_text ||
    (plan.oracle_index != null ? `#${plan.oracle_index}` : '—');
  const { flags, flagLabels } = collectPlanFlags(plan);
  const notes = Array.isArray(plan.notes) ? plan.notes.filter(Boolean).slice(0, 8) : [];
  return {
    era: plan.era || '—',
    seed: plan.seed || '—',
    tensorFp: plan.tensor_fp || '—',
    oracle,
    briefing: plan.briefing || '—',
    roomBias: plan.room_bias || '—',
    adapt: plan.adapt || '—',
    slack: plan.slack == null ? '—' : num(plan.slack),
    authored: plan.authored || '—',
    spawnWeapon: Boolean(plan.spawn_weapon),
    extractLate: Boolean(plan.extract_late),
    enemyMixLabel: formatEnemyMix(plan.enemy_mix),
    recipesLabel: formatRecipes(plan.recipes),
    notes,
    flags,
    flagLabels,
  };
}
