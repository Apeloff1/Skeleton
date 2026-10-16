/** Deluxe role adapters — values originate in frontend/theme/tokens.ts.
 * Kept as named aliases so older Galaxy Studio components remain import-safe.
 */
import design, { spacing, radii, typography, elevation, palette } from '../../theme/tokens';

export const C = {
  get bg() { return design.colors.bg; },
  get surface() { return design.colors.bgElevated; },
  get surface2() { return design.colors.bgSubtle; },
  get surface3() { return design.colors.bgMuted; },
  get text() { return design.colors.text; },
  get textDim() { return design.colors.textMuted; },
  get textMute() { return design.colors.textMuted; },
  get brand() { return design.colors.primary; },
  get brand2() { return design.colors.primaryHover; },
  get brandDeep() { return palette.brand[900]; },
  get success() { return design.colors.success; },
  get warning() { return design.colors.warning; },
  get error() { return design.colors.danger; },
  get info() { return design.colors.info; },
  get gold() { return design.colors.accentGold; },
  get border() { return design.colors.border; },
  get borderStrong() { return design.colors.borderStrong; },
  get divider() { return design.colors.border; },
} as const;

export const S = {
  xs: spacing.xs, sm: spacing.sm, md: spacing.md,
  lg: spacing.base, xl: spacing.xl, xxl: spacing['2xl'],
  xxxl: spacing['4xl'],
} as const;
export const R = { sm: radii.xs, md: radii.md, lg: radii.xl, pill: radii.pill } as const;

export const T = {
  get display() { return { ...typography.display, color: C.text }; },
  get h1() { return { ...typography.h1, color: C.text }; },
  get h2() { return { ...typography.h2, color: C.text }; },
  get metric() { return { ...typography.metric, color: C.text }; },
  get label() { return { ...typography.label, color: C.textMute }; },
  get body() { return { ...typography.body, color: C.textDim }; },
  get small() { return { ...typography.caption, color: C.textMute }; },
} as const;

// Getter properties preserve the legacy exported object shape while reading
// the active skin at render time rather than freezing first-import colors.
export const card = {
  get backgroundColor() { return C.surface; },
  borderRadius: R.lg,
  borderWidth: 1,
  get borderColor() { return C.border; },
};

export const cardActive = {
  get backgroundColor() { return C.surface; },
  borderRadius: R.lg,
  borderWidth: 1,
  get borderColor() { return C.brand; },
};
export const glow = elevation.glow as object;

export default { C, S, R, T, card, cardActive, glow };
