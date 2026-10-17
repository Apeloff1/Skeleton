/**
 * Foundation colour: palette ramps + semantic roles for dark AND light.
 *
 * Read-only view over frontend/theme/tokens.ts — the single edit point for
 * token values. This module holds no colour literals.
 */
import tokens, { canonicalColors, status, textUsage } from '../tokens';

const { palette } = tokens;

export type ColorMode = 'dark' | 'light';

/** Palette ramps, re-exported from tokens.ts. */
export const ramps = {
  ink: palette.ink,
  brand: palette.brand,
  /**
   * UI_ART_KIT §1.3 #3 / §5 step 1: the ramp formerly misnamed `cyan` is blue.
   * Use `ramps.blue` for that hue; `ramps.cyan` is true cyan.
   */
  blue: palette.blue,
  cyan: palette.cyan,
  pink: palette.pink,
  success: palette.success,
  warning: palette.warning,
  danger: palette.danger,
  info: palette.info,
} as const;

/** UI_ART_KIT §2.1 `accentCyan` (fix): the only true cyan in the repo. */
export const TRUE_CYAN = palette.cyan[400];

/**
 * Alias for code that still means "the blue that used to be called cyan"
 * (tokens.ts gradients.cyan, many skins' accentCyan). UI_ART_KIT §1.3 #3.
 */
export const LEGACY_CYAN_BLUE = palette.blue;

type TokenRoleKey = keyof typeof canonicalColors.dark;

/** Semantic colour roles shared by both modes. */
export type ColorRoles = { [K in TokenRoleKey]: string } & {
  /**
   * Primary-coloured *text* on `bg`. UI_ART_KIT §2.6 (last paragraph): when
   * `primary` is below 4.5:1 on its own `bg`, use `primaryHover` for text.
   */
  primaryText: string;
};

function toRoles(source: { [K in TokenRoleKey]: string }): ColorRoles {
  const out = {} as ColorRoles;
  (Object.keys(source) as TokenRoleKey[]).forEach((key) => {
    out[key] = source[key];
  });
  // Canonical primaries pass 4.5:1 on bg in both modes (UI_ART_KIT §2.5).
  out.primaryText = source.primary;
  return out;
}

/** Canonical semantic roles per mode (tokens.ts canonicalColors; immune to skinStore). */
export const roles: Readonly<Record<ColorMode, Readonly<ColorRoles>>> = {
  dark: Object.freeze(toRoles(canonicalColors.dark)),
  light: Object.freeze(toRoles(canonicalColors.light)),
};

/** Status keys; the Forge cockpit `Tone` set plus `info`. */
export type StatusKey = keyof typeof status.glyph;
export type StatusShape = (typeof status.shape)[StatusKey];

export type StatusRole = {
  color: string;
  glyph: string;
  shape: StatusShape;
  /** Glyph/icon opacity. Idle is 50% (UI_ART_KIT §3.4). */
  opacity: number;
  /** Plain-language meaning, for a11y labels. */
  meaning: string;
};

/** HUD glyph pairing — tokens.ts `status.glyph` (UI_ART_KIT §3.4). */
export const STATUS_GLYPH: Readonly<Record<StatusKey, string>> = status.glyph;

const STATUS_KEYS: readonly StatusKey[] = ['ok', 'warn', 'bad', 'info', 'idle'];

/**
 * Build the semantic status roles for a resolved colour set.
 * `colorBlind` swaps success -> info and keeps glyphs (UI_ART_KIT §3.4,
 * UI_ART_HUD_SEMANTIC.md §2).
 */
export function statusRoles(c: ColorRoles, colorBlind = false): Readonly<Record<StatusKey, StatusRole>> {
  const color: Record<StatusKey, string> = {
    ok: colorBlind ? c.info : c.success,
    warn: c.warning,
    bad: c.danger,
    info: c.info,
    idle: c.textDim,
  };
  const out = {} as Record<StatusKey, StatusRole>;
  STATUS_KEYS.forEach((k) => {
    out[k] = { color: color[k], glyph: status.glyph[k], shape: status.shape[k], opacity: status.opacity[k], meaning: status.meaning[k] };
  });
  return out;
}

export type TextUsage = 'body' | 'large' | 'never';

/** Text-usage rules from tokens.ts `textUsage` (UI_ART_KIT §2.5). */
export const TEXT_USAGE: Readonly<Record<ColorMode, Readonly<Partial<Record<keyof ColorRoles, TextUsage>>>>> = textUsage;
