/**
 * utils/quickWins.ts — A grab-bag of tiny utilities introduced as part of
 * the Feb 2026 "42 fast wins" pass. Each helper is small, dependency-free,
 * and self-contained so it can be imported a la carte without dragging
 * any heavy modules into a hot path.
 */

import { Platform } from 'react-native';

// ─── ① clamp ─────────────────────────────────────────────────────────────
/** Clamp a number to [min, max]. NaN-safe → returns `min`. */
export function clamp(n: number, min: number, max: number): number {
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

// ─── ② safeDivide ────────────────────────────────────────────────────────
/** Division that returns `fallback` instead of Infinity / NaN. */
export function safeDivide(num: number, den: number, fallback = 0): number {
  if (!Number.isFinite(num) || !Number.isFinite(den) || den === 0) return fallback;
  return num / den;
}

// ─── ③ formatBytes ───────────────────────────────────────────────────────
/** Human-readable bytes: 1234 → "1.21 KB". */
export function formatBytes(n: number, dp = 2): string {
  if (!Number.isFinite(n) || n < 0) return '?';
  if (n === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const k = 1024;
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(k)));
  return `${(n / Math.pow(k, i)).toFixed(dp)} ${units[i]}`;
}

// ─── ④ formatDuration ────────────────────────────────────────────────────
/** Human-readable ms duration: 95000 → "1m 35s". */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '?';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  if (m < 60) return remS ? `${m}m ${remS}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM ? `${h}h ${remM}m` : `${h}h`;
}

// ─── ⑤ debounce ──────────────────────────────────────────────────────────
/** Cancellable debounce. Returns the wrapper + a `.cancel()` method. */
export function debounce<T extends (...args: any[]) => any>(fn: T, waitMs: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const wrapped = (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(...args); }, waitMs);
  };
  (wrapped as any).cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  return wrapped as T & { cancel: () => void };
}

// ─── ⑥ throttle ──────────────────────────────────────────────────────────
/** Leading-edge throttle — fires immediately, then ignores for `waitMs`. */
export function throttle<T extends (...args: any[]) => any>(fn: T, waitMs: number): T {
  let last = 0;
  return ((...args: any[]) => {
    const now = Date.now();
    if (now - last >= waitMs) { last = now; return fn(...args); }
  }) as T;
}

// ─── ⑦ chunk ─────────────────────────────────────────────────────────────
/** Split an array into fixed-size chunks. */
export function chunk<T>(arr: readonly T[], size: number): T[][] {
  if (size <= 0) return [];
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

// ─── ⑧ pick / omit ───────────────────────────────────────────────────────
/** Type-safe pick — returns a shallow copy with only the named keys. */
export function pick<T extends Record<string, any>, K extends keyof T>(obj: T, keys: readonly K[]): Pick<T, K> {
  const out = {} as Pick<T, K>;
  for (const k of keys) if (k in obj) (out as any)[k] = obj[k];
  return out;
}

/** Type-safe omit — returns a shallow copy without the named keys. */
export function omit<T extends Record<string, any>, K extends keyof T>(obj: T, keys: readonly K[]): Omit<T, K> {
  const set = new Set(keys as readonly (keyof T)[]);
  const out = {} as any;
  for (const k of Object.keys(obj)) if (!set.has(k as keyof T)) out[k] = obj[k];
  return out as Omit<T, K>;
}

// ─── ⑨ deepEqual (cheap) ─────────────────────────────────────────────────
/** Shallow-of-shallow deep equality good enough for memo guards (no cycles). */
export function deepEqual(a: any, b: any): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object' || a == null || b == null) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) if (!Object.is(a[k], b[k])) return false;
  return true;
}

// ─── ⑩ once ──────────────────────────────────────────────────────────────
/** Like Lodash once — returns the first call's result on every invocation. */
export function once<T extends (...args: any[]) => any>(fn: T): T {
  let called = false;
  let result: any;
  return ((...args: any[]) => {
    if (!called) { called = true; result = fn(...args); }
    return result;
  }) as T;
}

// ─── ⑪ sleep ─────────────────────────────────────────────────────────────
/** Promise-based delay. Optionally aborts via AbortSignal. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('aborted'));
    const t = setTimeout(() => resolve(), ms);
    signal?.addEventListener?.('abort', () => { clearTimeout(t); reject(new Error('aborted')); });
  });
}

// ─── ⑫ isWeb / isIOS / isAndroid ─────────────────────────────────────────
export const isWeb = Platform.OS === 'web';
export const isIOS = Platform.OS === 'ios';
export const isAndroid = Platform.OS === 'android';
export const isNative = !isWeb;

// ─── ⑬ shortenId ─────────────────────────────────────────────────────────
/** "abc12345-def6-7890-1234-56789abc" → "abc12345…56789abc" for log readability. */
export function shortenId(id: string | undefined | null, head = 6, tail = 4, sep = '…'): string {
  if (!id) return '';
  if (id.length <= head + tail + sep.length) return id;
  return `${id.slice(0, head)}${sep}${id.slice(-tail)}`;
}

// ─── ⑭ randomId ──────────────────────────────────────────────────────────
/** Crypto-strong-ish 11-char id. Falls back to Math.random where crypto is unavailable. */
export function randomId(prefix = ''): string {
  let id = '';
  try {
    // @ts-ignore — RN has crypto.getRandomValues
    const c = (globalThis as any).crypto;
    if (c?.getRandomValues) {
      const arr = new Uint8Array(8);
      c.getRandomValues(arr);
      id = Array.from(arr).map((b) => b.toString(36)).join('').slice(0, 11);
    }
  } catch { /* swallow */ }
  if (!id) id = Math.random().toString(36).slice(2, 13);
  return prefix ? `${prefix}_${id}` : id;
}

// ─── ⑮ tryOr ─────────────────────────────────────────────────────────────
/** Run a possibly-throwing fn, return its value or `fallback` on throw. */
export function tryOr<T>(fn: () => T, fallback: T): T {
  try { return fn(); } catch { return fallback; }
}
