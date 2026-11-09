/**
 * src/boot/runner.ts — SOTA parallel DAG runner for frontend boot.
 *
 * 2026-05 batch upgrades:
 *   • Per-stage retry with exponential backoff. Stages that declare
 *     ``retries`` will be re-attempted up to that many times after a
 *     failure or timeout. The `attempts` field on `StageState` reflects
 *     the total attempts run so far.
 *   • Cancellable. Every stage's `run()` now receives an AbortSignal.
 *     Calling `runner.cancel()` triggers it; in-flight stages should
 *     bail out promptly. Pending stages skip immediately.
 *   • Phase-aware snapshot — `phaseProgress[0..2]` exposes a 0–100
 *     weighted score for EACH phase, so the UI can show a phase-1
 *     "background prep" chip independently of the main bar.
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
  bootScore: number;             // 0–100 across ALL phases, weighted
  phaseProgress: { 0: number; 1: number; 2: number }; // per-phase weighted %
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

function _withTimeout<T>(
  p: Promise<T>,
  ms: number,
  signal?: AbortSignal,
): Promise<TimeoutResult<T>> {
  return new Promise(resolve => {
    let done = false;
    const finish = (r: TimeoutResult<T>) => { if (!done) { done = true; resolve(r); } };
    const t = setTimeout(() => finish({ ok: false, reason: 'timeout' }), ms);
    const onAbort = () => { clearTimeout(t); finish({ ok: false, reason: 'aborted' }); };
    if (signal?.aborted) { clearTimeout(t); return finish({ ok: false, reason: 'aborted' }); }
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);
    p.then(v => { clearTimeout(t); finish({ ok: true, v }); })
     .catch(e => { clearTimeout(t); finish({ ok: false, reason: e?.message || 'error' }); });
  });
}

function _sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('aborted'));
    const t = setTimeout(resolve, ms);
    const onAbort = () => { clearTimeout(t); reject(new Error('aborted')); };
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);
  });
}

export class BootRunner {
  private states: Record<string, StageState>;
  private listeners: Set<Listener> = new Set();
  private startedAt = Date.now();
  private resolvedTasks: Record<string, Promise<void>> = {};
  private aborter: AbortController | null = null;
  private _started = false;

  constructor(private stages: BootStageDef[]) {
    this.states = Object.fromEntries(stages.map(s => [s.id, {
      id: s.id, label: s.label, status: 'pending' as StageStatus,
      attempts: 0, critical: s.critical, weight: s.weight, phase: s.phase, deps: [...s.deps],
    } as StageState]));
    this.aborter = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  }

  on(fn: Listener): () => void {
    this.listeners.add(fn);
    try { fn(this.snapshot()); } catch {}
    return () => { this.listeners.delete(fn); };
  }

  private _emit() {
    const snap = this.snapshot();
    this.listeners.forEach(fn => { try { fn(snap); } catch {} });
  }

  /** Compute per-phase weighted progress (0–100). */
  private _phaseProgress(): { 0: number; 1: number; 2: number } {
    const out = { 0: 0, 1: 0, 2: 0 } as { 0: number; 1: number; 2: number };
    for (const p of [0, 1, 2] as const) {
      const ph = Object.values(this.states).filter(s => s.phase === p);
      if (ph.length === 0) { out[p] = 100; continue; }
      const totalW = ph.reduce((a, s) => a + s.weight, 0) || 1;
      const okW = ph.filter(s => s.status === 'ok').reduce((a, s) => a + s.weight, 0);
      out[p] = Math.round((100 * okW / totalW) * 10) / 10;
    }
    return out;
  }

  snapshot(): RunnerSnapshot {
    const list = Object.values(this.states);
    const total = list.length;
    const ok = list.filter(s => s.status === 'ok').length;
    const failed = list.filter(s => s.status === 'failed' || s.status === 'timed_out').length;
    const skipped = list.filter(s => s.status === 'skipped').length;
    const pending = list.filter(s => s.status === 'pending' || s.status === 'running').length;
    const criticalOk = list.every(s => !s.critical || s.status === 'ok');
    const totalW = list.reduce((a, s) => a + s.weight, 0) || 1;
    const okW = list.filter(s => s.status === 'ok').reduce((a, s) => a + s.weight, 0);
    const phaseDone = { 0: false, 1: false, 2: false } as { 0: boolean; 1: boolean; 2: boolean };
    for (const p of [0, 1, 2] as const) {
      const ph = list.filter(s => s.phase === p);
      phaseDone[p] = ph.length > 0 && ph.every(s => s.status !== 'pending' && s.status !== 'running');
    }
    return {
      ok: failed === 0 && criticalOk,
      bootScore: Math.round((100.0 * okW / totalW) * 10) / 10,
      phaseProgress: this._phaseProgress(),
      counts: { ok, failed, skipped, pending, total },
      criticalOk, elapsedMs: Date.now() - this.startedAt,
      stages: { ...this.states }, phaseDone,
      cancelled: !!this.aborter?.signal?.aborted,
    };
  }

  /** Abort all in-flight stages and skip pending ones. */
  cancel(): void {
    try { this.aborter?.abort(); } catch {}
    // Snap all still-pending stages to skipped.
    for (const st of Object.values(this.states)) {
      if (st.status === 'pending' || st.status === 'running') {
        st.status = 'skipped';
        st.error = st.error || 'cancelled';
      }
    }
    trail.add('boot', 'runner_cancelled', {}, 'warn');
    this._emit();
  }

  private async _runOne(def: BootStageDef): Promise<void> {
    const st = this.states[def.id];
    const sig = this.aborter?.signal;

    // Wait for dependencies (any dep that critically-failed → skip).
    for (const d of def.deps) {
      const depPromise = this.resolvedTasks[d];
      if (depPromise) {
        try { await depPromise; } catch { /* swallow — we check state below */ }
      }
      const dep = this.states[d];
      if (!dep || (dep.critical && dep.status !== 'ok')) {
        st.status = 'skipped';
        st.error = `dep failed: ${d}`;
        trail.add('boot', `stage_skipped ${def.id}`, { dep: d }, 'warn');
        this._emit();
        return;
      }
    }

    // Already cancelled?
    if (sig?.aborted) {
      st.status = 'skipped';
      st.error = 'cancelled';
      this._emit();
      return;
    }

    const maxAttempts = 1 + Math.max(0, def.retries ?? 0);
    const backoffBase = def.backoffMs ?? 250;
    st.startedAt = Date.now();

    let lastResult: TimeoutResult<StageRun> = { ok: false, reason: 'init' };

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      if (sig?.aborted) {
        st.status = 'skipped';
        st.error = 'cancelled';
        st.attempts = attempt - 1;
        st.endedAt = Date.now();
        st.durationMs = st.endedAt - st.startedAt!;
        this._emit();
        return;
      }

      st.attempts = attempt;
      st.status = 'running';
      this._emit();
      trail.add('boot', `stage_started ${def.id}`,
        { attempt, max: maxAttempts }, 'info');

      lastResult = await _withTimeout<StageRun>(def.run(sig), def.timeoutMs, sig);

      // Success? Done.
      if (lastResult.ok && lastResult.v && (lastResult.v as StageRun).ok) {
        st.endedAt = Date.now();
        st.durationMs = st.endedAt - st.startedAt!;
        st.status = 'ok';
        trail.add('boot', `stage_ok ${def.id}`,
          { ms: st.durationMs, attempts: attempt }, 'info');
        this._emit();
        return;
      }

      // Aborted? Bail without retrying.
      if (lastResult.reason === 'aborted' || sig?.aborted) {
        st.endedAt = Date.now();
        st.durationMs = st.endedAt - st.startedAt!;
        st.status = 'skipped';
        st.error = 'cancelled';
        this._emit();
        return;
      }

      // Soft-fail (returned {ok:false}) — record reason but still retry if budget left.
      const note = (lastResult.ok && lastResult.v) ? lastResult.v.note : lastResult.reason;
      trail.add('boot', `stage_attempt_failed ${def.id}`,
        { attempt, max: maxAttempts, reason: note }, 'warn');

      if (attempt < maxAttempts) {
        const wait = backoffBase * Math.pow(2, attempt - 1);
        try { await _sleep(wait, sig); }
        catch {
          // aborted during backoff
          st.endedAt = Date.now();
          st.durationMs = st.endedAt - st.startedAt!;
          st.status = 'skipped';
          st.error = 'cancelled';
          this._emit();
          return;
        }
      }
    }

    // Out of attempts — finalize as failed/timed_out.
    st.endedAt = Date.now();
    st.durationMs = st.endedAt - st.startedAt!;
    if (lastResult.reason === 'timeout') {
      st.status = 'timed_out';
      st.error = 'timeout';
    } else if (lastResult.ok && lastResult.v && !(lastResult.v as StageRun).ok) {
      st.status = 'failed';
      st.error = (lastResult.v as StageRun).note || 'failed';
    } else {
      st.status = 'failed';
      st.error = lastResult.reason || 'failed';
    }
    trail.add('boot', `stage_failed ${def.id}`,
      { reason: st.error, ms: st.durationMs, attempts: maxAttempts }, 'error');
    this._emit();
  }

  async run(): Promise<RunnerSnapshot> {
    this._started = true;
    for (const def of this.stages) {
      this.resolvedTasks[def.id] = this._runOne(def);
    }
    return Promise.allSettled(Object.values(this.resolvedTasks)).then(() => this.snapshot());
  }

  async waitForPhase(phase: 0 | 1 | 2): Promise<RunnerSnapshot> {
    // Belt-and-braces: if the caller awaits a phase before invoking run(),
    // `resolvedTasks` would be empty and Promise.allSettled([]) resolves
    // instantly with everything still 'pending' (criticalOk=false). Auto-
    // start so waitForPhase ALWAYS reflects real stage completion.
    if (!this._started) this.run();
    const ids = this.stages.filter(s => s.phase <= phase).map(s => s.id);
    await Promise.allSettled(ids.map(i => this.resolvedTasks[i]).filter(Boolean));
    return this.snapshot();
  }
}
