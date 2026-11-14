/**
 * Non-overlapping native storage mutations.
 *
 * An AsyncStorage timeout is only a JS deadline. Native I/O may keep running.
 * Retain ownership of affected keys until the physical promise settles;
 * reject overlapping mutations rather than claiming newer values persisted.
 *
 * No queues or growing retry backlog: a stalled key owns at most one
 * underlying native request. Independent keys remain concurrent.
 */
export const MAX_NATIVE_MUTATION_KEYS = 256;

export class NativeMutationFence {
  private readonly pending = new Map<string, Promise<void>>();
  private paused = false;

  /** Fence new operations and await the actual completion of all old writes. */
  pauseAndDrain(): Promise<void> {
    this.paused = true;
    return Promise.all([...new Set(this.pending.values())]).then(() => undefined);
  }

  resume(): void {
    this.paused = false;
  }

  run(keys: readonly string[], operation: () => Promise<void>): Promise<boolean> {
    const unique = [...new Set(keys)];
    if (this.paused) return Promise.resolve(false);
    if (unique.length === 0) return Promise.resolve(true);
    // Global bound protects low-RAM devices if many independent storage
    // writes hang. Oversized bulk deletes are denied, never partially applied.
    if (unique.length > MAX_NATIVE_MUTATION_KEYS ||
        this.pending.size + unique.length > MAX_NATIVE_MUTATION_KEYS) return Promise.resolve(false);
    if (unique.some(key => this.pending.has(key))) return Promise.resolve(false);

    const executed = Promise.resolve().then(operation);
    const settled = executed.then(() => undefined, () => undefined);
    for (const key of unique) this.pending.set(key, settled);
    void settled.then(() => {
      for (const key of unique) {
        if (this.pending.get(key) === settled) this.pending.delete(key);
      }
    });
    return executed.then(() => true, () => false);
  }

  isBusy(key: string): boolean {
    return this.pending.has(key);
  }

  get inFlight(): number {
    return new Set(this.pending.values()).size;
  }
}
