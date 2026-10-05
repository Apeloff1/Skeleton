/**
 * utils/quickWins2.ts — 42 additional dependency-free utilities (Feb 2026).
 *
 * Companion to `utils/quickWins.ts` (15 helpers shipped earlier). Together
 * they cover the lion's share of micro-optimisations every screen ends up
 * writing inline. Each helper is small, side-effect-free, and explicitly
 * NaN/null/undefined-safe so adopting them never trades correctness for
 * convenience.
 *
 * Categories:
 *   • Strings  (1-7)     • Numbers   (8-14)
 *   • Arrays   (15-21)   • Objects   (22-28)
 *   • Async    (29-35)   • Misc      (36-42)
 */

// ═══ STRINGS ═════════════════════════════════════════════════════════════

/** ① Capitalize first letter, leave the rest untouched. */
export function capitalize(s: string): string {
  return !s ? '' : s.charAt(0).toUpperCase() + s.slice(1);
}

/** ② Title-case every space-separated word. */
export function titleCase(s: string): string {
  return !s ? '' : s.split(/\s+/).map(capitalize).join(' ');
}

/** ③ Truncate with ellipsis at a max length (default 80). */
export function truncate(s: string, max = 80, ellipsis = '…'): string {
  if (!s) return '';
  return s.length <= max ? s : s.slice(0, max - ellipsis.length) + ellipsis;
}

/** ④ Truncate at a word boundary. */
export function truncateWords(s: string, max = 80, ellipsis = '…'): string {
  if (!s || s.length <= max) return s ?? '';
  const cut = s.slice(0, max - ellipsis.length);
  const lastSpace = cut.lastIndexOf(' ');
  return (lastSpace > max * 0.5 ? cut.slice(0, lastSpace) : cut) + ellipsis;
}

/** ⑤ Strip HTML tags safely (no regex catastrophic backtracking). */
export function stripHtml(s: string): string {
  if (!s) return '';
  return s.replace(/<[^>]*>/g, '');
}

/** ⑥ Slugify for URL-safe ids. */
export function slugify(s: string): string {
  return (s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

/** ⑦ Bytes-aware string length (UTF-8). */
export function byteLength(s: string): number {
  if (!s) return 0;
  // @ts-ignore — RN has TextEncoder on Hermes ≥ 0.71
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(s).length;
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0xD800 || c >= 0xE000 ? 3 : (i++, 4);
  }
  return n;
}

// ═══ NUMBERS ═════════════════════════════════════════════════════════════

/** ⑧ Sum of an array of numbers, NaN-safe. */
export function sum(arr: readonly number[]): number {
  let total = 0;
  for (const v of arr) if (Number.isFinite(v)) total += v;
  return total;
}

/** ⑨ Mean (average), NaN-safe. */
export function mean(arr: readonly number[]): number {
  return arr.length ? sum(arr) / arr.length : 0;
}

/** ⑩ Median (sorts a copy). */
export function median(arr: readonly number[]): number {
  if (!arr.length) return 0;
  const sorted = [...arr].filter(Number.isFinite).sort((a, b) => a - b);
  const m = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
}

/** ⑪ Percentile (0-100). */
export function percentile(arr: readonly number[], p: number): number {
  if (!arr.length) return 0;
  const sorted = [...arr].filter(Number.isFinite).sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length)));
  return sorted[idx];
}

/** ⑫ Format as percentage string (0.123 → "12.3%"). */
export function formatPercent(n: number, dp = 1): string {
  if (!Number.isFinite(n)) return '—';
  return `${(n * 100).toFixed(dp)}%`;
}

/** ⑬ Format with thousand separators ("1,234,567"). */
export function formatNumber(n: number, dp = 0): string {
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: dp, minimumFractionDigits: dp });
}

/** ⑭ Linear interpolation. */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}

// ═══ ARRAYS ══════════════════════════════════════════════════════════════

/** ⑮ Remove duplicates (Set-based, preserves first occurrence order). */
export function unique<T>(arr: readonly T[]): T[] {
  return Array.from(new Set(arr));
}

/** ⑯ Group by a key function. */
export function groupBy<T, K extends string | number>(arr: readonly T[], key: (item: T) => K): Record<K, T[]> {
  const out = {} as Record<K, T[]>;
  for (const item of arr) {
    const k = key(item);
    (out[k] = out[k] || []).push(item);
  }
  return out;
}

