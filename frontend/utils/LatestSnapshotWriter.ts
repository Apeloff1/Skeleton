/**
 * At most one native write in flight, plus the latest pending snapshot.
 *
 * Diagnostic persistence is best-effort. Never create an unbounded promise
 * chain when native storage stops responding. The pending slot is bounded
 * independently of the number of trace events produced during an outage.
 *
 * pauseAndDiscard() fences pending writes while an operator resets state.
 * Callers MUST wait for idle before removing keys; a hung in-flight native
 * write means reset cannot be confirmed and should be reported as failed.
 */
export class LatestSnapshotWriter {
  private pending: string | null = null;
  private active: Promise<void> | null = null;
  private paused = false;

  constructor(private readonly write: (snapshot: string) => Promise<void>) {}

  enqueue(snapshot: string): void {
    if (this.paused) return;
    this.pending = snapshot;
    this.start();
  }

  private start(): void {
    if (this.paused || this.active || this.pending === null) return;
    const snapshot = this.pending;
    this.pending = null;
    const operation = Promise.resolve().then(() => this.write(snapshot));
    this.active = operation.then(
      () => undefined,
      () => undefined,
    ).then(() => {
      this.active = null;
      this.start();
    });
  }

  pauseAndDiscard(): Promise<void> {
    this.paused = true;
    this.pending = null;
    return this.active ?? Promise.resolve();
  }

  resume(): void {
    this.paused = false;
    this.start();
  }

  get pendingCount(): number {
    return Number(this.pending !== null) + Number(this.active !== null);
  }
}
