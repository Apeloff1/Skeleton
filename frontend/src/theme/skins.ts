/**
 * 🎨 APP SKINS — 30-skin large-scale reskinner. Default: "hyperwave".
 * Each skin overrides the live palette keys read across the app (theme.colors.*).
 * Applied at runtime by src/utils/skinStore.ts.
 *
 * Compatibility layer: skin palettes live in frontend/theme/tokens.ts
 * (`skinPalettes`, `DEFAULT_SKIN_ID`) — edit values there, not here. This file
 * keeps its original export names and shapes and only derives the computed
 * keys (bgSubtle, onPrimary, primarySoft, borderFocus).
 */
import tokens, { DEFAULT_SKIN_ID, skinPalettes } from './tokens';

const { palette } = tokens;

export type SkinColors = {
  bg: string; bgElevated: string; bgSubtle: string;
  primary: string; onPrimary: string; primaryHover: string; primarySoft: string; borderFocus: string;
  accentCyan: string; accentPink: string; accentGold: string;
};
export type Skin = { id: string; name: string; emoji: string; colors: SkinColors };

/** Convert an opaque six-digit primary color to a valid translucent surface. */
export function primaryTint(hex: string, alpha = 0.16): string {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error('skin primary must be an opaque #RRGGBB color');
  const channels = match.slice(1).map(part => Number.parseInt(part, 16));
  if (!Number.isFinite(alpha) || alpha < 0 || alpha > 1) throw new Error('invalid skin alpha');
  return `rgba(${channels[0]},${channels[1]},${channels[2]},${alpha})`;
}

function luminance(hex: string): number {
  const rgb = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!rgb) throw new Error('invalid skin contrast color');
  const channels = rgb.slice(1).map(part => {
    const v = Number.parseInt(part, 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

/** Choose the more readable of white and dark ink on the selected skin fill. */
export function onPrimaryFor(hex: string): string {
  const y = luminance(hex);
  const white = (1.05) / (y + 0.05);
  const ink = luminance(palette.ink[900]);
  const dark = (Math.max(y, ink) + 0.05) / (Math.min(y, ink) + 0.05);
  if (Math.max(white, dark) >= 4.5) return white >= dark ? palette.ink[0] : palette.ink[900];
  // Royal and lavender narrowly miss AA with either conventional ink. The
  // existing ink1000 token is darker: rescue these labels without recoloring
  // either skin's signature primary fill or changing its content hierarchy.
  return palette.ink[1000];
}

const mk = (
  id: string, name: string, emoji: string,
  bg: string, bg2: string, primary: string, hover: string,
  cyan: string, pink: string, gold: string,
): Skin => ({
  id, name, emoji,
  colors: {
    bg, bgElevated: bg2, bgSubtle: bg2,
    primary, onPrimary: onPrimaryFor(primary), primaryHover: hover,
    primarySoft: primaryTint(primary), borderFocus: primary,
    accentCyan: cyan, accentPink: pink, accentGold: gold,
  },
});

export const DEFAULT_SKIN = DEFAULT_SKIN_ID;

export const SKINS: Skin[] = skinPalettes.map(
  ([id, name, emoji, bg, bg2, primary, hover, cyan, pink, gold]) =>
    mk(id, name, emoji, bg, bg2, primary, hover, cyan, pink, gold),
);

export const SKIN_BY_ID: Record<string, Skin> = Object.fromEntries(SKINS.map((s) => [s.id, s]));
