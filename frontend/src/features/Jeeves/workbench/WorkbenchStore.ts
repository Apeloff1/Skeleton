import { HANDOFF_KEY, RECOVERY_KEY, WORKBENCH_KEY } from './types';
import type { ChatHandoff, Entity, MutationContext, Workbench } from './types';
import type { Command, MutationResult } from './domain';
import { applyCommand, createWorkbench } from './domain';
import { parseWorkbench, WorkbenchError } from './validation';
import { inspectIntegrity } from './integrity';
import { mergeBackup, previewBackup, replaceFromBackup } from './backup';
import { captureMessage } from './capture';
import type { CaptureInput } from './capture';

export interface WorkbenchStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface WorkbenchSnapshot {
  state: Workbench;
  ready: boolean;
  loading: boolean;
  saveStatus: 'idle' | 'saving' | 'saved' | 'failed' | 'conflict';
  error: string | null;
  notice: string | null;
  lastSavedAt: number | null;
  recoveryAvailable: boolean;
  undoAvailable: boolean;
  redoAvailable: boolean;
}

export interface StoreClock {
  now(): number;
  id(): string;
}

const defaultClock: StoreClock = {
  now: () => Date.now(),
  id: () => globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
};

/** Shared in-memory store with ordered persistence, bounded undo, and explicit conflict recovery. */
export class WorkbenchStore {
  private snapshot: WorkbenchSnapshot;
  private listeners = new Set<() => void>();
  private opening: Promise<void> | null = null;
  private writing: Promise<void> | null = null;
  private pending: Workbench | null = null;
  private lastStored: string | null = null;
  private history: Workbench[] = [];
  private future: Workbench[] = [];
  private generation = 0;
  private entityRevisions = new Map<string, number>();

  constructor(
    private readonly storage: WorkbenchStorage,
    private readonly clock: StoreClock = defaultClock,
  ) {
    this.snapshot = {
      state: createWorkbench(this.context()),
      ready: false,
      loading: false,
      saveStatus: 'idle',
      error: null,
      notice: null,
      lastSavedAt: null,
      recoveryAvailable: false,
      undoAvailable: false,
      redoAvailable: false,
    };
  }

  getSnapshot = (): WorkbenchSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private context(): MutationContext {
    return { now: this.clock.now(), id: () => this.clock.id() };
  }

  private emit(patch: Partial<WorkbenchSnapshot>): void {
    if (patch.state) {
      for (const collection of [patch.state.projects, patch.state.tasks, patch.state.notes, patch.state.sources, patch.state.cards, patch.state.reviews, patch.state.prompts, patch.state.sessions]) {
        for (const record of collection) this.entityRevisions.set(record.id, Math.max(record.revision, this.entityRevisions.get(record.id) || 0));
      }
    }
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }

  notify = (notice: string): void => {
    this.emit({ notice });
  };

  dismissNotice = (): void => {
    this.emit({ notice: null });
  };

  initialize(): Promise<void> {
    if (this.snapshot.ready) return Promise.resolve();
    if (this.opening) return this.opening;
    this.opening = this.load().finally(() => { this.opening = null; });
    return this.opening;
  }

  private async load(): Promise<void> {
    this.emit({ loading: true, error: null });
    try {
      const raw = await this.storage.getItem(WORKBENCH_KEY);
      const recovery = await this.storage.getItem(RECOVERY_KEY);
      this.emit({ recoveryAvailable: recovery !== null });
      let state = this.snapshot.state;
      if (raw !== null) {
        const parsed = parseWorkbench(raw);
        if (!parsed.ok) throw new WorkbenchError(parsed.issues.map(issue => issue.message).join(' '));
        const integrity = inspectIntegrity(parsed.value);
        if (integrity.length) throw new WorkbenchError(integrity.map(issue => issue.message).join(' '));
        state = parsed.value;
      }
      this.lastStored = raw;
      this.emit({ state, ready: true, loading: false, error: null, saveStatus: raw === null ? 'idle' : 'saved' });
      if (raw === null) this.enqueue(state);
    } catch (error) {
      this.emit({
        loading: false,
        ready: false,
        error: `Could not open saved work. ${error instanceof Error ? error.message : 'Device storage is unavailable.'} Existing data has not been changed.`,
        saveStatus: 'failed',
      });
    }
  }

