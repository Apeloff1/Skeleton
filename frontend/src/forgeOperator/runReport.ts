/**
 * Forge run report — turns a raw GameForgeRun payload into what an operator
 * needs to decide "ship it / review it / it's blocked".
 *
 * Inputs are the real `/api/v1/gameforge/run` and `/gameforge/intake` bodies.
 * Several signals only exist implicitly and are recovered here:
 *   • when `playtest=require` fails, the emit stage raises before the
 *     `playtest` key is stored, so the verdict is parsed from the stage error
 *     ("RuntimeError: playtest unavailable: missing-godot-binary");
 *   • suggest-mode repairs carry `applied: 0` actions and `proposed_paths`,
 *     apply-mode ones `applied: 1` and `changed_paths`;
 *   • the verify loop's `trace.history` is the per-round score curve.
 */
import type {
  EngineRunPayload,
  EngineRunRequest,
  FileReport,
  PlaytestMode,
  RepairAction,
  SimEncounter,
  StageRow,
} from './types';
import { FORGE_STAGES } from './types';

// ── Stages ─────────────────────────────────────────────────────────────

export type StageState = 'ok' | 'failed' | 'skipped' | 'retried' | 'not_run';

export interface StageLine {
  name: string;
  state: StageState;
  attempts: number;
  durationS: number;
  error: string | null;
  gate: string | null;
}

function normStatus(row: StageRow): StageState {
  const s = String(row.status || '').toUpperCase();
  if (s === 'SUCCEEDED' || s === 'OK' || s === 'PASSED') return (row.attempts ?? 1) > 1 ? 'retried' : 'ok';
  if (s === 'SKIPPED') return 'skipped';
  if (s === 'FAILED' || s === 'ERROR') return 'failed';
  return 'not_run';
}

function gateText(gate: unknown): string | null {
  if (gate == null) return null;
  if (typeof gate === 'string') return gate;
  if (typeof gate === 'object') {
    const g = gate as Record<string, unknown>;
    return String(g.reason ?? g.message ?? g.gate ?? JSON.stringify(g));
  }
  return String(gate);
}

/** Every canonical stage in order, including ones the run never reached. */
export function stageTimeline(payload: EngineRunPayload | null | undefined): StageLine[] {
  const rows = payload?.run?.stages ?? [];
  const byName = new Map(rows.map((r) => [r.name, r]));
  const names = [...FORGE_STAGES, ...rows.map((r) => r.name).filter((n) => !(FORGE_STAGES as readonly string[]).includes(n))];
  return names.map((name) => {
    const row = byName.get(name);
    if (!row) return { name, state: 'not_run' as const, attempts: 0, durationS: 0, error: null, gate: null };
    return {
      name,
      state: normStatus(row),
      attempts: row.attempts ?? 1,
      durationS: row.duration_s ?? 0,
      error: row.error ?? null,
      gate: gateText(row.gate_failure),
    };
  });
}

export function failedStage(payload: EngineRunPayload | null | undefined): StageLine | null {
  return stageTimeline(payload).find((s) => s.state === 'failed') ?? null;
}

// ── Playtest ───────────────────────────────────────────────────────────

export type PlaytestState = 'passed' | 'failed' | 'unavailable' | 'off' | 'blocked' | 'unknown';

export interface PlaytestVerdict {
  state: PlaytestState;
  mode: PlaytestMode | 'unknown';
  label: string;
  detail: string;
  binarySource: string | null;
  frames: number | null;
  errors: string[];
  /** Whether the run's emit stage was gated on this playtest. */
  gating: boolean;
}

const PLAYTEST_REASON: Record<string, string> = {
  'missing-godot-binary': 'No Godot binary on the engine host (set GODOT_BIN or install godot4).',
  'unverified-binary': 'A Godot binary was found but failed its version check.',
  timeout: 'The headless boot exceeded its time budget.',
};

function explainReason(reason: string | undefined | null): string {
  if (!reason) return '';
  return PLAYTEST_REASON[reason] ?? reason.replace(/[-_]/g, ' ');
}

const EMIT_PLAYTEST_RE = /playtest\s+(unavailable|failed|passed)\s*:?\s*(.*)$/i;