/** ⑰ Partition into [matches, rest] by predicate. */
export function partition<T>(arr: readonly T[], pred: (item: T) => boolean): [T[], T[]] {
  const yes: T[] = [], no: T[] = [];
  for (const item of arr) (pred(item) ? yes : no).push(item);
  return [yes, no];
}

/** ⑱ Range generator: [0..n) or [a..b). */
export function range(start: number, end?: number, step = 1): number[] {
  const lo = end === undefined ? 0 : start;
  const hi = end === undefined ? start : end;
  const out: number[] = [];
  if (step === 0) return out;
  for (let i = lo; step > 0 ? i < hi : i > hi; i += step) out.push(i);
  return out;
}

/** ⑲ Last element (safer than `arr[arr.length-1]` when arr is empty). */
export function last<T>(arr: readonly T[]): T | undefined {
  return arr.length ? arr[arr.length - 1] : undefined;
}

/** ⑳ Move element from `from` index to `to` index (returns new array). */
export function moveItem<T>(arr: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= arr.length) return arr.slice();
  const copy = arr.slice();
  const [item] = copy.splice(from, 1);
  copy.splice(Math.max(0, Math.min(copy.length, to)), 0, item);
  return copy;
}

/** ㉑ Shuffle (Fisher-Yates, returns new array). */
export function shuffle<T>(arr: readonly T[]): T[] {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

// ═══ OBJECTS ═════════════════════════════════════════════════════════════

/** ㉒ Map values of an object (key-preserving). */
export function mapValues<V, R>(obj: Record<string, V>, fn: (v: V, k: string) => R): Record<string, R> {
  const out: Record<string, R> = {};
  for (const k of Object.keys(obj)) out[k] = fn(obj[k], k);
  return out;
}

/** ㉓ Filter object entries by a predicate. */
export function filterObject<V>(obj: Record<string, V>, pred: (v: V, k: string) => boolean): Record<string, V> {
  const out: Record<string, V> = {};
  for (const k of Object.keys(obj)) if (pred(obj[k], k)) out[k] = obj[k];
  return out;
}

/** ㉔ Invert: {a:1,b:2} → {1:"a",2:"b"}. */
export function invert(obj: Record<string, string | number>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of Object.keys(obj)) out[String(obj[k])] = k;
  return out;
}

/** ㉕ Get a deeply-nested path safely ("a.b.c"). */
export function get(obj: any, path: string, fallback?: any): any {
  if (obj == null) return fallback;
  const parts = path.split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return fallback;
    cur = cur[p];
  }
  return cur === undefined ? fallback : cur;
}

/** ㉖ Set a deeply-nested path immutably. */
export function set(obj: any, path: string, value: any): any {
  const parts = path.split('.');
  const root: any = Array.isArray(obj) ? obj.slice() : { ...(obj || {}) };
  let cur = root;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    cur[key] = Array.isArray(cur[key]) ? cur[key].slice() : { ...(cur[key] || {}) };
    cur = cur[key];
  }
  cur[parts[parts.length - 1]] = value;
  return root;
}

/** ㉗ Is plain object (not array, not null, not class instance)? */
export function isPlainObject(v: any): v is Record<string, any> {
  if (v == null || typeof v !== 'object') return false;
  const proto = Object.getPrototypeOf(v);
  return proto === null || proto === Object.prototype;
}

/** ㉘ Recursive merge (right wins; arrays replace, not concat). */
export function deepMerge<T extends Record<string, any>>(...sources: Partial<T>[]): T {
  const out: any = {};
  for (const src of sources) {
    if (!isPlainObject(src)) continue;
    for (const k of Object.keys(src)) {
      const v = (src as any)[k];
      if (isPlainObject(v) && isPlainObject(out[k])) out[k] = deepMerge(out[k], v);
      else out[k] = v;
    }
  }
  return out as T;
}

// ═══ ASYNC ═══════════════════════════════════════════════════════════════

/** ㉙ Promise.all but bounded concurrency. */
export async function asyncPool<T, R>(items: readonly T[], concurrency: number, fn: (item: T, idx: number) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i], i);
    }
  }
  await Promise.all(range(0, Math.max(1, concurrency)).map(worker));
  return out;
}

