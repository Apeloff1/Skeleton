/**
 * Parallel, cancellable boot-stage runner.
 *
 * Stages inside the same phase run concurrently, but higher phases are now
 * genuinely gated behind lower phases. This keeps network prewarm and lazy
 * housekeeping from competing with the local phase-0 path for the first
 * interactive frame.
 */
import { BootStageDef, StageRun } from './stages';
import { trail } from '../utils/breadcrumbs';

export type StageStatus = 'pending' | 'running' | 'ok' | 'failed' | 'skipped' | 'timed_out';

export interface StageState {
  id: string;
  label: string;
  status: StageStatus;
  attempts: number;
  startedAt?: number;
  endedAt?: number;
  durationMs?: number;
  error?: string;
  critical: boolean;
  weight: number;
  phase: 0 | 1 | 2;
  deps: string[];
}

export interface RunnerSnapshot {
  ok: boolean;
  bootScore: number;
  phaseProgress: { 0: number; 1: number; 2: number };
  counts: { ok: number; failed: number; skipped: number; pending: number; total: number };
  criticalOk: boolean;
  elapsedMs: number;
  stages: Record<string, StageState>;
  phaseDone: { 0: boolean; 1: boolean; 2: boolean };
  cancelled: boolean;
}

type Listener = (snap: RunnerSnapshot) => void;

interface TimeoutResult<T> {
  ok: boolean;
  v?: T;
  reason?: 'timeout' | 'aborted' | string;
}

function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  signal?: AbortSignal,
): Promise<TimeoutResult<T>> {
  return new Promise(resolve => {
    let done = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const onAbort = () => finish({ ok: false, reason: 'aborted' });
    const finish = (result: TimeoutResult<T>) => {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      signal?.removeEventListener?.('abort', onAbort);
      resolve(result);
    };

    if (signal?.aborted) {
      finish({ ok: false, reason: 'aborted' });
      return;
    }

    timer = setTimeout(() => finish({ ok: false, reason: 'timeout' }), ms);
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);

    promise
      .then(v => finish({ ok: true, v }))
      .catch(e => finish({ ok: false, reason: e?.message || 'error' }));
  });
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }

    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.('abort', onAbort);
      fn();
    };
    const timer = setTimeout(() => finish(resolve), ms);
    const onAbort = () => {
      clearTimeout(timer);
      finish(() => reject(new Error('aborted')));
    };
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);
  });
}

export class BootRunner {
  private states: Record<string, StageState>;
  private listeners = new Set<Listener>();
  private startedAt = Date.now();
  private resolvedTasks: Record<string, Promise<void>> = {};
  private aborter: AbortController | null = null;
  private started = false;
  private runPromise: Promise<RunnerSnapshot> | null = null;

  constructor(private stages: BootStageDef[]) {
    this.states = Object.fromEntries(stages.map(stage => [stage.id, {
      id: stage.id,
      label: stage.label,
      status: 'pending' as StageStatus,
      attempts: 0,
      critical: stage.critical,
      weight: stage.weight,
      phase: stage.phase,
      deps: [...stage.deps],
    } as StageState]));
    this.aborter = typeof AbortController !== 'undefined' ? new AbortController() : null;
  }

  on(fn: Listener): () => void {
    this.listeners.add(fn);
    try { fn(this.snapshot()); } catch {}
    return () => { this.listeners.delete(fn); };
  }

  private emit(): void {
    const snap = this.snapshot();
    this.listeners.forEach(fn => { try { fn(snap); } catch {} });
  }

  private phaseProgress(): { 0: number; 1: number; 2: number } {
    const out = { 0: 0, 1: 0, 2: 0 } as { 0: number; 1: number; 2: number };
    for (const phase of [0, 1, 2] as const) {
      const stages = Object.values(this.states).filter(state => state.phase === phase);
      if (stages.length === 0) {
        out[phase] = 100;
        continue;
      }
      const totalWeight = stages.reduce((sum, state) => sum + state.weight, 0) || 1;
      const okWeight = stages
        .filter(state => state.status === 'ok')
        .reduce((sum, state) => sum + state.weight, 0);
      out[phase] = Math.round((100 * okWeight / totalWeight) * 10) / 10;
    }
    return out;
  }

  snapshot(): RunnerSnapshot {
    const list = Object.values(this.states);
    const total = list.length;
    const ok = list.filter(state => state.status === 'ok').length;
    const failed = list.filter(state => state.status === 'failed' || state.status === 'timed_out').length;
    const skipped = list.filter(state => state.status === 'skipped').length;
    const pending = list.filter(state => state.status === 'pending' || state.status === 'running').length;
    const criticalOk = list.every(state => !state.critical || state.status === 'ok');
    const totalWeight = list.reduce((sum, state) => sum + state.weight, 0) || 1;
    const okWeight = list
      .filter(state => state.status === 'ok')
      .reduce((sum, state) => sum + state.weight, 0);

    const phaseDone = { 0: false, 1: false, 2: false } as { 0: boolean; 1: boolean; 2: boolean };
    for (const phase of [0, 1, 2] as const) {
      const stages = list.filter(state => state.phase === phase);
      phaseDone[phase] = stages.length > 0
        && stages.every(state => state.status !== 'pending' && state.status !== 'running');
    }

    return {
      ok: failed === 0 && criticalOk,
      bootScore: Math.round((100 * okWeight / totalWeight) * 10) / 10,
      phaseProgress: this.phaseProgress(),
      counts: { ok, failed, skipped, pending, total },
      criticalOk,
      elapsedMs: Date.now() - this.startedAt,
      stages: { ...this.states },
      phaseDone,
      cancelled: !!this.aborter?.signal?.aborted,
    };
  }

