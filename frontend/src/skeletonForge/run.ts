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
  if (status === 'passed' && p.passed === true) return { state: 'passed', tone: 'ok', label: 'Headless Godot playtest passed' };
  if (status === 'unavailable') return { state: 'unavailable', tone: 'warn', label: `Playtest unavailable${p.reason ? ` (${p.reason})` : ''}` };
  return { state: 'failed', tone: 'bad', label: 'Headless Godot playtest failed' };
}

/** Independent native scene completion. The main-world boot is insufficient. */
export function playableSceneView(payload: RunPayload | null | undefined): PlaytestView | null {
  const archetype = payload?.forge?.playable_archetype;
  if (!archetype) return null;
  const report = payload?.playable_scene_playtest;
  if (!report) {
    return { state: 'off', tone: 'idle', label: 'Playable scene not dynamically tested' };
  }
  if (report.status === 'passed' && report.passed === true) {
    return { state: 'passed', tone: 'ok', label: 'Playable ' + archetype + ' scene completed in Godot' };
  }
  if (report.status === 'unavailable') {
    return { state: 'unavailable', tone: 'warn', label: 'Playable scene unverified (Godot unavailable)' };
  }
  return { state: 'failed', tone: 'bad', label: 'Playable scene qualification failed' };
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

// ─── Local cancel and Play handoff (Studio build screen) ────────────────
//
// POST /api/skeleton/run is a single synchronous request and the server has
// no cancel route. "Cancel" can therefore only stop *this device* from
// waiting and from applying the result. The copy must say exactly that.

/** Error text recorded when the user stops waiting for a run on this device. */
export const RUN_CANCELLED_LOCALLY =
  'Stopped waiting on this device. The server may still finish this build, but its result will not be applied here.';

/** True when a finished run record is a local stop rather than a server failure. */
export function isLocallyCancelled(phase: string, error: string | null | undefined): boolean {
  return phase === 'error' && error === RUN_CANCELLED_LOCALLY;
}

export type PlayHandoffState =
  | 'ready'          // verified playable scene + exact-run source ZIP ready
  | 'ready-unverified' // scene + ZIP ready, but Godot did not complete it here
  | 'needs-export'   // scene generated, but no source files were prepared
  | 'failed'         // scene qualification failed; do not invite play
  | 'not-requested'  // Godot project without a playable scene
  | 'json-target';   // JSON blueprint: nothing to run

export interface PlayHandoff {
  state: PlayHandoffState;
  tone: Tone;
  title: string;
  detail: string;
  /** Ordered, literal steps to actually play the generated project. */
  steps: string[];
  /** Primary action the build screen offers next to this card. */
  action: 'export' | 'edit-brief' | 'none';
  actionLabel: string | null;
  scene: string | null;
  verified: boolean;
}

const SCENE_LABEL: Record<string, string> = {
  extraction: 'Extraction',
  combat_loop: 'Combat Loop',
  pipeline: 'Pipeline',
};

/**
 * What "Play" honestly means for one finished forge run. The app has no
 * in-app Godot runtime, so playing is: save the exact-run source ZIP, open
 * it in Godot 4, run the main scene and use the in-game launcher. Returns
 * null while nothing successful exists to hand off.
 */
export function playHandoff(
  payload: RunPayload | null | undefined,
  request?: { target?: string; playable_content?: boolean; include_files?: boolean } | null,
): PlayHandoff | null {
  if (!payload) return null;
  if (!summarizeRun(payload).succeeded) return null;
  const target = request?.target ?? (payload.forge?.playable_archetype ? 'godot' : undefined);
  if (target === 'json') {
    return {
      state: 'json-target', tone: 'idle', title: 'Blueprint only',
      detail: 'This run produced a JSON blueprint. There is no game to play. Choose the Godot 4 project target and turn on a playable scene to get something you can run.',
      steps: [], action: 'edit-brief', actionLabel: 'Change target in the brief', scene: null, verified: false,
    };
  }
  const archetype = payload.forge?.playable_archetype ?? null;
  const scene = archetype ? (SCENE_LABEL[archetype] ?? archetype) : null;
  const exportReady = payload.succeeded === true && payload.source_export?.status === 'ready';
  if (!archetype) {
    return {
      state: 'not-requested', tone: 'idle', title: 'No playable scene in this build',
      detail: 'The Godot project was generated without a controllable prototype scene. Turn on "Playable Godot prototype scene" in the brief and forge again to get one.',
      steps: [], action: 'edit-brief', actionLabel: 'Add a playable scene', scene: null, verified: false,
    };
  }
  const view = playableSceneView(payload);
  if (view?.state === 'failed') {
    const errors = payload.playable_scene_playtest?.errors ?? [];
    return {
      state: 'failed', tone: 'bad', title: scene + ' scene did not pass',
      detail: 'Godot ran the generated ' + scene + ' scene and it did not complete its win/lose loop'
        + (errors.length ? ': ' + errors[0].slice(0, 160) : '.')
        + ' Change the brief and forge again before playing.',
      steps: [], action: 'edit-brief', actionLabel: 'Change the brief', scene, verified: false,
    };
  }
  const verified = view?.state === 'passed';
  const steps = [
    'Save the Godot ZIP from this screen and unzip it.',
    'Open Godot 4, choose Import, and select project.godot from the unzipped folder.',
    'Press Play (F5) to start the main world.',
    payload.playable_portal?.sealed && payload.playable_portal.return_supported
      ? 'Use the in-game launch button to enter the ' + scene + ' scene; its return button brings you back.'
      : 'Open the ' + scene + ' scene from the FileSystem dock and press Play Scene (F6).',
  ];
  if (!exportReady) {
    return {
      state: 'needs-export', tone: 'warn', title: scene + ' scene generated',
      detail: 'This run did not prepare its source files, so there is nothing to open yet. Turn on "Export your generated Godot project" in the brief and forge again.',
      steps: [], action: 'edit-brief', actionLabel: 'Turn on Godot export', scene, verified,
    };
  }
  return {
    state: verified ? 'ready' : 'ready-unverified',
    tone: verified ? 'ok' : 'warn',
    title: verified ? 'Ready to play: ' + scene : scene + ' scene ready, not yet verified',
    detail: verified
      ? 'Godot completed the ' + scene + ' scene on the server. The ZIP holds the exact files from this run.'
      : 'The ZIP holds the exact files from this run, but Godot did not complete the scene here'
        + (view?.state === 'unavailable' ? ' because no engine was installed.' : '.')
        + ' It may still need fixes.',
    steps, action: 'export', actionLabel: 'Save Godot ZIP to play', scene, verified,
  };
}