export function playtestVerdict(payload: EngineRunPayload | null | undefined, requested?: PlaytestMode): PlaytestVerdict {
  const mode: PlaytestMode | 'unknown' = requested ?? 'unknown';
  const report = payload?.playtest ?? null;
  const emit = stageTimeline(payload).find((s) => s.name === 'emit');
  const gating = mode === 'require';

  if (report && typeof report === 'object') {
    const status = String(report.status || (report.passed ? 'passed' : 'failed'));
    const state: PlaytestState = status === 'passed' ? 'passed' : status === 'unavailable' ? 'unavailable' : status === 'failed' ? 'failed' : 'unknown';
    const errors = Array.isArray(report.errors) ? report.errors.map(String) : [];
    const detail =
      state === 'passed'
        ? `Booted headless for ${report.frames ?? '?'} frames without script errors.`
        : state === 'unavailable'
          ? explainReason(report.reason ?? report.binary_source ?? undefined) || 'Playtest could not run.'
          : errors[0] ?? explainReason(report.reason) ?? 'Headless boot reported errors.';
    return {
      state,
      mode,
      label: state === 'passed' ? 'PLAYABLE' : state === 'unavailable' ? 'NOT RUN' : state === 'failed' ? 'BOOT FAILED' : 'UNKNOWN',
      detail,
      binarySource: report.binary_source ? String(report.binary_source) : null,
      frames: typeof report.frames === 'number' ? report.frames : null,
      errors,
      gating,
    };
  }

  const match = emit?.error ? EMIT_PLAYTEST_RE.exec(emit.error) : null;
  if (match) {
    const kind = match[1].toLowerCase();
    const reason = match[2].trim();
    return {
      state: 'blocked',
      mode: requested ?? 'require',
      label: kind === 'unavailable' ? 'REQUIRED · UNAVAILABLE' : 'REQUIRED · FAILED',
      detail: `Emit was blocked because the required playtest ${kind}. ${explainReason(reason.split(/[;:]/)[0]) || reason}`.trim(),
      binarySource: kind === 'unavailable' ? reason.split(/[;:\s]/)[0] || null : null,
      frames: null,
      errors: kind === 'failed' && reason ? [reason] : [],
      gating: true,
    };
  }
  if (mode === 'off') {
    return { state: 'off', mode, label: 'STATIC ONLY', detail: 'Playtest disabled; only static GDScript and project checks ran.', binarySource: null, frames: null, errors: [], gating: false };
  }
  return { state: 'unknown', mode, label: 'NO REPORT', detail: 'The run did not report a playtest result.', binarySource: null, frames: null, errors: [], gating };
}

// ── Verification and repair ────────────────────────────────────────────

export interface VerificationSummary {
  accepted: boolean | null;
  score: number | null;
  threshold: number | null;
  reason: string;
  weakestPath: string | null;
  files: { checked: number; passed: number; warned: number; failed: number };
  blocking: string[];
  /** Lowest-scoring files first, with their hard/soft issues. */
  worstFiles: FileReport[];
  rounds: number;
  history: number[];
  stoppedReason: string | null;
  advisory: { path: string; confidence: number | null; issues: string[] } | null;
}

function issueText(issue: unknown): string {
  if (typeof issue === 'string') return issue;
  if (issue && typeof issue === 'object') {
    const i = issue as Record<string, unknown>;
    const where = i.path ? `${i.path}: ` : '';
    return `${where}${i.message ?? i.issue ?? JSON.stringify(i)}`;
  }
  return String(issue);
}

export function verificationSummary(payload: EngineRunPayload | null | undefined, worst = 5): VerificationSummary {
  const forge = payload?.forge ?? {};
  const v = forge.verification ?? null;
  const loop = forge.verify_loop ?? null;
  const summary = v?.summary ?? {};
  const history = (loop?.trace?.history ?? []).filter((x): x is number => typeof x === 'number');
  const threshold = typeof loop?.threshold === 'number' ? loop.threshold : v?.thresholds?.project_accept_at ?? null;
  const reports = [...(v?.file_reports ?? [])].sort((a, b) => a.score - b.score || a.path.localeCompare(b.path));
  const code = loop?.code_verdict ?? null;
  return {
    accepted: typeof v?.accepted === 'boolean' ? v.accepted : null,
    score: typeof v?.score === 'number' ? v.score : null,
    threshold: typeof threshold === 'number' ? threshold : null,
    reason: String(v?.reason ?? ''),
    weakestPath: v?.weakest_path ?? null,
    files: {
      checked: summary.files_checked ?? 0,
      passed: summary.passed_files ?? 0,
      warned: summary.warned_files ?? 0,
      failed: summary.failed_files ?? 0,
    },
    blocking: [...(v?.blocking_issues ?? []), ...(v?.project_issues ?? [])].map(issueText),
    worstFiles: reports.slice(0, worst),
    rounds: loop?.trace?.rounds ?? history.length,
    history,
    stoppedReason: loop?.stopped_reason ?? loop?.trace?.stopped_reason ?? null,
    advisory: code?.path ? { path: code.path, confidence: code.confidence ?? null, issues: code.issues ?? [] } : null,
  };
}

