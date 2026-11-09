/**
 * Pure questionnaire / beats view-model helpers for BeatsPanel / tests.
 * Uses catalog beatProgress / cleanAnswers; mirrors planSummary / walkSummary.
 */
import type { Beat } from './types';
import {
  EXPLICIT_ERA_BEAT,
  beatProgress,
  cleanAnswers,
  type BeatProgress,
} from './catalog';

export interface BeatSummary {
  answered: number;
  total: number;
  missing: string[];
  complete: boolean;
  progressLabel: string;
  cleaned: Record<string, string>;
  cleanedCount: number;
  answerSheet: string[];
  /** Cleaned era_explicit when present (unspecified never appears in cleaned). */
  explicitEra: string | null;
}

/** e.g. "3 / 11 answered". */
export function progressLabel(progress: BeatProgress | null | undefined): string {
  if (!progress || !Number.isFinite(progress.total)) return '0 / 0 answered';
  return `${progress.answered} / ${progress.total} answered`;
}

/** Short operator-facing lines like `pace: processional`. Stable key order. */
export function formatAnswerSheet(answers: Record<string, string> | null | undefined): string[] {
  if (!answers || typeof answers !== 'object') return [];
  return Object.keys(answers)
    .sort()
    .filter((k) => typeof answers[k] === 'string' && answers[k])
    .map((k) => `${k}: ${answers[k]}`);
}

export function isOptionSelected(
  answers: Record<string, string> | null | undefined,
  beatId: string,
  option: string,
): boolean {
  if (!answers || !beatId || !option) return false;
  return answers[beatId] === option;
}

/**
 * Null-safe questionnaire readout. Empty beats → null; empty answers still yields
 * a summary (0 answered, all required missing).
 */
export function summarizeBeats(
  beats: Beat[] | null | undefined,
  answers: Record<string, string> | null | undefined,
): BeatSummary | null {
  if (!beats?.length) return null;
  const ans = answers && typeof answers === 'object' ? answers : {};
  const progress = beatProgress(beats, ans);
  const cleaned = cleanAnswers(beats, ans);
  const complete = progress.missing.length === 0;
  return {
    answered: progress.answered,
    total: progress.total,
    missing: progress.missing,
    complete,
    progressLabel: progressLabel(progress),
    cleaned,
    cleanedCount: Object.keys(cleaned).length,
    answerSheet: formatAnswerSheet(cleaned),
    explicitEra: cleaned[EXPLICIT_ERA_BEAT] ?? null,
  };
}

export { EXPLICIT_ERA_BEAT };
