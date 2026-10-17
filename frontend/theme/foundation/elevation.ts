/**
 * Foundation elevation — UI_ART_KIT §2.4.
 * Dark (OLED): separation from surface tint + border first, shadow second.
 * Light: tokens.ts drop shadows.
 */
import type { ViewStyle } from 'react-native';
import { elevation, hud } from '../tokens';
import type { ColorMode, ColorRoles } from './color';

export const shadows = elevation;
export type ShadowKey = keyof typeof elevation;

export type ElevationLevel = 'flat' | 'card' | 'raised' | 'selected' | 'sheet' | 'modal';
export const ELEVATION_LEVELS: readonly ElevationLevel[] = ['flat', 'card', 'raised', 'selected', 'sheet', 'modal'];

export type Surface = {
  backgroundColor: string;
  borderColor: string;
  borderWidth: number;
  shadow: ViewStyle;
  /** Scrim colour drawn behind the surface (modal only), else null. */
  scrim: string | null;
};

/** Resolve the §2.4 elevation ladder for a mode and colour set. */
export function surfaces(mode: ColorMode, c: ColorRoles): Readonly<Record<ElevationLevel, Surface>> {
  if (mode === 'dark') {
    return {
      flat: { backgroundColor: c.bg, borderColor: c.border, borderWidth: 0, shadow: shadows.none, scrim: null },
      card: { backgroundColor: c.bgElevated, borderColor: c.border, borderWidth: 1, shadow: shadows.none, scrim: null },
      raised: { backgroundColor: c.surfaceAlt, borderColor: c.borderStrong, borderWidth: 1, shadow: shadows.none, scrim: null },
      selected: { backgroundColor: c.surfaceAlt, borderColor: c.borderFocus, borderWidth: 1, shadow: shadows.none, scrim: null },
      sheet: { backgroundColor: c.bgSubtle, borderColor: c.border, borderWidth: 1, shadow: shadows.md, scrim: null },
      modal: { backgroundColor: c.bgElevated, borderColor: c.borderStrong, borderWidth: 1, shadow: shadows.lg, scrim: c.overlay },
    };
  }
  return {
    flat: { backgroundColor: c.bg, borderColor: c.border, borderWidth: 0, shadow: shadows.none, scrim: null },
    card: { backgroundColor: c.bgElevated, borderColor: c.border, borderWidth: 0, shadow: shadows.xs, scrim: null },
    raised: { backgroundColor: c.bgElevated, borderColor: c.border, borderWidth: 0, shadow: shadows.sm, scrim: null },
    selected: { backgroundColor: c.bgElevated, borderColor: c.borderFocus, borderWidth: 1, shadow: shadows.sm, scrim: null },
    sheet: { backgroundColor: c.bgElevated, borderColor: c.border, borderWidth: 0, shadow: shadows.md, scrim: null },
    modal: { backgroundColor: c.bgElevated, borderColor: c.border, borderWidth: 0, shadow: shadows.lg, scrim: c.overlay },
  };
}

/** UI_ART_KIT §2.4 / §3.2: at most one `glow` element per screen. */
export const GLOW_MAX_PER_SCREEN = hud.glowMaxPerScreen;