/** ㉚ Timeout a promise — rejects with `Error("timeout")` after `ms`. */
export function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timeout after ${ms}ms`)), ms);
    p.then(v => { clearTimeout(t); resolve(v); }, e => { clearTimeout(t); reject(e); });
  });
}

/** ㉛ Race-first-resolved (Promise.any polyfill — RN doesn't always have it). */
export function any<T>(promises: readonly Promise<T>[]): Promise<T> {
  return new Promise((resolve, reject) => {
    let rejected = 0;
    const errors: any[] = new Array(promises.length);
    if (!promises.length) return reject(new Error('any() on empty input'));
    promises.forEach((p, i) => p.then(resolve, (e) => {
      errors[i] = e;
      if (++rejected === promises.length) reject(new AggregateError(errors, 'all rejected'));
    }));
  });
}

/** ㉜ Defer a microtask — useful to break long synchronous chains. */
export function defer(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0));
}

/** ㉝ Memoize an async function by JSON-stringifying its args. */
export function memoAsync<A extends any[], R>(fn: (...args: A) => Promise<R>, ttlMs = 60_000) {
  const cache = new Map<string, { v: Promise<R>; at: number }>();
  return (...args: A): Promise<R> => {
    const key = JSON.stringify(args);
    const hit = cache.get(key);
    if (hit && Date.now() - hit.at < ttlMs) return hit.v;
    const promise = fn(...args);
    cache.set(key, { v: promise, at: Date.now() });
    promise.catch(() => cache.delete(key));  // don't cache rejections
    return promise;
  };
}

/** ㉞ Retry an async fn with exponential back-off + jitter. */
export async function asyncRetry<T>(fn: () => Promise<T>, attempts = 3, baseMs = 200): Promise<T> {
  let lastErr: any;
  for (let i = 0; i < attempts; i++) {
    try { return await fn(); }
    catch (e) {
      lastErr = e;
      if (i === attempts - 1) break;
      const delay = baseMs * Math.pow(2, i) * (0.75 + Math.random() * 0.5);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw lastErr;
}

/** ㉟ Polling helper — calls `probe` until it returns truthy or `maxMs` elapses. */
export async function pollUntil<T>(probe: () => Promise<T | null | undefined>, opts: { intervalMs?: number; maxMs?: number } = {}): Promise<T | null> {
  const interval = opts.intervalMs ?? 500;
  const deadline = Date.now() + (opts.maxMs ?? 10_000);
  while (Date.now() < deadline) {
    const v = await probe();
    if (v) return v;
    await new Promise(r => setTimeout(r, interval));
  }
  return null;
}

// ═══ MISC ════════════════════════════════════════════════════════════════

/** ㊱ Stable JSON stringify (sorted keys) — useful for cache keys. */
export function stableStringify(value: any): string {
  if (value == null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
  const keys = Object.keys(value).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + stableStringify(value[k])).join(',') + '}';
}

/** ㊲ Hash a string into a 32-bit signed int (FNV-1a). */
export function hash32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h | 0;
}

/** ㊳ Color helper — pick a deterministic HSL from any string id. */
export function colorFromId(id: string, sat = 70, light = 50): string {
  const h = Math.abs(hash32(id || '')) % 360;
  return `hsl(${h}deg ${sat}% ${light}%)`;
}

/** ㊴ Initials extractor ("John Doe" → "JD"). */
export function initials(name: string, max = 2): string {
  if (!name) return '';
  return name.split(/\s+/).filter(Boolean).slice(0, max).map(p => p[0]?.toUpperCase() ?? '').join('');
}

/** ㊵ Coerce any unknown value into a safe number with fallback. */
export function toNumber(v: any, fallback = 0): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : fallback;
}

/** ㊶ Coerce any unknown value into a non-empty string with fallback. */
export function toString(v: any, fallback = ''): string {
  if (v == null) return fallback;
  if (typeof v === 'string') return v;
  try { return String(v); } catch { return fallback; }
}

/** ㊷ Compose two predicates with logical AND. */
export function and<T>(...preds: ((v: T) => boolean)[]): (v: T) => boolean {
  return (v: T) => preds.every(p => p(v));
}
