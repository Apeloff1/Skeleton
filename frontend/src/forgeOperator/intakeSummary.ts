/**
 * Pure GameForge intake helpers for IntakePanel / ComposeRunPanel.
 * Shapes match IntakeSummary + EngineRunPayload.intake in types.ts.
 */
import { ballotShares, beatProgress, cleanAnswers, EXPLICIT_ERA_BEAT, UNSPECIFIED } from './catalog';
import type { Beat, EngineRunPayload, IntakeSummary, TensorState } from './types';

export interface IntakeReadiness {
  answered: number;
  total: number;
  missing: string[];
  complete: boolean;
  cleaned: Record<string, string>;
  cleanedCount: number;
  explicitEra: string | null;
  answerSheet: string[];
  progressLabel: string;
  canSubmit: boolean;
  hint: string;
}

export interface IntakeResultSummary {
  era: string;
  votedEra: string;
  vision: string;
  fingerprint: string;
  dominant: string;
  ballotLabel: string;
  ballotLines: string[];
  answerCount: number;
  answerSheet: string[];
  succeeded: boolean | null;
  runEra: string;
}

function num(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return Number(n).toFixed(digits);
}

/** Sorted "beat: option" lines for the applied answer sheet. */
export function formatIntakeAnswers(answers: Record<string, string> | null | undefined): string[] {
  if (!answers || typeof answers !== 'object') return [];
  return Object.keys(answers)
    .sort()
    .filter((k) => typeof answers[k] === 'string' && answers[k])
    .map((k) => `${k}: ${answers[k]}`);
}

export function formatDominantAxes(tensor: TensorState | null | undefined, max = 3): string {
  const dom = tensor?.dominant;
  if (!Array.isArray(dom) || !dom.length) return '—';
  return dom
    .slice(0, max)
    .map((d) => `${d.axis}=${num(d.value, 3)}`)
    .join(' · ');
}

/** e.g. "soulslike 45% (5) · extraction_now 27% (3)". */
export function formatBallotLines(
  ballots: Record<string, number> | null | undefined,
  max = 6,
): string[] {
  return ballotShares(ballots)
    .slice(0, max)
    .map((b) => `${b.era} ${Math.round(b.share * 100)}% (${b.votes})`);
}

export function formatBallotLabel(ballots: Record<string, number> | null | undefined): string {
  const lines = formatBallotLines(ballots, 3);
  return lines.length ? lines.join(' · ') : '—';
}

/**
 * Readiness of applied beat answers for POST /api/v1/gameforge/intake.
 * Incomplete sheets can still submit (engine votes from what it has) but
 * canSubmit prefers at least one cleaned answer.
 */
export function summarizeIntakeReadiness(
  beats: Beat[] | null | undefined,
  answers: Record<string, string> | null | undefined,
): IntakeReadiness {
  const list = Array.isArray(beats) ? beats : [];
  const raw = answers && typeof answers === 'object' ? answers : {};
  const progress = beatProgress(list, raw);
  const cleaned = list.length ? cleanAnswers(list, raw) : { ...raw };
  const explicit =
    cleaned[EXPLICIT_ERA_BEAT] && cleaned[EXPLICIT_ERA_BEAT] !== UNSPECIFIED
      ? cleaned[EXPLICIT_ERA_BEAT]
      : null;
  const answerSheet = formatIntakeAnswers(cleaned);
  const complete = list.length ? progress.missing.length === 0 : answerSheet.length > 0;
  const canSubmit = answerSheet.length > 0;
  let hint = 'Apply answers from the Beats tab, then forge via intake.';
  if (!list.length && !answerSheet.length) {
    hint = 'Load beats and apply a questionnaire sheet before intake.';
  } else if (!canSubmit) {
    hint = 'No cleaned answers yet — pick options on Beats and tap Apply.';
  } else if (!complete) {
    hint = `Partial sheet (${progress.answered}/${progress.total}) — intake will vote from what you sent.`;
  } else if (explicit) {
    hint = `Ready · explicit era ${explicit}.`;
  } else {
    hint = 'Ready · era will be decided by ballot vote.';
  }
  return {
    answered: progress.answered,
    total: progress.total,
    missing: progress.missing,
    complete,
    cleaned,
    cleanedCount: answerSheet.length,
    explicitEra: explicit,
    answerSheet,
    progressLabel: `${progress.answered} / ${progress.total} answered`,
    canSubmit,
    hint,
  };
}

/** Pull IntakeSummary from a run/intake payload (null-safe). */
export function extractIntake(payload: EngineRunPayload | null | undefined): IntakeSummary | null {
  const intake = payload?.intake;
  if (!intake || typeof intake !== 'object') return null;
  if (!intake.era && !intake.vision && !intake.answers) return null;
  return intake;
}

/** Flatten intake (+ optional run envelope) into operator readout fields. */
export function summarizeIntakeResult(
  payload: EngineRunPayload | null | undefined,
): IntakeResultSummary | null {
  const intake = extractIntake(payload);
  if (!intake) return null;
  const ballots = intake.ballots ?? {};
  const answers = intake.answers && typeof intake.answers === 'object' ? intake.answers : {};
  return {
    era: intake.era || '—',
    votedEra: intake.era || '—',
    vision: (intake.vision || '').slice(0, 280) || '—',
    fingerprint: intake.tensor?.fingerprint || '—',
    dominant: formatDominantAxes(intake.tensor),
    ballotLabel: formatBallotLabel(ballots),
    ballotLines: formatBallotLines(ballots),
    answerCount: Object.keys(answers).filter((k) => answers[k]).length,
    answerSheet: formatIntakeAnswers(answers),
    succeeded: typeof payload?.succeeded === 'boolean' ? payload.succeeded : null,
    runEra: payload?.era || intake.era || '—',
  };
}

export function intakeA11yLabel(readiness: IntakeReadiness | null | undefined): string {
  if (!readiness) return 'Intake form empty';
  if (!readiness.canSubmit) return 'Intake form not ready';
  if (readiness.complete) return `Intake ready, ${readiness.cleanedCount} answers`;
  return `Intake partial, ${readiness.answered} of ${readiness.total} answered`;
}
