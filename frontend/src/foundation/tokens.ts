/**
 * Semantic foundation tokens derived from the canonical palette in
 * theme/tokens.ts. Never introduce raw hex values here; alias the palette.
 */
import type { TextStyle } from 'react-native';
import theme from '../../theme/tokens';

// Canonical tokens expose theme-bound roles on the default object.
// Do not import these as named exports: the theme API intentionally removed them.
const { palette, spacing, radii, typography, breathing } = theme;

export const color = {
  bg: palette.ink[950],
  surface: palette.ink[900],
  surfaceRaised: palette.ink[850],
  border: palette.ink[700],
  text: palette.ink[50],
  textMuted: palette.ink[300],
  textSubtle: palette.ink[400],
  primary: palette.brand[600],
  primaryPressed: palette.brand[800],
  onPrimary: palette.ink[0],
  danger: palette.danger[400],
  success: palette.success[400],
  warning: palette.warning[400],
  focus: palette.brand[300],
} as const;

export type ColorToken = keyof typeof color;
export type SpaceToken = keyof typeof spacing;
export type TextVariant = 'display' | 'h1' | 'h2' | 'h3' | 'body' | 'bodyLg' | 'caption' | 'label' | 'mono';

export const textVariants: Record<TextVariant, TextStyle> = {
  display: typography.display,
  h1: typography.h1,
  h2: typography.h2,
  h3: typography.h3,
  body: typography.body,
  bodyLg: typography.bodyLg,
  caption: typography.caption,
  label: typography.label,
  mono: typography.mono,
};

/** Headings get the `header` accessibility role automatically. */
export function isHeadingVariant(v: TextVariant): boolean {
  return v === 'display' || v === 'h1' || v === 'h2' || v === 'h3';
}

export function space(token: SpaceToken | number): number {
  return typeof token === 'number' ? token : spacing[token];
}

export const minTouch = breathing.minTouch;
export const motion = theme.motion;
export { spacing, radii, palette };
