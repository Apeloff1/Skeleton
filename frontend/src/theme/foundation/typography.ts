/**
 * Foundation typography — full type scale from tokens.ts (UI_ART_KIT §2.2),
 * including the HUD `metric` / `label` roles, plus HUD tier mapping (§3.2–3.3).
 */
import type { TextStyle } from 'react-native';
import tokens, { hud } from '../tokens';

const { typography: tokenTypography } = tokens;

export const fontFamily = tokenTypography.fontFamily;

export type TypeRole =
  | 'display' | 'h1' | 'h2' | 'h3' | 'h4'
  | 'bodyLg' | 'body' | 'caption' | 'micro'
  | 'metric' | 'label'
  | 'mono' | 'monoSm'
  | 'buttonLg' | 'button' | 'buttonSm';

export const TYPE_ROLES: readonly TypeRole[] = [
  'display', 'h1', 'h2', 'h3', 'h4',
  'bodyLg', 'body', 'caption', 'micro',
  'metric', 'label',
  'mono', 'monoSm',
  'buttonLg', 'button', 'buttonSm',
];

/** Type scale (values are the tokens.ts objects). */
export const typeScale: Readonly<Record<TypeRole, TextStyle>> = {
  display: tokenTypography.display,
  h1: tokenTypography.h1,
  h2: tokenTypography.h2,
  h3: tokenTypography.h3,
  h4: tokenTypography.h4,
  bodyLg: tokenTypography.bodyLg,
  body: tokenTypography.body,
  caption: tokenTypography.caption,
  micro: tokenTypography.micro,
  metric: tokenTypography.metric,
  label: tokenTypography.label,
  mono: tokenTypography.mono,
  monoSm: tokenTypography.monoSm,
  buttonLg: tokenTypography.buttonLg,
  button: tokenTypography.button,
  buttonSm: tokenTypography.buttonSm,
};

/**
 * HUD tiers — UI_ART_KIT §3.2: critical = metric, contextual = h4/label,
 * ambient = caption. §3.3: HUD text read while moving is >= 14 px (`body`);
 * `micro` is forbidden in HUD.
 */
export const hudType = {
  critical: tokenTypography.metric,
  contextualTitle: tokenTypography.h4,
  contextualLabel: tokenTypography.label,
  ambient: tokenTypography.caption,
  minMovingTextSize: hud.minMovingTextSize,
  forbidden: ['micro'] as readonly TypeRole[],
} as const;

/** UI_ART_KIT §2.5: >= 24 px, or >= 18.66 px bold, counts as large text. */
export const LARGE_TEXT = { minSize: 24, minBoldSize: 18.66 } as const;
