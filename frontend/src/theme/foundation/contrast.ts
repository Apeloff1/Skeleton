/**
 * WCAG 2.x contrast helpers for the foundation kit.
 *
 * Formula as stated in docs/UI_ART_KIT.md (header + §2.5): sRGB relative
 * luminance, ratio = (L1 + 0.05) / (L2 + 0.05). Only opaque #RRGGBB values
 * are accepted; translucent surfaces must be composited before measuring.
 */

/** WCAG AA thresholds (UI_ART_KIT §2.5). */
export const WCAG = {
  /** Normal body text. */
  aaText: 4.5,
  /** Large text (>= 24 px, or >= 18.66 px bold) and UI glyphs / icons (WCAG 1.4.11). */
  aaLarge: 3,
  aaa: 7,
} as const;

function channel(part: string): number {
  const v = Number.parseInt(part, 16) / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

/** Relative luminance of an opaque #RRGGBB colour. */
export function relativeLuminance(hex: string): number {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`foundation contrast: expected opaque #RRGGBB, got ${hex}`);
  return 0.2126 * channel(match[1]) + 0.7152 * channel(match[2]) + 0.0722 * channel(match[3]);
}

/** Contrast ratio between two opaque colours (order-independent). */
export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
