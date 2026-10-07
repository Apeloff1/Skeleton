/**
 * ═══════════════════════════════════════════════════════════════════════
 *  CodeDock Quantum Nexus — Design Tokens (2026 SOTA)
 * ═══════════════════════════════════════════════════════════════════════
 *
 *  Single source of truth for every visual property in the app.
 *  Heavily inspired by 2026-era references (Linear, Vercel, Apple Sport
 *  Pulse, Arc Search) — deep neutrals, vibrant accents, generous spacing,
 *  refined typography, soft glows.
 *
 *  Do not hardcode colors / sizes / radii anywhere else — always import
 *  from this file. Add new tokens here, then consume.
 * ═══════════════════════════════════════════════════════════════════════
 */
import { Platform, TextStyle, ViewStyle } from 'react-native';

// ─────────────────────────────────────────────────────────────────────
//  PALETTE — Aurora / Quantum / Cosmic — deep neutrals + vivid accents
// ─────────────────────────────────────────────────────────────────────
const palette = {
  // Neutrals (slate-derived, slightly warmer than pure-grey)
  ink: {
    0:   '#FFFFFF',
    50:  '#F8FAFC',
    100: '#E2E8F0',
    200: '#CBD5E1',
    300: '#94A3B8',
    400: '#64748B',
    500: '#475569',
    600: '#334155',
    700: '#1E293B',
    800: '#0F172A',
    900: '#0B1120',
    950: '#070B16',
    1000: '#04060D',
  },
  // Brand accent — quantum violet
  brand: {
    50:  '#F5F3FF',
    100: '#EDE9FE',
    200: '#DDD6FE',
    300: '#C4B5FD',
    400: '#A78BFA',
    500: '#8B5CF6',
    600: '#7C3AED',
    700: '#6D28D9',
    800: '#5B21B6',
    900: '#4C1D95',
  },
  // Secondary accent — electric cyan
  cyan: {
    400: '#3B82F6',
    500: '#2563EB',
    600: '#1D4ED8',
  },
  // Tertiary accent — neon pink
  pink: {
    400: '#F472B6',
    500: '#EC4899',
    600: '#DB2777',
  },
  // Semantic
  success: {
    400: '#34D399',
    500: '#10B981',
    600: '#059669',
  },
  warning: {
    400: '#FBBF24',
    500: '#F59E0B',
    600: '#D97706',
  },
  danger: {
    400: '#F87171',
    500: '#EF4444',
    600: '#DC2626',
  },
  info: {
    400: '#60A5FA',
    500: '#3B82F6',
    600: '#2563EB',
  },
} as const;

// ─────────────────────────────────────────────────────────────────────
//  SEMANTIC COLOR TOKENS — what every component should reference.
//  Light + Dark are both defined; the active theme picks one.
// ─────────────────────────────────────────────────────────────────────
const colors = {
  dark: {
    // ★ 2026-05 — Business-ready dark palette.
    // Shifted away from pure neon glassmorphism toward calmer charcoal
    // surfaces + slightly elevated borders. Result: feels closer to
    // Linear / Vercel / Stripe Dashboard than a consumer game app.
    // Backgrounds
    bg:           palette.ink[950],
    bgElevated:   palette.ink[900],
    bgSubtle:     palette.ink[850] ?? palette.ink[800],
    bgMuted:      palette.ink[700],
    // Surfaces (slightly heavier so cards feel solid, not floating glass)
    surface:      'rgba(255,255,255,0.045)',
    surfaceAlt:   'rgba(255,255,255,0.07)',
    surfaceHover: 'rgba(255,255,255,0.10)',
    // Borders (stronger so hierarchy reads at-a-glance on small screens)
    border:       'rgba(255,255,255,0.10)',
    borderStrong: 'rgba(255,255,255,0.18)',
    borderFocus:  palette.brand[400],
    // Text
    text:         palette.ink[50],
    textMuted:    palette.ink[300],
    textDim:      palette.ink[400],
    textDisabled: palette.ink[500],
    textInverse:  palette.ink[900],
    // Brand
    primary:      palette.brand[500],
    primaryHover: palette.brand[400],
    primarySoft:  'rgba(139,92,246,0.16)',
    // Semantic
    success:      palette.success[500],
    warning:      palette.warning[500],
    danger:       palette.danger[500],
    info:         palette.info[500],
    // Accents
    accentCyan:   palette.cyan[400],
    accentPink:   palette.pink[400],
    accentGold:   palette.warning[400],
    // Overlays
    overlay:      'rgba(4,6,13,0.72)',
    overlayLight: 'rgba(4,6,13,0.45)',
    // Misc
    shadow:       '#000000',
    skeleton:     palette.ink[800],
  },
  light: {
    bg:           palette.ink[50],
    bgElevated:   '#FFFFFF',
    bgSubtle:     palette.ink[100],
    bgMuted:      palette.ink[200],
    surface:      'rgba(0,0,0,0.03)',
    surfaceAlt:   'rgba(0,0,0,0.05)',
    surfaceHover: 'rgba(0,0,0,0.08)',
    border:       'rgba(0,0,0,0.08)',
    borderStrong: 'rgba(0,0,0,0.14)',
    borderFocus:  palette.brand[600],
    text:         palette.ink[900],
    textMuted:    palette.ink[500],
    textDim:      palette.ink[400],
    textDisabled: palette.ink[300],
    textInverse:  palette.ink[50],
    primary:      palette.brand[600],
    primaryHover: palette.brand[500],
    primarySoft:  'rgba(139,92,246,0.10)',
    success:      palette.success[600],
    warning:      palette.warning[600],
    danger:       palette.danger[600],
    info:         palette.info[600],
    accentCyan:   palette.cyan[600],
    accentPink:   palette.pink[600],
    accentGold:   palette.warning[500],
    overlay:      'rgba(0,0,0,0.45)',
    overlayLight: 'rgba(0,0,0,0.20)',
    shadow:       '#000000',
    skeleton:     palette.ink[100],
  },
} as const;

