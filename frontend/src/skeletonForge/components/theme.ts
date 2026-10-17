/** Forge cockpit compatibility colors from the canonical design-token module. */
import type { Tone } from '../run';
import design, { status } from '../../../theme/tokens';

const { breathing, radii } = design;

export const C = {
  get bg() { return design.colors.bg; },
  get card() { return design.colors.bgElevated; },
  get cardAlt() { return design.colors.bgSubtle; },
  get border() { return design.colors.border; },
  get borderStrong() { return design.colors.borderStrong; },
  get text() { return design.colors.textMuted; },
  get textStrong() { return design.colors.text; },
  get mute() { return design.colors.textMuted; },
  get dim() { return design.colors.textDim; },
  get green() { return design.colors.success; },
  get blue() { return design.colors.info; },
  get amber() { return design.colors.warning; },
  get red() { return design.colors.danger; },
  get accent() { return design.colors.primaryHover; },
} as const;

export const TONE_COLOR: Record<Tone, string> = {
  get ok() { return C.green; },
  get warn() { return C.amber; },
  get bad() { return C.red; },
  get idle() { return C.dim; },
};

/** Glyph values live in tokens.ts `status.glyph` (single edit point). */
export const TONE_GLYPH: Record<Tone, string> = {
  ok: status.glyph.ok, warn: status.glyph.warn, bad: status.glyph.bad, idle: status.glyph.idle,
};

/** Shared touch and radius rules for cockpit controls. */
export const TOUCH = breathing.minTouch;
export const RADIUS = radii.md;
