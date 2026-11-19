/**
 * Pure summary of a GameForge run payload (POST /api/skeleton/run) for the
 * forge run panel: stage track, verify loop, repair, playtest, era and
 * blueprint. Everything is defensive — any block may be null or missing.
 */
import type { RunPayload, StageRow } from './types';

/** Canonical GameForgeRun stage order (skeleton/context/pipeline.py). */
export const PIPELINE_STAGES = ['ingest', 'detect', 'tensor', 'lattice', 'oracle', 'forge', 'jeeves', 'sim', 'emit', 'seal'] as const;

export const STAGE_COPY: Record<string, string> = {
  ingest: 'Read the vision',
  detect: 'Detect era & hardware',
  tensor: 'Shape the context tensor',
  lattice: 'Weigh design faces',
  oracle: 'Consult the oracle',
  forge: 'Forge, verify & repair',
  jeeves: 'Brief Jeeves',
  sim: 'Simulate encounters',
  emit: 'Emit project files',
  seal: 'Seal the ledger',
};

export type Tone = 'ok' | 'warn' | 'bad' | 'idle';

export interface StageView {
  name: string;
  label: string;
  status: 'succeeded' | 'failed' | 'skipped' | 'pending' | 'running';
  tone: Tone;
  durationMs: number | null;
  attempts: number;
  error: string | null;
}

export interface VerifyView {
  state: 'passed' | 'failed' | 'unknown';
  tone: Tone;
  score: number | null;
  threshold: number | null;
  rounds: number;
  history: number[];
  stoppedReason: string | null;
  blocking: number;
  filesChecked: number | null;
  warned: number | null;
  failed: number | null;
  weakest: string | null;
}

export interface RepairView {
  state: 'not-needed' | 'applied' | 'unresolved' | 'unknown';
  tone: Tone;
  label: string;
  detail: string | null;
}

export interface PlaytestView {
  state: 'off' | 'passed' | 'failed' | 'unavailable';
  tone: Tone;
  label: string;
}

export interface RunSummary {
  succeeded: boolean;
  runId: string | null;
  era: string | null;
  generation: string | null;
  blueprintId: string | null;
  fileCount: number;
  primaryDps: number | null;
  stages: StageView[];
  completed: number;
  total: number;
  failedStage: StageView | null;
  verify: VerifyView;
  repair: RepairView;
  playtest: PlaytestView;
  simPassed: boolean | null;
  ledgerValid: boolean | null;
  advice: string | null;
  briefing: string | null;
  composedFeatures: string[];
  composedFallback: boolean;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function stageView(name: string, row: StageRow | undefined): StageView {
  const raw = String(row?.status ?? '').toUpperCase();
  const status: StageView['status'] =
    raw === 'SUCCEEDED' ? 'succeeded' : raw === 'FAILED' ? 'failed' : raw === 'SKIPPED' ? 'skipped' : raw === 'RUNNING' ? 'running' : 'pending';
  const tone: Tone = status === 'succeeded' ? 'ok' : status === 'failed' ? 'bad' : status === 'skipped' ? 'warn' : 'idle';
  return {
    name,
    label: STAGE_COPY[name] ?? name,
    status,
    tone,
    durationMs: num(row?.duration_s) === null ? null : Math.round((row!.duration_s as number) * 1000),
    attempts: num(row?.attempts) ?? 0,
    error: row?.error ? String(row.error) : null,
  };
}

/** Stage track: canonical order first, then any extra server stages. */
export function stageViews(rows: StageRow[] | undefined | null): StageView[] {
  const byName = new Map((rows ?? []).map((r) => [r.name, r]));
  const views: StageView[] = PIPELINE_STAGES.map((n) => stageView(n, byName.get(n)));
  for (const r of rows ?? []) if (!(PIPELINE_STAGES as readonly string[]).includes(r.name)) views.push(stageView(r.name, r));
  return views;
}

export function verifyView(payload: RunPayload | null | undefined): VerifyView {
  const v = payload?.forge?.verification ?? null;
  const loop = payload?.forge?.verify_loop ?? null;
  const accepted = loop?.accepted ?? v?.accepted;
  const state: VerifyView['state'] = accepted === true ? 'passed' : accepted === false ? 'failed' : 'unknown';
  const history = (loop?.trace?.history ?? []).filter((x): x is number => typeof x === 'number');
  return {
    state,
    tone: state === 'passed' ? 'ok' : state === 'failed' ? 'bad' : 'idle',
    score: num(v?.score) ?? (history.length ? history[history.length - 1] : null),
    threshold: num(loop?.threshold) ?? num(v?.thresholds?.project_accept_at),
    rounds: num(loop?.trace?.rounds) ?? history.length,
    history,
    stoppedReason: loop?.stopped_reason ?? loop?.trace?.stopped_reason ?? v?.reason ?? null,
    blocking: (v?.blocking_issues ?? []).length || (num(v?.summary?.blocking_issues) ?? 0),
    filesChecked: num(v?.summary?.files_checked),
    warned: num(v?.summary?.warned_files),
    failed: num(v?.summary?.failed_files),
    weakest: v?.weakest_path ?? null,
  };
}

export function repairView(payload: RunPayload | null | undefined, verify: VerifyView = verifyView(payload)): RepairView {
  const repair = payload?.forge?.repair ?? null;
  if (repair && typeof repair === 'object') {
    const bits = Object.entries(repair)
      .filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v))
      .slice(0, 4)
      .map(([k, v]) => `${k}: ${String(v)}`);
    const ok = verify.state === 'passed';
    return {
      state: ok ? 'applied' : 'unresolved',
      tone: ok ? 'ok' : 'bad',
      label: ok ? 'Repaired and re-verified' : 'Repair attempted, still failing',
      detail: bits.length ? bits.join(' · ') : null,
    };
  }
  if (verify.state === 'passed') return { state: 'not-needed', tone: 'ok', label: 'No repair needed', detail: null };
  if (verify.state === 'failed') return { state: 'unresolved', tone: 'bad', label: 'Verification failed without a repair', detail: null };
  return { state: 'unknown', tone: 'idle', label: 'Repair status unavailable', detail: null };
}