  dispatch(command: Command): MutationResult | null {
    if (!this.snapshot.ready) {
      this.notify('Wait until the workbench has opened.');
      return null;
    }
    if (this.snapshot.saveStatus === 'conflict') {
      this.notify('Resolve the other-tab conflict before making more changes. Export your current work first.');
      return null;
    }
    try {
      const result = applyCommand(this.snapshot.state, command, this.context());
      this.remember(this.snapshot.state);
      this.future = [];
      this.emit({
        state: result.state,
        notice: null,
        undoAvailable: this.history.length > 0,
        redoAvailable: false,
      });
      this.enqueue(result.state);
      return result;
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'The change could not be applied.');
      return null;
    }
  }

  private remember(state: Workbench): void {
    this.history.push(state);
    // Keep undo useful without retaining twenty copies of a near-capacity workbench.
    let total = this.history.reduce((sum, item) => sum + JSON.stringify(item).length, 0);
    while (this.history.length > 20 || (total > 8 * 1024 * 1024 && this.history.length > 1)) {
      total -= JSON.stringify(this.history.shift()).length;
    }
  }

  dispatchBatch(commands: Command[]): boolean {
    if (!this.snapshot.ready || this.snapshot.saveStatus === 'conflict') return false;
    if (!commands.length || commands.length > 500) {
      this.notify('A batch must contain between 1 and 500 changes.');
      return false;
    }
    try {
      let state = this.snapshot.state;
      const context = this.context();
      for (const command of commands) state = applyCommand(state, command, context).state;
      this.remember(this.snapshot.state);
      this.future = [];
      this.emit({ state, notice: `Applied ${commands.length} changes.`, undoAvailable: true, redoAvailable: false });
      this.enqueue(state);
      return true;
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'The batch could not be applied. No records were changed.');
      return false;
    }
  }

  undo = (): void => {
    if (!this.snapshot.ready || !this.history.length || this.snapshot.saveStatus === 'conflict') return;
    const previous = this.history.pop()!;
    this.future.push(this.snapshot.state);
    this.restoreMemory(previous, 'Undid the last workbench change.');
  };

  redo = (): void => {
    if (!this.snapshot.ready || !this.future.length || this.snapshot.saveStatus === 'conflict') return;
    const next = this.future.pop()!;
    this.remember(this.snapshot.state);
    this.restoreMemory(next, 'Restored the change.');
  };

  private restoreMemory(target: Workbench, notice: string): void {
    // Undo restores content, but never reuses a revision accepted by an older open editor.
    const restore = <T extends Entity>(records: T[]): T[] => records.map(record => ({
      ...record,
      revision: Math.max(record.revision, this.entityRevisions.get(record.id) || 0) + 1,
    }));
    const state = {
      ...target,
      projects: restore(target.projects),
      tasks: restore(target.tasks),
      notes: restore(target.notes),
      sources: restore(target.sources),
      cards: restore(target.cards),
      reviews: restore(target.reviews),
      prompts: restore(target.prompts),
      sessions: restore(target.sessions),
      revision: this.snapshot.state.revision + 1,
      updatedAt: Math.max(this.snapshot.state.updatedAt, this.clock.now()),
    };
    this.emit({ state, notice, undoAvailable: !!this.history.length, redoAvailable: !!this.future.length });
    this.enqueue(state);
  }

  private enqueue(state: Workbench): void {
    this.pending = state;
    this.emit({ saveStatus: 'saving' });
    if (!this.writing) {
      this.writing = this.drain().finally(() => {
        this.writing = null;
        if (this.pending && this.snapshot.saveStatus !== 'conflict') this.enqueue(this.pending);
      });
    }
  }

  private async drain(): Promise<void> {
    const generation = this.generation;
    while (this.pending && generation === this.generation) {
      const state = this.pending;
      this.pending = null;
      try {
        const existing = await this.storage.getItem(WORKBENCH_KEY);
        if (generation !== this.generation) return;
        if (existing !== this.lastStored) {
          this.pending = null;
          this.emit({ saveStatus: 'conflict', notice: 'Another tab or session changed the saved workbench. Export your in-memory work, then reload the saved version to avoid overwriting it.' });
          return;
        }
        const previous = existing === null ? null : parseWorkbench(existing);
        if (existing !== null && previous?.ok && !inspectIntegrity(previous.value).length) {
          await this.storage.setItem(RECOVERY_KEY, existing);
          this.emit({ recoveryAvailable: true });
        }
        const encoded = JSON.stringify(state);
        await this.storage.setItem(WORKBENCH_KEY, encoded);
        this.lastStored = encoded;
        if (!this.pending) this.emit({ saveStatus: 'saved', lastSavedAt: this.clock.now() });
      } catch {
        this.pending = null;
        this.emit({ saveStatus: 'failed', notice: 'Changes remain in memory, but device storage could not save them. Export a backup or retry saving.' });
        return;
      }
    }
  }

  retrySave = (): void => {
    if (!this.snapshot.ready || this.snapshot.saveStatus === 'conflict') return;
    this.enqueue(this.snapshot.state);
  };

  async settled(): Promise<void> {
    while (this.writing) await this.writing;
  }

  async reloadSaved(): Promise<void> {
    await this.settled();
    this.generation++;
    this.pending = null;
    this.history = [];
    this.future = [];
    this.emit({ ready: false, undoAvailable: false, redoAvailable: false });
    await this.load();
  }

  async restoreRecovery(): Promise<boolean> {
    await this.settled();
    try {
      const raw = await this.storage.getItem(RECOVERY_KEY);
      if (!raw) throw new WorkbenchError('No recovery snapshot is available.');
      const parsed = parseWorkbench(raw);
      if (!parsed.ok || inspectIntegrity(parsed.value).length) throw new WorkbenchError('The recovery snapshot is not valid.');
      const current = await this.storage.getItem(WORKBENCH_KEY);
      this.lastStored = current;
      const state = { ...parsed.value, revision: parsed.value.revision + 1, updatedAt: Math.max(parsed.value.updatedAt, this.clock.now()) };
      this.history = [];
      this.future = [];
      this.emit({ state, ready: true, error: null, notice: 'Recovery snapshot restored. Export a backup before making further changes.', undoAvailable: false, redoAvailable: false });
      this.enqueue(state);
      await this.settled();
      return this.snapshot.saveStatus === 'saved';
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Recovery failed.');
      return false;
    }
  }

  importBackup(raw: string, mode: 'merge' | 'replace'): boolean {
    if (!this.snapshot.ready || this.snapshot.saveStatus === 'conflict') return false;
    try {
      const parsed = previewBackup(raw);
      if (!parsed.ok) throw new WorkbenchError(parsed.issues.map(issue => issue.message).join('\n'));
      const state = mode === 'merge'
        ? mergeBackup(this.snapshot.state, parsed.value.imported, this.context())
        : replaceFromBackup(this.snapshot.state, parsed.value.imported, this.context());
      this.remember(this.snapshot.state);
      this.future = [];
      this.emit({ state, notice: mode === 'merge' ? 'Imported records as separate projects.' : 'Replaced the workbench. Undo is available during this visit.', undoAvailable: true, redoAvailable: false });
      this.enqueue(state);
      return true;
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Import failed.');
      return false;
    }
  }

  async handoff(value: ChatHandoff): Promise<boolean> {
    try {
      await this.storage.setItem(HANDOFF_KEY, JSON.stringify(value));
      return true;
    } catch {
      this.notify('The chat draft could not be saved. Free some device storage and try again.');
      return false;
    }
  }

  capture(input: CaptureInput): boolean {
    if (!this.snapshot.ready || this.snapshot.saveStatus === 'conflict') return false;
    try {
      const result = captureMessage(this.snapshot.state, input, this.context());
      if (result.duplicate) {
        this.notify('This message is already saved in this project’s notebook.');
        return true;
      }
      this.remember(this.snapshot.state);
      this.future = [];
      this.emit({ state: result.state, notice: 'Message saved as an unverified note with its conversation source.', undoAvailable: true, redoAvailable: false });
      this.enqueue(result.state);
      return true;
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Could not save the message.');
      return false;
    }
  }
}
