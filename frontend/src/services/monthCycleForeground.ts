/**
 * Explicitly owned foreground driver for month-cycle recovery.
 *
 * Invocations are bounded and low-cadence (default 15 minutes). The driver
 * holds at most one timer and one reconciliation pass, stops when the UI
 * backgrounds or unmounts, and triggers a fresh due scan upon foreground.
 * It cannot execute after the process exits and does not start server jobs.
 */
import { MonthCycleRecovery, type MonthCycleRecoveryReport } from './monthCycleRecovery';

export interface ForegroundObserver {
  currentState?: string;
  addEventListener(
    kind: 'change', listener: (state: string) => void,
  ): { remove(): void };
}
export interface MonthCycleForegroundOptions {
  cadenceMs?: number;
  onReport?: (report: MonthCycleRecoveryReport) => void;
  onError?: (error: unknown) => void;
}
function safeCadence(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(60_000, Math.min(6 * 60 * 60_000, Math.floor(value)))
    : 15 * 60_000;
}
export class MonthCycleForegroundDriver {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private subscription: { remove(): void } | null = null;
  private epoch = 0;
  private running = false;
  private started = false;
  private disposed = false;
  private active: boolean;
  private readonly cadenceMs: number;
  private readonly onReport?: (report: MonthCycleRecoveryReport) => void;
  private readonly onError?: (error: unknown) => void;

  constructor(
    private readonly appState: ForegroundObserver,
    private readonly recovery: MonthCycleRecovery,
    options: MonthCycleForegroundOptions = {},
  ) {
    this.active = !['background', 'inactive'].includes(appState.currentState || '');
    this.cadenceMs = safeCadence(options.cadenceMs);
    this.onReport = options.onReport;
    this.onError = options.onError;
  }
  start(): () => void {
    if (this.disposed) throw new Error('Foreground recovery driver already disposed');
    if (this.started) return () => this.dispose();
    this.started = true;
    this.subscription = this.appState.addEventListener('change', state => {
      if (this.disposed) return;
      const active = !['background', 'inactive'].includes(state);
      if (active === this.active) return;
      this.active = active;
      this.epoch++;
      if (this.timer) clearTimeout(this.timer);
      this.timer = null;
      if (!active) this.recovery.stop();
      else this.schedule(0);
    });
    if (this.active) this.schedule(0);
    return () => this.dispose();
  }
  private schedule(delay: number) {
    if (this.disposed || !this.started || !this.active || this.timer) return;
    const epoch = this.epoch;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.disposed || !this.active || epoch !== this.epoch) return;
      void this.reconcile(epoch);
    }, delay);
  }
  private async reconcile(epoch: number) {
    if (this.running) return;
    this.running = true;
    try {
      const report = await this.recovery.reconcileDue();
      if (this.disposed || epoch !== this.epoch || !this.active) return;
      try { this.onReport?.(report); } catch { /* optional view callback */ }
    } catch (error) {
      if (this.disposed || epoch !== this.epoch || !this.active) return;
      try { this.onError?.(error); } catch { /* optional view callback */ }
    } finally {
      this.running = false;
      if (!this.disposed && this.active) {
        // If a foreground transition happened mid-pass, arrange an immediate
        // refresh rather than losing the only wakeup until the next cadence.
        this.schedule(epoch !== this.epoch ? 0 : this.cadenceMs);
      }
    }
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.epoch++;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.recovery.stop();
    this.subscription?.remove();
    this.subscription = null;
  }
  get status() {
    return {
      started: this.started, active: this.active,
      running: this.running, armed: this.timer !== null,
      disposed: this.disposed,
    };
  }
}