export interface RepairSummary {
  mode: string;
  /** Actions that were (apply) or would be (suggest) taken. */
  actions: RepairAction[];
  byClass: { klass: string; count: number }[];
  applied: number;
  proposed: number;
  paths: string[];
  beforeScore: number | null;
  afterScore: number | null;
  reason: string;
  /** Nothing to repair: first verification round already accepted. */
  clean: boolean;
}

export function repairSummary(payload: EngineRunPayload | null | undefined, requested?: string): RepairSummary {
  const forge = payload?.forge ?? {};
  const r = forge.repair ?? null;
  const loop = forge.verify_loop ?? null;
  const mode = String(r?.mode ?? loop?.repair_mode ?? requested ?? 'apply');
  const actions = Array.isArray(r?.actions) ? r!.actions : [];
  const counts = new Map<string, number>();
  for (const a of actions) counts.set(a.class || 'other', (counts.get(a.class || 'other') ?? 0) + 1);
  const applied = actions.filter((a) => a.applied === 1).length;
  const paths = Array.from(new Set([...(r?.changed_paths ?? []), ...(r?.proposed_paths ?? []), ...actions.map((a) => a.path || '').filter(Boolean)]));
  const rounds = loop?.rounds_detail ?? [];
  return {
    mode,
    actions,
    byClass: Array.from(counts, ([klass, count]) => ({ klass, count })).sort((a, b) => b.count - a.count || a.klass.localeCompare(b.klass)),
    applied,
    proposed: actions.length - applied,
    paths,
    beforeScore: typeof r?.before?.score === 'number' ? r.before.score : rounds[0]?.confidence ?? null,
    afterScore: typeof r?.after?.score === 'number' ? r.after.score : rounds.length ? rounds[rounds.length - 1].confidence : null,
    reason: String(r?.reason ?? ''),
    clean: !r && (rounds.length === 0 || rounds[0].accepted === true),
  };
}

// ── Simulation ─────────────────────────────────────────────────────────

export interface EncounterPair {
  enemy: string;
  targetTtk: number;
  ideal: number | null;
  thermal: number | null;
  /** thermal / target; > 1 means heat management slows kills. */
  slowdown: number | null;
  overheat: boolean;
  vents: number;
  killed: boolean;
}

/** Pair ideal and thermal encounters per enemy class, preserving server order. */
export function encounterPairs(encounters: SimEncounter[] | null | undefined): EncounterPair[] {
  const order: string[] = [];
  const byEnemy = new Map<string, EncounterPair>();
  for (const e of encounters ?? []) {
    let pair = byEnemy.get(e.enemy_id);
    if (!pair) {
      pair = { enemy: e.enemy_id, targetTtk: e.target_ttk, ideal: null, thermal: null, slowdown: null, overheat: false, vents: 0, killed: true };
      byEnemy.set(e.enemy_id, pair);
      order.push(e.enemy_id);
    }
    if (e.mode === 'ideal') pair.ideal = e.measured_ttk;
    else if (e.mode === 'thermal') {
      pair.thermal = e.measured_ttk;
      pair.slowdown = e.target_ttk > 0 ? e.measured_ttk / e.target_ttk : null;
    }
    pair.overheat = pair.overheat || !!e.overheat;
    pair.vents += e.vents ?? 0;
    pair.killed = pair.killed && e.killed !== false;
  }
  return order.map((k) => byEnemy.get(k)!);
}

// ── Verdict ────────────────────────────────────────────────────────────

export type Verdict = 'ship' | 'review' | 'blocked';

export interface VerdictReason {
  level: Verdict;
  text: string;
}

export interface OperatorVerdict {
  verdict: Verdict;
  reasons: VerdictReason[];
}

const RANK: Record<Verdict, number> = { ship: 0, review: 1, blocked: 2 };

/**
 * Decide what an operator should do with a run. Blocking signals: a failed
 * stage, verification rejected, a required playtest that did not pass.
 * Review signals: playtest skipped/unavailable, suggest-mode repairs pending,
 * simulation or walk failures, soft file warnings, post-processing errors.
 */