export type Theme = typeof colors.dark;

// ─────────────────────────────────────────────────────────────────────
//  GRADIENTS — used for hero surfaces, cards, buttons
// ─────────────────────────────────────────────────────────────────────
const gradients = {
  // Hero aurora — purple → cyan, deep, premium
  aurora:        ['#1E1B4B', '#312E81', '#1E1B4B'] as const,
  auroraVivid:   ['#8B5CF6', '#3B82F6', '#EC4899'] as const,
  // Brand wash
  brand:         ['#7C3AED', '#A78BFA'] as const,
  brandSoft:     ['#7C3AED44', '#A78BFA22'] as const,
  // Cosmic background (subtle)
  cosmic:        ['#070B16', '#0F172A', '#0B1120'] as const,
  cosmicMesh:    ['#0B1120', '#1E1B4B', '#0B1120'] as const,
  // Accent washes
  cyan:          ['#1D4ED8', '#3B82F6'] as const,
  pink:          ['#DB2777', '#F472B6'] as const,
  sunset:        ['#F59E0B', '#EC4899'] as const,
  emerald:       ['#059669', '#34D399'] as const,
  // Glass surfaces
  glass:         ['rgba(255,255,255,0.06)', 'rgba(255,255,255,0.02)'] as const,
  glassStrong:   ['rgba(255,255,255,0.12)', 'rgba(255,255,255,0.04)'] as const,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  SPACING — 8pt-based scale
// ─────────────────────────────────────────────────────────────────────
const spacing = {
  none: 0,
  xs:   4,
  sm:   8,
  md:   12,
  base: 16,
  lg:   20,
  xl:   24,
  '2xl': 32,
  '3xl': 40,
  '4xl': 56,
  '5xl': 72,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  RADII — consistent rounding
// ─────────────────────────────────────────────────────────────────────
const radii = {
  none: 0,
  xs:   4,
  sm:   8,
  md:   12,
  lg:   16,
  xl:   20,
  '2xl': 28,
  '3xl': 36,
  full: 9999,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  TYPOGRAPHY — refined scale, system-first
// ─────────────────────────────────────────────────────────────────────
const FONT_UI = Platform.select({
  ios: 'System',
  android: 'sans-serif',
  default: 'System',
}) as string;
const FONT_MONO = Platform.select({
  ios: 'Menlo',
  android: 'monospace',
  default: 'monospace',
}) as string;

const typography = {
  fontFamily: {
    ui:   FONT_UI,
    mono: FONT_MONO,
  },
  // Type scale (mobile-first)
  display: {
    fontFamily: FONT_UI, fontSize: 34, lineHeight: 40, fontWeight: '800',
    letterSpacing: -0.5,
  } as TextStyle,
  h1: {
    fontFamily: FONT_UI, fontSize: 28, lineHeight: 34, fontWeight: '800',
    letterSpacing: -0.4,
  } as TextStyle,
  h2: {
    fontFamily: FONT_UI, fontSize: 22, lineHeight: 28, fontWeight: '700',
    letterSpacing: -0.3,
  } as TextStyle,
  h3: {
    fontFamily: FONT_UI, fontSize: 18, lineHeight: 24, fontWeight: '700',
    letterSpacing: -0.2,
  } as TextStyle,
  h4: {
    fontFamily: FONT_UI, fontSize: 16, lineHeight: 22, fontWeight: '700',
    letterSpacing: -0.1,
  } as TextStyle,
  body: {
    fontFamily: FONT_UI, fontSize: 14, lineHeight: 20, fontWeight: '500',
  } as TextStyle,
  bodyLg: {
    fontFamily: FONT_UI, fontSize: 16, lineHeight: 24, fontWeight: '500',
  } as TextStyle,
  caption: {
    fontFamily: FONT_UI, fontSize: 12, lineHeight: 16, fontWeight: '600',
  } as TextStyle,
  micro: {
    fontFamily: FONT_UI, fontSize: 10, lineHeight: 14, fontWeight: '700',
    letterSpacing: 0.4, textTransform: 'uppercase',
  } as TextStyle,
  mono: {
    fontFamily: FONT_MONO, fontSize: 13, lineHeight: 18, fontWeight: '500',
  } as TextStyle,
  monoSm: {
    fontFamily: FONT_MONO, fontSize: 11, lineHeight: 14, fontWeight: '500',
  } as TextStyle,
  // Button labels
  buttonLg: {
    fontFamily: FONT_UI, fontSize: 16, lineHeight: 20, fontWeight: '700',
    letterSpacing: -0.1,
  } as TextStyle,
  button: {
    fontFamily: FONT_UI, fontSize: 14, lineHeight: 18, fontWeight: '700',
  } as TextStyle,
  buttonSm: {
    fontFamily: FONT_UI, fontSize: 12, lineHeight: 16, fontWeight: '700',
  } as TextStyle,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  ELEVATIONS — layered shadows (cross-platform safe)
// ─────────────────────────────────────────────────────────────────────
const elevation = {
  none: {} as ViewStyle,
  xs: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.18, shadowRadius: 2 },
    android: { elevation: 1 },
    default: {},
  }) as ViewStyle,
  sm: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.22, shadowRadius: 4 },
    android: { elevation: 2 },
    default: {},
  }) as ViewStyle,
  md: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.28, shadowRadius: 10 },
    android: { elevation: 4 },
    default: {},
  }) as ViewStyle,
  lg: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.34, shadowRadius: 18 },
    android: { elevation: 8 },
    default: {},
  }) as ViewStyle,
  xl: Platform.select({
    ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 14 }, shadowOpacity: 0.42, shadowRadius: 28 },
    android: { elevation: 16 },
    default: {},
  }) as ViewStyle,
  // Brand glow (purple)
  glow: Platform.select({
    ios: { shadowColor: '#8B5CF6', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.55, shadowRadius: 18 },
    android: { elevation: 8 },
    default: {},
  }) as ViewStyle,
  // Cyan glow
  glowCyan: Platform.select({
    ios: { shadowColor: '#3B82F6', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.55, shadowRadius: 16 },
    android: { elevation: 6 },
    default: {},
  }) as ViewStyle,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  MOTION — durations + easings for Reanimated
