/**
 * Deluxe design system — Tutolage / Galaxy Studio.
 * Glass / Luxe surfaces + Dark-First Utility typography. OLED-friendly #0A0A0A base,
 * amethyst (#8B5CF6) accent, border-highlight elevation (no heavy drop shadows).
 * Shared by the creation→compete→monetize→level-up flow.
 */
import { Platform } from 'react-native';

export const C = {
  bg: '#0A0A0A',
  surface: '#141414',
  surface2: '#1F1F1F',
  surface3: '#262626',
  text: '#E5E5E5',
  textDim: '#CCCCCC',
  textMute: '#A3A3A3',
  brand: '#8B5CF6',
  brand2: '#A78BFA',
  brandDeep: '#2E1B5B',
  success: '#10B981',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#3B82F6',
  gold: '#F5C451',
  border: '#262626',
  borderStrong: '#404040',
  divider: '#1F1F1F',
} as const;

export const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;
export const R = { sm: 6, md: 12, lg: 20, pill: 999 } as const;

// Tactical/display-leaning system font with letter-spacing to evoke Rajdhani.
const displayFont = Platform.select({ ios: 'System', android: 'sans-serif-condensed', default: 'System' });

export const T = {
  display: { fontFamily: displayFont, fontWeight: '800' as const, letterSpacing: 0.5, color: C.text },
  h1: { fontSize: 26, fontWeight: '800' as const, letterSpacing: 0.4, color: C.text },
  h2: { fontSize: 20, fontWeight: '800' as const, letterSpacing: 0.3, color: C.text },
  metric: { fontSize: 24, fontWeight: '800' as const, letterSpacing: 0.5, color: C.text },
  label: { fontSize: 12, fontWeight: '700' as const, letterSpacing: 1.1, textTransform: 'uppercase' as const, color: C.textMute },
  body: { fontSize: 14, color: C.textDim, lineHeight: 20 },
  small: { fontSize: 12, color: C.textMute },
};

/** Border-highlight elevation token (avoid heavy shadows on OLED). */
export const card = {
  backgroundColor: C.surface,
  borderRadius: R.lg,
  borderWidth: 1,
  borderColor: C.border,
};

export const cardActive = { ...card, borderColor: C.brand, borderWidth: 1 };

/** Subtle premium shadow for floating CTAs (kept light). */
export const glow = Platform.select({
  ios: { shadowColor: C.brand, shadowOpacity: 0.35, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
  android: { elevation: 8 },
  default: {},
}) as object;

export default { C, S, R, T, card, cardActive, glow };