  cancel(): void {
    try { this.aborter?.abort(); } catch {}
    for (const state of Object.values(this.states)) {
      if (state.status === 'pending' || state.status === 'running') {
        state.status = 'skipped';
        state.error = state.error || 'cancelled';
      }
    }
    trail.add('boot', 'runner_cancelled', {}, 'warn');
    this.emit();
  }

  private async waitForEarlierPhases(def: BootStageDef): Promise<void> {
    if (def.phase === 0) return;
    const priorTasks = this.stages
      .filter(stage => stage.phase < def.phase)
      .map(stage => this.resolvedTasks[stage.id])
      .filter(Boolean);
    await Promise.allSettled(priorTasks);
  }

  private async runOne(def: BootStageDef): Promise<void> {
    const state = this.states[def.id];
    const signal = this.aborter?.signal;

    // The phase gate is separate from explicit dependency semantics: every
    // phase-1 task waits for all phase-0 work, and phase 2 waits for phases 0+1.
    await this.waitForEarlierPhases(def);

    for (const depId of def.deps) {
      const depPromise = this.resolvedTasks[depId];
      if (depPromise) {
        try { await depPromise; } catch {}
      }
      const dep = this.states[depId];
      if (!dep || (dep.critical && dep.status !== 'ok')) {
        state.status = 'skipped';
        state.error = `dep failed: ${depId}`;
        trail.add('boot', `stage_skipped ${def.id}`, { dep: depId }, 'warn');
        this.emit();
        return;
      }
    }

    if (signal?.aborted) {
      state.status = 'skipped';
      state.error = 'cancelled';
      this.emit();
      return;
    }

    const maxAttempts = 1 + Math.max(0, def.retries ?? 0);
    const backoffBase = def.backoffMs ?? 250;
    state.startedAt = Date.now();
    let lastResult: TimeoutResult<StageRun> = { ok: false, reason: 'init' };

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      if (signal?.aborted) {
        state.status = 'skipped';
        state.error = 'cancelled';
        state.attempts = attempt - 1;
        state.endedAt = Date.now();
        state.durationMs = state.endedAt - state.startedAt;
        this.emit();
        return;
      }

      state.attempts = attempt;
      state.status = 'running';
      this.emit();
      trail.add('boot', `stage_started ${def.id}`, { attempt, max: maxAttempts }, 'info');

      lastResult = await withTimeout<StageRun>(def.run(signal), def.timeoutMs, signal);

      if (lastResult.ok && lastResult.v?.ok) {
        state.endedAt = Date.now();
        state.durationMs = state.endedAt - state.startedAt;
        state.status = 'ok';
        trail.add('boot', `stage_ok ${def.id}`, { ms: state.durationMs, attempts: attempt }, 'info');
        this.emit();
        return;
      }

      if (lastResult.reason === 'aborted' || signal?.aborted) {
        state.endedAt = Date.now();
        state.durationMs = state.endedAt - state.startedAt;
        state.status = 'skipped';
        state.error = 'cancelled';
        this.emit();
        return;
      }

      const note = lastResult.ok && lastResult.v ? lastResult.v.note : lastResult.reason;
      trail.add('boot', `stage_attempt_failed ${def.id}`, {
        attempt,
        max: maxAttempts,
        reason: note,
      }, 'warn');

      if (attempt < maxAttempts) {
        const wait = backoffBase * Math.pow(2, attempt - 1);
        try {
          await sleep(wait, signal);
        } catch {
          state.endedAt = Date.now();
          state.durationMs = state.endedAt - state.startedAt;
          state.status = 'skipped';
          state.error = 'cancelled';
          this.emit();
          return;
        }
      }
    }

    state.endedAt = Date.now();
    state.durationMs = state.endedAt - state.startedAt;
    if (lastResult.reason === 'timeout') {
      state.status = 'timed_out';
      state.error = 'timeout';
    } else if (lastResult.ok && lastResult.v && !lastResult.v.ok) {
      state.status = 'failed';
      state.error = lastResult.v.note || 'failed';
    } else {
      state.status = 'failed';
      state.error = lastResult.reason || 'failed';
    }

    trail.add('boot', `stage_failed ${def.id}`, {
      reason: state.error,
      ms: state.durationMs,
      attempts: maxAttempts,
    }, 'error');
    this.emit();
  }

  run(): Promise<RunnerSnapshot> {
    if (this.runPromise) return this.runPromise;
    this.started = true;

    // Populate every task synchronously so waitForPhase() can always see the
    // complete task map. Execution itself is gated by waitForEarlierPhases().
    const ordered = [...this.stages].sort((a, b) => a.phase - b.phase);
    for (const def of ordered) {
      this.resolvedTasks[def.id] = this.runOne(def);
    }

    this.runPromise = Promise.allSettled(Object.values(this.resolvedTasks))
      .then(() => this.snapshot());
    return this.runPromise;
  }

  async waitForPhase(phase: 0 | 1 | 2): Promise<RunnerSnapshot> {
    if (!this.started) void this.run();
    const ids = this.stages.filter(stage => stage.phase <= phase).map(stage => stage.id);
    await Promise.allSettled(ids.map(id => this.resolvedTasks[id]).filter(Boolean));
    return this.snapshot();
  }
}