// ─────────────────────────────────────────────────────────────────────
const motion = {
  duration: {
    instant: 0,
    micro:   80,
    fast:    150,
    base:    220,
    slow:    320,
    epic:    600,
  },
  easing: {
    standard: [0.4, 0, 0.2, 1] as [number, number, number, number],
    decelerate: [0, 0, 0.2, 1] as [number, number, number, number],
    accelerate: [0.4, 0, 1, 1] as [number, number, number, number],
    spring:     [0.34, 1.56, 0.64, 1] as [number, number, number, number],
  },
} as const;

// ─────────────────────────────────────────────────────────────────────
//  BREATHING ROOM — 2026 SOTA spacing praxis (no overlap, no cramming)
//  Use these constants in every new screen so the layout breathes.
//  Default values land on: 14px gutters · 12px gaps · 44px taps.
// ─────────────────────────────────────────────────────────────────────
const breathing = {
  // Horizontal screen gutter — slightly bigger than 12 to feel generous
  gutter:        14,
  gutterLg:      18,
  // Vertical row gaps between major sections
  rowGap:        12,
  rowGapLg:      16,
  // Section spacing (between cards, between H1 → body, etc)
  sectionGap:    20,
  // Card / list-item padding
  cardPadding:   14,
  cardGap:       12,
  // Minimum touch target (Apple HIG = 44 / Material = 48 — use 44)
  minTouch:      44,
  minTouchSm:    38,        // for dense secondary controls
  // Bottom safe-area minimum (always at least this, ignoring inset)
  safeBottomMin: 14,
  // Header (sub-screen back-button + title)
  headerHeight:  56,
  // Stacked text rhythm — line-height bumps for legibility
  rhythmText:    8,
} as const;

// ─────────────────────────────────────────────────────────────────────
//  HIT SLOP — uniform tap-area expansion
// ─────────────────────────────────────────────────────────────────────
const hitSlop = {
  sm: { top: 6, left: 6, right: 6, bottom: 6 },
  md: { top: 10, left: 10, right: 10, bottom: 10 },
  lg: { top: 14, left: 14, right: 14, bottom: 14 },
} as const;

// ─────────────────────────────────────────────────────────────────────
//  COMBINED THEME EXPORT — for ThemeProvider consumers
// ─────────────────────────────────────────────────────────────────────
const theme = {
  colors:    colors.dark,   // default scheme
  gradients,
  spacing,
  radii,
  typography,
  elevation,
  motion,
  hitSlop,
  breathing,
  palette,
} as const;

export type DesignTheme = typeof theme;

export default theme;
