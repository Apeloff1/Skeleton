/**
 * Tiny typed query cache: keyed entries, stale time, in-flight de-duplication,
 * invalidation and subscriptions. Framework-free; `useQuery` adapts it to React.
 */
export type QueryStatus = 'idle' | 'loading' | 'success' | 'error';

export interface QueryState<T> {
  status: QueryStatus;
  data: T | undefined;
  error: Error | null;
  updatedAt: number;
  fetching: boolean;
}

export type QueryKey = string | readonly (string | number | boolean | null | undefined)[];
type Listener = () => void;

interface Entry {
  state: QueryState<unknown>;
  inflight: Promise<unknown> | null;
  listeners: Set<Listener>;
  generation: number;
}

export function serializeKey(key: QueryKey): string {
  return typeof key === 'string' ? key : JSON.stringify(key);
}

export function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  if (typeof value === 'string') return new Error(value);
  return new Error('Unexpected error');
}

const IDLE: QueryState<never> = Object.freeze({
  status: 'idle', data: undefined, error: null, updatedAt: 0, fetching: false,
}) as QueryState<never>;

export class QueryCache {
  private entries = new Map<string, Entry>();
  constructor(private now: () => number = () => Date.now(), private maxEntries = 200) {}

  private entry(id: string): Entry {
    let e = this.entries.get(id);
    if (!e) {
      e = { state: IDLE, inflight: null, listeners: new Set(), generation: 0 };
      this.entries.set(id, e);
      this.evict();
    }
    return e;
  }

  private evict() {
    if (this.entries.size <= this.maxEntries) return;
    for (const [id, e] of this.entries) {
      if (this.entries.size <= this.maxEntries) break;
      if (e.listeners.size === 0 && !e.inflight) this.entries.delete(id);
    }
  }

  private set(e: Entry, next: QueryState<unknown>) {
    e.state = next;
    e.listeners.forEach(l => { try { l(); } catch {} });
  }

  get<T>(key: QueryKey): QueryState<T> {
    return (this.entries.get(serializeKey(key))?.state ?? IDLE) as QueryState<T>;
  }

  isStale(key: QueryKey, staleTimeMs: number): boolean {
    const s = this.get(key);
    if (s.status !== 'success' || s.updatedAt === 0) return true;
    return this.now() - s.updatedAt >= staleTimeMs;
  }

  subscribe(key: QueryKey, listener: Listener): () => void {
    const e = this.entry(serializeKey(key));
    e.listeners.add(listener);
    return () => { e.listeners.delete(listener); };
  }

  /** Run `fetcher` unless fresh data exists; concurrent callers share one request. */
  fetch<T>(key: QueryKey, fetcher: () => Promise<T>, opts: { staleTimeMs?: number; force?: boolean } = {}): Promise<T> {
    const id = serializeKey(key);
    const e = this.entry(id);
    if (e.inflight) return e.inflight as Promise<T>;
    if (!opts.force && !this.isStale(key, opts.staleTimeMs ?? 0)) return Promise.resolve(e.state.data as T);
    const generation = e.generation;
    const prev = e.state;
    this.set(e, { ...prev, status: prev.status === 'success' ? 'success' : 'loading', fetching: true, error: prev.status === 'success' ? null : prev.error });
    let p: Promise<T>;
    try { p = Promise.resolve(fetcher()); } catch (err) { p = Promise.reject(err); }
    const run = p.then(
      data => {
        if (e.generation === generation) this.set(e, { status: 'success', data, error: null, updatedAt: this.now(), fetching: false });
        return data;
      },
      err => {
        const error = toError(err);
        if (e.generation === generation) this.set(e, { status: 'error', data: e.state.data, error, updatedAt: e.state.updatedAt, fetching: false });
        throw error;
      },
    ).finally(() => { if (e.inflight === run) e.inflight = null; });
    e.inflight = run;
    return run;
  }

  setData<T>(key: QueryKey, data: T) {
    const e = this.entry(serializeKey(key));
    e.generation += 1;
    e.inflight = null;
    this.set(e, { status: 'success', data, error: null, updatedAt: this.now(), fetching: false });
  }

  /** Mark matching entries stale (prefix match on serialized string keys or array heads). */
  invalidate(prefix?: QueryKey) {
    const p = prefix === undefined ? null : serializeKey(prefix);
    const arrayPrefix = p && p.startsWith('[') ? p.slice(0, -1) : null;
    for (const [id, e] of this.entries) {
      if (p && !(id === p || id.startsWith(p) || (arrayPrefix && id.startsWith(arrayPrefix)))) continue;
      e.generation += 1;
      e.inflight = null;
      if (e.state.status === 'success') this.set(e, { ...e.state, updatedAt: 0 });
    }
  }

  clear() {
    for (const e of this.entries.values()) { e.generation += 1; e.inflight = null; this.set(e, IDLE); }
  }

  size(): number { return this.entries.size; }
}

/** Uniform view-state derived from a query (drives loading/error/empty UI). */
export type ViewState = 'loading' | 'error' | 'empty' | 'ready';

export function viewStateOf<T>(state: QueryState<T>, isEmpty: (data: T) => boolean = defaultIsEmpty): ViewState {
  if (state.status === 'success' && state.data !== undefined) return isEmpty(state.data) ? 'empty' : 'ready';
  if (state.status === 'error') return state.data !== undefined && !isEmpty(state.data) ? 'ready' : 'error';
  return 'loading';
}

export function defaultIsEmpty(data: unknown): boolean {
  if (data === null || data === undefined) return true;
  if (Array.isArray(data)) return data.length === 0;
  if (typeof data === 'object') {
    const items = (data as { items?: unknown }).items;
    if (Array.isArray(items)) return items.length === 0;
  }
  return false;
}

export const appQueryCache = new QueryCache();
