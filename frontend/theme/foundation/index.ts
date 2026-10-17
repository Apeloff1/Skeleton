/**
 * ═══════════════════════════════════════════════════════════════════════
 *  Foundation visual kit — typed design-token package for the app shell.
 * ═══════════════════════════════════════════════════════════════════════
 *
 *  Read-only layer over frontend/theme/tokens.ts — the ONLY place token values
 *  are edited — and frontend/theme/skins.ts (derived from tokens.ts). This
 *  package holds no colour literals.
 *  Specs: docs/UI_ART_KIT.md, docs/UI_ART_HUD_SEMANTIC.md,
 *  docs/UI_ART_ICONOGRAPHY.md. Consumer guide: docs/UI_ART_TOKENS.md.
 *
 *    import { getTheme, foundation } from '@/theme/foundation';
 *    const t = getTheme(isDark ? 'dark' : 'light', getActiveSkinId());
 *
 *  getTheme never mutates tokens.ts; results are frozen and memoised so the
 *  same (mode, skin, options) returns the same object reference.
 */
import type { TextStyle, ViewStyle } from 'react-native';
import tokens from '../tokens';
import {
  LEGACY_CYAN_BLUE, ramps, roles, STATUS_GLYPH, statusRoles, TEXT_USAGE, TRUE_CYAN,
  type ColorMode, type ColorRoles, type StatusKey, type StatusRole,
} from './color';
import { contrastRatio, relativeLuminance, WCAG } from './contrast';
import { ELEVATION_LEVELS, GLOW_MAX_PER_SCREEN, shadows, surfaces, type ElevationLevel, type Surface } from './elevation';
import { ICON_DOMAINS, ICON_GRID, ICON_SIZES, ICON_SPEC, ICON_STROKE_STYLE, iconName, isIconName } from './icons';
import { duration, easing, hudMotion } from './motion';
import { ICON_SQUARE_RADIUS, legacyRadius, radius } from './radius';
import { DEFAULT_SKIN, ON_PRIMARY_BY_SKIN, SKIN_IDS, isSkinId, skinOverrides } from './skins';
import { breathing, hitSlop, hudSafeZone, spacing, touch } from './spacing';
import { fontFamily, hudType, LARGE_TEXT, typeScale, TYPE_ROLES, type TypeRole } from './typography';

const { gradients } = tokens;

export * from './color';
export * from './contrast';
export * from './elevation';
export * from './icons';
export * from './motion';
export * from './radius';
export * from './skins';
export * from './spacing';
export * from './typography';

export type ThemeMode = ColorMode;

export type GetThemeOptions = {
  /** Swap success -> info for status roles, keep glyphs (UI_ART_KIT §3.4). */
  colorBlind?: boolean;
};

export type ResolvedTheme = {
  mode: ThemeMode;
  isDark: boolean;
  /** Skin actually applied (dark mode only), else null. */
  skinId: string | null;
  /** expo-status-bar style that reads on this mode's `bg`. */
  statusBarStyle: 'light' | 'dark';
  colors: Readonly<ColorRoles>;
  status: Readonly<Record<StatusKey, StatusRole>>;
  surfaces: Readonly<Record<ElevationLevel, Surface>>;
  gradients: typeof gradients;
  type: Readonly<Record<TypeRole, TextStyle>>;
  fontFamily: typeof fontFamily;
  hudType: typeof hudType;
  spacing: typeof spacing;
  breathing: typeof breathing;
  touch: typeof touch;
  hitSlop: typeof hitSlop;
  hudSafeZone: typeof hudSafeZone;
  radius: typeof radius;
  shadows: Readonly<Record<keyof typeof shadows, ViewStyle>>;
  motion: { duration: typeof duration; easing: typeof easing; hud: typeof hudMotion };
  icons: { grid: typeof ICON_GRID; sizes: typeof ICON_SIZES; spec: typeof ICON_SPEC; stroke: typeof ICON_STROKE_STYLE };
};

/** Static (mode-independent) foundation tokens. */
export const foundation = Object.freeze({
  ramps,
  roles,
  trueCyan: TRUE_CYAN,
  legacyCyanBlue: LEGACY_CYAN_BLUE,
  statusGlyph: STATUS_GLYPH,
  textUsage: TEXT_USAGE,
  wcag: WCAG,
  contrastRatio,
  relativeLuminance,
  type: typeScale,
  typeRoles: TYPE_ROLES,
  fontFamily,
  hudType,
  largeText: LARGE_TEXT,
  spacing,
  breathing,
  touch,
  hitSlop,
  hudSafeZone,
  radius,
  legacyRadius,
  iconSquareRadius: ICON_SQUARE_RADIUS,
  shadows,
  elevationLevels: ELEVATION_LEVELS,
  glowMaxPerScreen: GLOW_MAX_PER_SCREEN,
  motion: { duration, easing, hud: hudMotion },
  icons: { grid: ICON_GRID, sizes: ICON_SIZES, spec: ICON_SPEC, stroke: ICON_STROKE_STYLE, domains: ICON_DOMAINS, name: iconName, isName: isIconName },
  skins: { ids: SKIN_IDS, defaultId: DEFAULT_SKIN, onPrimary: ON_PRIMARY_BY_SKIN },
  gradients,
});

const cache = new Map<string, ResolvedTheme>();

/**
 * Fully resolved theme for the app shell.
 *
 * - `mode` picks the canonical dark or light role set (tokens.ts colors.*).
 * - `skinId` (dark only) layers that skin's overrides (theme/skins.ts) on top.
 *   Skins are dark palettes (near-black `bg`), so in light mode the skin is
 *   ignored and `skinId` resolves to null. Unknown ids also resolve to null.
 * - Omitting `skinId` returns the canonical kit (brand violet), not the
 *   runtime default skin; pass `getActiveSkinId()` to match skinStore.
 */
export function getTheme(mode: ThemeMode, skinId?: string | null, options: GetThemeOptions = {}): ResolvedTheme {
  if (mode !== 'dark' && mode !== 'light') throw new Error(`getTheme: unknown mode ${String(mode)}`);
  const applied = mode === 'dark' && isSkinId(skinId) ? skinId : null;
  const colorBlind = options.colorBlind === true;
  const key = `${mode}|${applied ?? ''}|${colorBlind ? 'cb' : ''}`;
  const hit = cache.get(key);
  if (hit) return hit;

  const overrides = applied ? skinOverrides(applied) : null;
  const colors: Readonly<ColorRoles> = Object.freeze({ ...roles[mode], ...(overrides ?? {}) });

  const resolved: ResolvedTheme = Object.freeze({
    mode,
    isDark: mode === 'dark',
    skinId: applied,
    statusBarStyle: mode === 'dark' ? 'light' : 'dark',
    colors,
    status: Object.freeze(statusRoles(colors, colorBlind)),
    surfaces: Object.freeze(surfaces(mode, colors)),
    gradients,
    type: typeScale,
    fontFamily,
    hudType,
    spacing,
    breathing,
    touch,
    hitSlop,
    hudSafeZone,
    radius,
    shadows,
    motion: { duration, easing, hud: hudMotion },
    icons: { grid: ICON_GRID, sizes: ICON_SIZES, spec: ICON_SPEC, stroke: ICON_STROKE_STYLE },
  });
  cache.set(key, resolved);
  return resolved;
}

