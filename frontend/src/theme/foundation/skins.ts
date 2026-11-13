/**
 * Foundation skin adapter — exposes the 30 runtime skins (frontend/theme/skins.ts)
 * as resolved colour overrides, including per-skin `onPrimary`.
 *
 * onPrimary: UI_ART_KIT §2.6 (white vs ink900, whichever is higher) with the
 * Oct 16 2026 accessibility follow-up in UI_ART_KIT ("Migration implementation
 * checkpoint"): royal and lavender fall back to ink1000 (palette.ink[1000]) so every skin
 * meets 4.5:1. The values are computed by skins.ts `onPrimaryFor`; this
 * adapter only reads them — it never mutates the live palette (skinStore does).
 */
import { DEFAULT_SKIN, SKIN_BY_ID, SKINS, type Skin, type SkinColors } from '../skins';
import { contrastRatio, WCAG } from './contrast';

export { DEFAULT_SKIN };
export type { Skin, SkinColors };

export const SKIN_IDS: readonly string[] = SKINS.map((s) => s.id);

/** Skin-specific overrides, plus the foundation `primaryText` role. */
export type SkinOverrides = SkinColors & { primaryText: string };

/**
 * UI_ART_KIT §2.6, last paragraph: where skin `primary` as text on its own
 * `bg` is below 4.5:1, primary-coloured text uses `primaryHover`.
 */
export function skinPrimaryText(c: SkinColors): string {
  return contrastRatio(c.primary, c.bg) >= WCAG.aaText ? c.primary : c.primaryHover;
}

/** Per-skin onPrimary table (UI_ART_KIT §2.6). */
export const ON_PRIMARY_BY_SKIN: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(SKINS.map((s) => [s.id, s.colors.onPrimary])),
);

export function isSkinId(id: string | null | undefined): id is string {
  return typeof id === 'string' && Object.prototype.hasOwnProperty.call(SKIN_BY_ID, id);
}

/** Resolved overrides for a skin, or null for an unknown id. */
export function skinOverrides(id: string | null | undefined): Readonly<SkinOverrides> | null {
  if (!isSkinId(id)) return null;
  const c = SKIN_BY_ID[id].colors;
  return Object.freeze({ ...c, primaryText: skinPrimaryText(c) });
}