export function operatorVerdict(payload: EngineRunPayload | null | undefined, request?: Partial<EngineRunRequest>): OperatorVerdict {
  const reasons: VerdictReason[] = [];
  if (!payload) return { verdict: 'blocked', reasons: [{ level: 'blocked', text: 'No run payload.' }] };
  const failed = failedStage(payload);
  if (failed) reasons.push({ level: 'blocked', text: `Stage "${failed.name}" failed${failed.error ? `: ${failed.error}` : ''}.` });
  else if (payload.succeeded === false || payload.run?.succeeded === false) reasons.push({ level: 'blocked', text: 'Pipeline reported failure.' });

  const v = verificationSummary(payload);
  if (v.accepted === false) reasons.push({ level: 'blocked', text: `Verification rejected (${v.reason || 'below threshold'}${v.score != null ? `, score ${v.score.toFixed(2)}` : ''}).` });
  else if (v.files.warned > 0) reasons.push({ level: 'review', text: `${v.files.warned} file(s) passed with warnings; weakest ${v.weakestPath ?? 'unknown'}.` });

  const p = playtestVerdict(payload, request?.playtest);
  if (p.state === 'blocked' || (p.gating && p.state !== 'passed')) reasons.push({ level: 'blocked', text: `Required playtest did not pass: ${p.detail}` });
  else if (p.state === 'failed') reasons.push({ level: 'review', text: `Playtest boot failed: ${p.detail}` });
  else if (p.state === 'unavailable') reasons.push({ level: 'review', text: `Playtest not run: ${p.detail}` });
  else if (p.state === 'off') reasons.push({ level: 'review', text: 'Playtest disabled — only static checks ran.' });

  const r = repairSummary(payload, request?.repair_mode);
  if (r.mode === 'suggest' && r.proposed > 0) reasons.push({ level: 'review', text: `${r.proposed} repair(s) proposed but not applied (suggest mode).` });

  const sim = payload.sim;
  if (sim && sim.passed === false) reasons.push({ level: 'review', text: 'Combat simulation failed its TTK identity check.' });
  if (sim?.walk && sim.walk.passed === false) reasons.push({ level: 'review', text: `Walkthrough did not extract (${sim.walk.collapsed ? 'collapsed' : 'incomplete'}).` });
  if (payload.postprocess_error && payload.postprocess_error !== 'ImportError') reasons.push({ level: 'review', text: `Post-processing error: ${payload.postprocess_error}` });
  if (payload.ledger && payload.ledger.valid === false) reasons.push({ level: 'blocked', text: 'Run ledger failed verification.' });

  const verdict = reasons.reduce<Verdict>((acc, r2) => (RANK[r2.level] > RANK[acc] ? r2.level : acc), 'ship');
  reasons.sort((a, b) => RANK[b.level] - RANK[a.level]);
  return { verdict, reasons };
}

// ── History digest ─────────────────────────────────────────────────────

export interface RunDigest {
  id: string;
  at: number;
  source: 'run' | 'intake';
  vision: string;
  era: string | null;
  archetype: string | null;
  target: string;
  playtestMode: PlaytestMode;
  repairMode: string;
  verdict: Verdict;
  score: number | null;
  fileCount: number | null;
  playtest: PlaytestState;
  failedStage: string | null;
  durationS: number | null;
  blueprintId: string | null;
}

/** Compact, persistable record of a run for the operator's history list. */
export function digestRun(payload: EngineRunPayload, request: EngineRunRequest, source: 'run' | 'intake', at = Date.now()): RunDigest {
  const verdict = operatorVerdict(payload, request).verdict;
  const composition = payload.forge?.composition;
  return {
    id: payload.run?.run_id || `local-${at.toString(36)}`,
    at,
    source,
    vision: (payload.intake?.vision || request.vision || '').slice(0, 240),
    era: payload.era ?? null,
    archetype: request.archetype || (composition ? 'auto' : null),
    target: request.target,
    playtestMode: request.playtest,
    repairMode: request.repair_mode,
    verdict,
    score: payload.forge?.verification?.score ?? null,
    fileCount: payload.forge?.file_count ?? (payload.file_names ? payload.file_names.length : null),
    playtest: playtestVerdict(payload, request.playtest).state,
    failedStage: failedStage(payload)?.name ?? null,
    durationS: payload.run?.duration_s ?? null,
    blueprintId: payload.forge?.blueprint_id ?? null,
  };
}

/** Group emitted file names by top-level folder for the artefact list. */
export function groupFiles(names: string[] | null | undefined): { folder: string; files: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const name of names ?? []) {
    const slash = name.indexOf('/');
    const folder = slash === -1 ? '(root)' : name.slice(0, slash);
    const list = groups.get(folder) ?? [];
    list.push(slash === -1 ? name : name.slice(slash + 1));
    groups.set(folder, list);
  }
  return Array.from(groups, ([folder, files]) => ({ folder, files: files.sort() })).sort((a, b) =>
    a.folder === '(root)' ? -1 : b.folder === '(root)' ? 1 : a.folder.localeCompare(b.folder),
  );
}
