/** Forge cockpit compatibility colors from the canonical design-token module. */
import type { Tone } from '../run';
import design, { breathing, radii } from '../../theme/tokens';

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

export const TONE_GLYPH: Record<Tone, string> = {
  ok: '✓', warn: '!', bad: '✕', idle: '○',
};

/** Shared touch and radius rules for cockpit controls. */
export const TOUCH = breathing.minTouch;
export const RADIUS = radii.md;
