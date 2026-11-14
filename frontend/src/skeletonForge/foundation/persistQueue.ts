/**
 * Coalescing, generation-fenced saver for the Studio shell.
 *
 * The shell saves the whole snapshot after every reducer change. Without a
 * queue, a burst of edits stacks one full device write per keystroke, and
 * outcomes race: an older write's success can clear the banner for a newer
 * failed write, and a manual "Retry save" can report over an automatic save.
 *
 * Contract:
 *  - At most one write in flight. While it runs, later snapshots collapse
 *    into a single pending slot (the newest wins), so the newest state
 *    always reaches the device and stale snapshots are never written after it.
 *  - `onSettled` reports only the outcome of the newest snapshot that has
 *    been written. Outcomes of superseded writes are never reported.
 *  - `idle()` resolves after the queue drains, for tests and teardown.
 *  - `close()` stops reporting but still writes the newest pending snapshot,
 *    so unmounting the shell never drops the user's last edit.
 *  - After `dispose()` nothing more is written or reported.
 */
export interface SaveOutcome {
  ok: boolean;
  error: unknown;
  generation: number;
}

export interface SnapshotSaver<T> {
  enqueue: (snapshot: T) => number;
  idle: () => Promise<void>;
  close: () => void;
  dispose: () => void;
  readonly inFlight: boolean;
  readonly pending: boolean;
}

export function createSnapshotSaver<T>(
  write: (snapshot: T) => Promise<void>,
  onSettled: (outcome: SaveOutcome) => void,
): SnapshotSaver<T> {
  let generation = 0;
  let pending: { snapshot: T; generation: number } | null = null;
  let active: Promise<void> | null = null;
  let disposed = false;
  let silenced = false;
  const waiters: Array<() => void> = [];

  const drained = () => {
    while (waiters.length) waiters.shift()!();
  };

  const pump = () => {
    if (disposed || active || !pending) {
      if (!active && !pending) drained();
      return;
    }
    const job = pending;
    pending = null;
    let outcome: SaveOutcome;
    active = Promise.resolve()
      .then(() => write(job.snapshot))
      .then(() => { outcome = { ok: true, error: null, generation: job.generation }; },
        (error: unknown) => { outcome = { ok: false, error, generation: job.generation }; })
      .then(() => {
        active = null;
        // A newer snapshot is queued: this result is superseded, because the
        // next write carries the complete newer state.
        if (!disposed && !silenced && !pending && job.generation === generation) onSettled(outcome);
        pump();
      });
  };

  return {
    enqueue(snapshot: T) {
      if (disposed || silenced) return generation;
      generation += 1;
      pending = { snapshot, generation };
      pump();
      return generation;
    },
    idle() {
      if (!active && !pending) return Promise.resolve();
      return new Promise<void>((resolve) => { waiters.push(resolve); });
    },
    close() {
      silenced = true;
      pump();
    },
    dispose() {
      disposed = true;
      pending = null;
      drained();
    },
    get inFlight() { return active !== null; },
    get pending() { return pending !== null; },
  };
}
