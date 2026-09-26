/**
 * Cockpit palette — matches the GameForge Studio console
 * (app/gameforge-studio.tsx: BG #0b1220, CARD #111827, GREEN/BLUE accents).
 */
import type { Tone } from '../run';

export const C = {
  bg: '#0b1220',
  card: '#111827',
  cardAlt: '#0f172a',
  border: '#1f2a44',
  borderStrong: '#334155',
  text: '#e5e7eb',
  textStrong: '#f8fafc',
  mute: '#94a3b8',
  dim: '#64748b',
  green: '#22c55e',
  blue: '#3b82f6',
  amber: '#f59e0b',
  red: '#ef4444',
  accent: '#a78bfa',
} as const;

export const TONE_COLOR: Record<Tone, string> = {
  ok: C.green,
  warn: C.amber,
  bad: C.red,
  idle: C.dim,
};

export const TONE_GLYPH: Record<Tone, string> = {
  ok: '✓',
  warn: '!',
  bad: '✕',
  idle: '○',
};

/** WCAG minimum touch target. */
export const TOUCH = 44;
export const RADIUS = 12;
