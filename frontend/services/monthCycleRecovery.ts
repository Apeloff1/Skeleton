/**
 * Bounded foreground reconciliation of durable month-cycle receipts.
 *
 * This controller NEVER drives backend execution. It only queries a job's
 * authoritative status when the application invokes a recovery pass (e.g.
 * cold boot / foreground / explicit resume). No promise or JS timer can run
 * while the process is terminated; backend scheduling is a separate concern.
 */
import {
  MonthCycleLedger, type MonthCycleRecord,
} from './monthCycleLedger';

export type MonthCycleObservation =
  | { phase: 'running'; cursor?: number }
  | { phase: 'disconnected' }
  | { phase: 'completed' | 'failed' | 'cancelled'; cursor?: number };
export type MonthCycleWorker = (
  record: Readonly<MonthCycleRecord>, signal: AbortSignal,
) => Promise<MonthCycleObservation>;
export interface MonthCycleRecoveryOptions {
  maxConcurrent?: number;
  batchSize?: number;
  timeoutMs?: number;
  baseRetryMs?: number;
  maxRetryMs?: number;
  onObserved?: (record: MonthCycleRecord) => void;
}
export interface MonthCycleRecoveryReport {
  attempted: number;
  stillRunning: number;
  disconnected: number;
  terminalObserved: number;
  skipped: number;
  interrupted: boolean;
}
function finite(value: number | undefined, fallback: number, min: number, max: number) {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(min, Math.min(max, Math.floor(value))) : fallback;
}
function delayedRetry(record: MonthCycleRecord, opts: {
  base: number; max: number; disconnected: boolean;
}): number {
  const exponent = opts.disconnected
    ? Math.min(12, record.failures) : 0;
  const next = Math.min(opts.max, opts.base * (2 ** exponent));
  // Stable, inexpensive per-operation spreading to avoid a thundering herd
  // after app resume; a bounded 0-20% additive delay is reproducible.
  let hash = 0;
  for (let i = 0; i < record.operationId.length; i++) {
    hash = (Math.imul(hash, 31) + record.operationId.charCodeAt(i)) | 0;
  }
  return next + Math.floor(next * ((hash >>> 0) % 21) / 100);
}
async function observeBounded(
  worker: MonthCycleWorker, record: MonthCycleRecord,
  signal: AbortSignal, timeoutMs: number,
): Promise<MonthCycleObservation | null> {
  if (signal.aborted) return null;
  const own = new AbortController();
  const abort = () => own.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) own.abort();
  let rejectAbort = () => {};
  const aborted = new Promise<never>((_resolve, reject) => {
    rejectAbort = () => reject(new Error('Observation interrupted'));
    if (own.signal.aborted) rejectAbort();
    else own.signal.addEventListener('abort', rejectAbort, { once: true });
  });
  const timer = setTimeout(() => own.abort(), timeoutMs);
  try {
    return await Promise.race([
      Promise.resolve().then(() => worker(record, own.signal)),
      aborted,
    ]);
  } catch {
    return signal.aborted ? null : { phase: 'disconnected' };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
    own.signal.removeEventListener('abort', rejectAbort);
  }
}
export class MonthCycleRecovery {
  private readonly concurrency: number;
  private readonly batchSize: number;
  private readonly timeoutMs: number;
  private readonly baseRetryMs: number;
  private readonly maxRetryMs: number;
  private readonly onObserved?: (record: MonthCycleRecord) => void;
  private batch: Promise<MonthCycleRecoveryReport> | null = null;
  private controller: AbortController | null = null;

  constructor(
    private readonly ledger: MonthCycleLedger,
    private readonly worker: MonthCycleWorker,
    options: MonthCycleRecoveryOptions = {},
  ) {
    this.concurrency = finite(options.maxConcurrent, 2, 1, 4);
    this.batchSize = finite(options.batchSize, 16, 1, 32);
    this.timeoutMs = finite(options.timeoutMs, 15_000, 250, 120_000);
    this.baseRetryMs = finite(options.baseRetryMs, 5 * 60_000, 30_000, 6 * 60 * 60_000);
    this.maxRetryMs = Math.max(this.baseRetryMs,
      finite(options.maxRetryMs, 6 * 60 * 60_000, 30_000, 7 * 24 * 60 * 60_000));
    this.onObserved = options.onObserved;
  }
  stop() { this.controller?.abort(); }
  reconcileDue(now = Date.now()): Promise<MonthCycleRecoveryReport> {
    if (this.batch) return this.batch;
    const controller = new AbortController();
    this.controller = controller;
    const job = this.reconcile(now, controller.signal);
    this.batch = job;
    const cleanup = () => {
      if (this.batch === job) this.batch = null;
      if (this.controller === controller) this.controller = null;
    };
    void job.then(cleanup, cleanup);
    return job;
  }
  private async reconcile(now: number, signal: AbortSignal): Promise<MonthCycleRecoveryReport> {
    const report: MonthCycleRecoveryReport = {
      attempted: 0, stillRunning: 0, disconnected: 0,
      terminalObserved: 0, skipped: 0, interrupted: false,
    };
    const due = await this.ledger.due(now, this.batchSize);
    let cursor = 0;
    const next = async () => {
      while (!signal.aborted) {
        const index = cursor++;
        if (index >= due.length) return;
        const record = due[index];
        const observed = await observeBounded(this.worker, record, signal, this.timeoutMs);
        if (!observed || signal.aborted) {
          report.skipped++;
          break;
        }
        report.attempted++;
        const sampledAt = Math.max(now, Date.now());
        if (observed.phase === 'disconnected') {
          const dueAt = sampledAt + delayedRetry(record, {
            base: this.baseRetryMs, max: this.maxRetryMs, disconnected: true,
          });
          const receipt = await this.ledger.observe(record, {
            phase: 'disconnected', nextCheckAt: Math.min(
              sampledAt + 7 * 24 * 60 * 60_000, dueAt,
            ), now: sampledAt,
          });
          if (receipt) { report.disconnected++; this.notify(receipt); }
        } else if (observed.phase === 'running') {
          const dueAt = sampledAt + delayedRetry(record, {
            base: this.baseRetryMs, max: this.maxRetryMs, disconnected: false,
          });
          const receipt = await this.ledger.observe(record, {
            phase: 'observing', cursor: observed.cursor,
            nextCheckAt: Math.min(sampledAt + 7 * 24 * 60 * 60_000, dueAt),
            now: sampledAt,
          });
          if (receipt) { report.stillRunning++; this.notify(receipt); }
        } else {
          const receipt = await this.ledger.observe(record, {
            phase: 'terminal_observed', terminalState: observed.phase,
            cursor: observed.cursor, now: sampledAt,
          });
          if (receipt) { report.terminalObserved++; this.notify(receipt); }
        }
      }
    };
    await Promise.all(Array.from(
      { length: Math.min(this.concurrency, due.length) }, () => next(),
    ));
    report.interrupted = signal.aborted;
    report.skipped += Math.max(0, due.length - cursor);
    return report;
  }
  private notify(record: MonthCycleRecord) {
    try { this.onObserved?.({ ...record }); } catch { /* display callbacks are optional */ }
  }
}
