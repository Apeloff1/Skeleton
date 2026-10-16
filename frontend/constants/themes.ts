/** Compatibility roles sourced from the canonical design-token module.
 * No competing palette: useTheme reads the current skin for dark mode.
 */
import design, { colors as canonicalColors } from '../theme/tokens';
import { onPrimaryFor } from '../theme/skins';

export interface ThemeColors {
  background: string;
  surface: string;
  surfaceAlt: string;
  card: string;
  text: string;
  textSecondary: string;
  textMuted: string;
  primary: string;
  secondary: string;
  accent: string;
  success: string;
  warning: string;
  error: string;
  border: string;
  borderSubtle: string;
  codeBackground: string;
  lineNumbers: string;
  tutorial: string;
  tutorialGlow: string;
  gold: string;
  gradient: string[];
}


/** Legacy role adapters are constructed on access to reflect live skin changes. */
export function getThemeColors(mode: 'dark' | 'light'): ThemeColors {
  const c = mode === 'dark' ? design.colors : canonicalColors.light;
  return {
    background: c.bg,
    surface: c.bgElevated,
    surfaceAlt: c.bgSubtle,
    card: c.bgElevated,
    text: c.text,
    textSecondary: c.textMuted,
    textMuted: c.textMuted,
    primary: c.primary,
    secondary: c.primaryHover,
    accent: c.accentCyan,
    success: c.success,
    warning: c.warning,
    error: c.danger,
    border: c.borderStrong,
    borderSubtle: c.border,
    codeBackground: c.bgSubtle,
    lineNumbers: c.textDim,
    tutorial: c.primaryHover,
    tutorialGlow: c.primarySoft,
    gold: c.accentGold,
    gradient: [c.primary, c.primaryHover, c.accent],
  };
}

/** Getters keep older `themes.dark` imports compatible and current. */
export const themes = {
  get dark(): ThemeColors { return getThemeColors('dark'); },
  get light(): ThemeColors { return getThemeColors('light'); },
};

export const darkTheme: ThemeColors = new Proxy({} as ThemeColors, {
  get(_target, key: string) {
    return getThemeColors('dark')[key as keyof ThemeColors];
  },
  ownKeys() { return Object.keys(getThemeColors('dark')); },
  getOwnPropertyDescriptor() { return { enumerable: true, configurable: true }; },
});

export const lightTheme: ThemeColors = getThemeColors('light');
export type ThemeType = keyof typeof themes;