export function playtestView(payload: RunPayload | null | undefined): PlaytestView {
  const p = (payload as any)?.playtest;
  if (!p || typeof p !== 'object') return { state: 'off', tone: 'idle', label: 'Headless playtest off' };
  const status = String(p.status ?? '');
  if (status === 'passed' || p.passed === true) return { state: 'passed', tone: 'ok', label: 'Headless Godot playtest passed' };
  if (status === 'unavailable') return { state: 'unavailable', tone: 'warn', label: `Playtest unavailable${p.reason ? ` (${p.reason})` : ''}` };
  return { state: 'failed', tone: 'bad', label: 'Headless Godot playtest failed' };
}

export function summarizeRun(payload: RunPayload | null | undefined): RunSummary {
  const stages = stageViews(payload?.run?.stages);
  const verify = verifyView(payload);
  const comp = payload?.forge?.composition ?? null;
  return {
    succeeded: Boolean(payload?.succeeded ?? payload?.run?.succeeded),
    runId: payload?.run?.run_id ?? null,
    era: payload?.era ?? null,
    generation: payload?.generation ?? null,
    blueprintId: payload?.forge?.blueprint_id ?? comp?.blueprint_id ?? null,
    fileCount: num(payload?.forge?.file_count) ?? (payload?.file_names ?? []).length,
    primaryDps: num(payload?.forge?.primary_dps),
    stages,
    completed: stages.filter((s) => s.status === 'succeeded').length,
    total: stages.length,
    failedStage: stages.find((s) => s.status === 'failed') ?? null,
    verify,
    repair: repairView(payload, verify),
    playtest: playtestView(payload),
    simPassed: typeof payload?.sim?.passed === 'boolean' ? payload.sim.passed : null,
    ledgerValid: typeof payload?.ledger?.valid === 'boolean' ? payload.ledger.valid : null,
    advice: payload?.jeeves?.next?.text ?? null,
    briefing: payload?.build_plan?.briefing ?? payload?.jeeves?.briefing ?? null,
    composedFeatures: comp?.features ?? [],
    composedFallback: Boolean(comp?.fallback),
  };
}

/** Pending track shown while the (synchronous) run request is in flight. */
export function pendingStages(): StageView[] {
  return PIPELINE_STAGES.map((n) => stageView(n, undefined));
}

export function formatScore(v: number | null): string {
  return v === null ? '—' : `${Math.round(v * 100)}%`;
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}
