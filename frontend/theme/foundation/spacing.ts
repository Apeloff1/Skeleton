/**
 * Foundation spacing — 4-pt scale, layout rhythm, touch and HUD safe zones.
 * Values from tokens.ts (UI_ART_KIT §2.3) and UI_ART_KIT §3.1.
 */
import { breathing as tokenBreathing, hitSlop as tokenHitSlop, hud, spacing as tokenSpacing } from '../tokens';

export const spacing = tokenSpacing;
export type SpacingKey = keyof typeof tokenSpacing;

/** Layout rhythm (gutter 14 is intentionally off-grid; do not add more). */
export const breathing = tokenBreathing;

export const hitSlop = tokenHitSlop;

/** UI_ART_KIT §2.3: 44 pt minimum; 38 only together with hitSlop.sm. */
export const touch = {
  min: tokenBreathing.minTouch,
  minSm: tokenBreathing.minTouchSm,
  minSmHitSlop: tokenHitSlop.sm,
  /** §3.1 thumb zones: targets >= spacing.sm apart. */
  minGap: tokenSpacing.sm,
} as const;

/** HUD safe zones as fractions of the screen — UI_ART_KIT §3.1. */
export const hudSafeZone = {
  /** titleSafe 5% per edge; actionSafe 2.5% (frames only); thumbZone bottom 40%; centreClear 40% × 40%. */
  ...hud.safeZone,
  mobileGutter: tokenBreathing.gutter,
  safeBottomMin: tokenBreathing.safeBottomMin,
} as const;
