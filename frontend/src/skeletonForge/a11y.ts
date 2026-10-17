/**
 * Keyboard and assistive-tech helpers for the Skeleton forge surfaces.
 *
 * - `gridMove` implements the WAI-ARIA grid/listbox key model (arrows,
 *   Home/End, Ctrl+Home/End, PageUp/PageDown) as a pure function so the
 *   roving-focus behaviour is unit tested without a DOM.
 * - `keyAction` maps activation/dismiss keys to intents.
 * - `webKeyProps` attaches `onKeyDown` only on web: react-native-web
 *   forwards it to the DOM, native platforms ignore the prop, and core RN
 *   typings do not declare it, so it is applied through a typed spread.
 * - `useRovingIndex` owns the active index for a list/grid and clamps it
 *   when the item count changes (filtering, reloading).
 * - `countAnnouncement` builds polite live-region copy for result counts.
 */
import React from 'react';
import { Platform } from 'react-native';

export type NavKey =
  | 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight'
  | 'Home' | 'End' | 'PageUp' | 'PageDown';

const NAV_KEYS = new Set<string>(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown']);

export function isNavKey(key: string): key is NavKey {
  return NAV_KEYS.has(key);
}

export interface GridMoveOptions {
  /** Columns in the visual grid (1 = vertical list). */
  cols: number;
  count: number;
  /** Ctrl/Cmd held: Home/End jump to the first/last item instead of the row edge. */
  ctrl?: boolean;
  /** Rows moved by PageUp/PageDown. */
  pageRows?: number;
  /** Wrap from last to first on ArrowRight/ArrowDown (lists only). */
  wrap?: boolean;
}

/**
 * Next active index for a key press, or `null` when the key is not a
 * navigation key or there is nothing to navigate. Never returns an
 * out-of-range index.
 */
export function gridMove(index: number, key: string, { cols, count, ctrl = false, pageRows = 3, wrap = false }: GridMoveOptions): number | null {
  if (!isNavKey(key) || count <= 0) return null;
  const c = Math.max(1, Math.floor(cols) || 1);
  const last = count - 1;
  const i = Math.min(Math.max(0, Number.isFinite(index) ? Math.floor(index) : 0), last);
  const rowStart = i - (i % c);
  const clamp = (n: number) => Math.min(Math.max(0, n), last);
  switch (key) {
    case 'ArrowRight':
      return wrap && i === last ? 0 : clamp(i + 1);
    case 'ArrowLeft':
      return wrap && i === 0 ? last : clamp(i - 1);
    case 'ArrowDown':
      if (i + c > last) return wrap && c === 1 ? 0 : i;
      return i + c;
    case 'ArrowUp':
      if (i - c < 0) return wrap && c === 1 ? last : i;
      return i - c;
    case 'Home':
      return ctrl || c === 1 ? 0 : rowStart;
    case 'End':
      return ctrl || c === 1 ? last : Math.min(rowStart + c - 1, last);
    case 'PageDown':
      return clamp(i + c * Math.max(1, pageRows));
    case 'PageUp':
      return clamp(i - c * Math.max(1, pageRows));
    default:
      return null;
  }
}

export type KeyIntent = 'activate' | 'dismiss' | null;

/** Enter/Space activate, Escape dismisses. */
export function keyAction(key: string): KeyIntent {
  if (key === 'Enter' || key === ' ' || key === 'Spacebar') return 'activate';
  if (key === 'Escape' || key === 'Esc') return 'dismiss';
  return null;
}

export interface KeyEventLike {
  key?: string;
  nativeEvent?: { key?: string; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
  preventDefault?: () => void;
}

/** Normalise web keyboard events (DOM or RN-synthetic) to key + modifiers. */
export function readKey(e: KeyEventLike): { key: string; ctrl: boolean; shift: boolean } {
  const key = String(e?.key ?? e?.nativeEvent?.key ?? '');
  const ctrl = Boolean(e?.ctrlKey || e?.metaKey || e?.nativeEvent?.ctrlKey || e?.nativeEvent?.metaKey);
  const shift = Boolean(e?.shiftKey || e?.nativeEvent?.shiftKey);
  return { key, ctrl, shift };
}

/**
 * `{ onKeyDown }` on web, `{}` elsewhere. Spread onto a View/Pressable/
 * TextInput: `<View {...webKeyProps(handler)} />`.
 */
export function webKeyProps(handler: ((e: KeyEventLike) => void) | undefined, os: string = Platform.OS): Record<string, unknown> {
  return os === 'web' && handler ? { onKeyDown: handler } : {};
}

/** Roving tab stop: only the active item is in the tab order. */
export function rovingTabIndex(i: number, active: number): 0 | -1 {
  return i === active ? 0 : -1;
}

/**
 * `{ tabIndex }` on web only. Core RN views do not take a DOM tab index;
 * native focus order stays with the platform.
 */
export function tabIndexProp(index: 0 | -1 | undefined, os: string = Platform.OS): Record<string, unknown> {
  return os === 'web' && index !== undefined ? { tabIndex: index } : {};
}

/** Active index for a roving-focus collection, clamped to `count`. */
export function useRovingIndex(count: number, initial = 0): [number, (i: number) => void] {
  const [active, setActive] = React.useState(initial);
  const clamped = count <= 0 ? 0 : Math.min(Math.max(0, active), count - 1);
  React.useEffect(() => {
    if (clamped !== active) setActive(clamped);
  }, [clamped, active]);
  return [clamped, setActive];
}

/** Polite live-region copy, e.g. "3 of 12 eras shown". */
export function countAnnouncement(shown: number, total: number, noun: string, query = ''): string {
  const plural = (n: number) => (n === 1 ? noun : `${noun}s`);
  if (!total) return `No ${plural(0)} available.`;
  const q = query.trim();
  if (!shown) return `No ${plural(0)} match “${q}”.`;
  if (shown === total) return `${total} ${plural(total)} shown.`;
  return `${shown} of ${total} ${plural(total)} shown${q ? ` for “${q}”` : ''}.`;
}
