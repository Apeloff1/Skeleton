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

const palette = {
  ink: {
    0: '#FFFFFF',
    50: '#F8FAFC',
    100: '#E2E8F0',
    200: '#CBD5E1',
    300: '#94A3B8',
    400: '#64748B',
    500: '#475569',
    600: '#334155',
    700: '#1E293B',
    800: '#0F172A',
    850: '#0D1425',
    900: '#0B1120',
    950: '#070B16',
    1000: '#04060D',
  },
  brand: {
    50: '#F5F3FF',
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
  blue: { 400: '#3B82F6', 500: '#2563EB', 600: '#1D4ED8' },
  cyan: { 400: '#22D3EE', 500: '#06B6D4', 600: '#0891B2' },
  pink: { 400: '#F472B6', 500: '#EC4899', 600: '#DB2777' },
  success: { 400: '#34D399', 500: '#10B981', 600: '#059669' },
  warning: { 400: '#FBBF24', 500: '#F59E0B', 600: '#D97706' },
  danger: { 400: '#F87171', 500: '#EF4444', 600: '#DC2626' },
  info: { 400: '#60A5FA', 500: '#3B82F6', 600: '#2563EB' },
} as const;

const colors = {
  dark: {
    bg: palette.ink[950],
    bgElevated: palette.ink[900],
    bgSubtle: palette.ink[850],
    bgMuted: palette.ink[700],
    surface: 'rgba(255,255,255,0.045)',
    surfaceAlt: 'rgba(255,255,255,0.07)',
    surfaceHover: 'rgba(255,255,255,0.10)',
    border: 'rgba(255,255,255,0.10)',
    borderStrong: 'rgba(255,255,255,0.18)',
    borderFocus: palette.brand[400],
    text: palette.ink[50],
    textMuted: palette.ink[300],
    textDim: palette.ink[400],
    textDisabled: palette.ink[500],
    textInverse: palette.ink[900],
    primary: palette.brand[500],
    // Brand500 needs the darkest canonical ink for >= 4.5:1 normal text.
    // White and ink900 both fall slightly below AA on this fill.
    onPrimary: palette.ink[1000],
    primaryHover: palette.brand[400],
    primarySoft: 'rgba(139,92,246,0.16)',
    accent: palette.brand[500],
    success: palette.success[500],
    warning: palette.warning[500],
    danger: palette.danger[500],
    info: palette.info[500],
    accentCyan: palette.cyan[400],
    accentPink: palette.pink[400],
    accentGold: palette.warning[400],
    overlay: 'rgba(4,6,13,0.72)',
    overlayLight: 'rgba(4,6,13,0.45)',
    shadow: '#000000',
    skeleton: palette.ink[800],
  },
  light: {
    bg: palette.ink[50],
    bgElevated: '#FFFFFF',
    bgSubtle: palette.ink[100],
    bgMuted: palette.ink[200],
    surface: 'rgba(0,0,0,0.03)',
    surfaceAlt: 'rgba(0,0,0,0.05)',
    surfaceHover: 'rgba(0,0,0,0.08)',
    border: 'rgba(0,0,0,0.08)',
    borderStrong: 'rgba(0,0,0,0.14)',
    borderFocus: palette.brand[600],
    text: palette.ink[900],
    textMuted: palette.ink[500],
    textDim: palette.ink[400],
    textDisabled: palette.ink[300],
    textInverse: palette.ink[50],
    primary: palette.brand[600],
    onPrimary: palette.ink[0],
    primaryHover: palette.brand[500],
    primarySoft: 'rgba(139,92,246,0.10)',
    accent: palette.brand[600],
    success: palette.success[600],
    warning: palette.warning[600],
    danger: palette.danger[600],
    info: palette.info[600],
    accentCyan: palette.cyan[600],
    accentPink: palette.pink[600],
    accentGold: palette.warning[500],
    overlay: 'rgba(0,0,0,0.45)',
    overlayLight: 'rgba(0,0,0,0.20)',
    shadow: '#000000',
    skeleton: palette.ink[100],
  },
} as const;

export type Theme = typeof colors.dark;

/**
 * Immutable canonical role sets. src/utils/skinStore.ts mutates `theme.colors`
 * (the same object as `colors.dark`) when a skin is applied; this snapshot is
 * taken at module evaluation, before any skin, so consumers that need the
 * canonical kit (theme/foundation getTheme) never see a skin leak.
 */
export const canonicalColors = {
  dark: Object.freeze({ ...colors.dark }),
  light: Object.freeze({ ...colors.light }),
} as const;

/**
 * Text-usage rules per role (docs/UI_ART_KIT.md §2.5 "Rules from the table"):
 * body = may carry body text (>= 4.5:1 on bg); large = large text / icons /
 * dividers only (>= 3:1); never = must never carry information.
 */
export const textUsage = {
  dark: { text: 'body', textMuted: 'body', textDim: 'large', textDisabled: 'never', primaryText: 'body', success: 'body', warning: 'body', danger: 'body', info: 'body', accentPink: 'body' },
  light: { text: 'body', textMuted: 'body', textDim: 'body', textDisabled: 'never', primaryText: 'body', success: 'large', warning: 'large', danger: 'body', accentGold: 'never' },
} as const;

/**
 * HUD status pairing: colour + glyph + shape, never hue alone
 * (docs/UI_ART_KIT.md §3.4, docs/UI_ART_HUD_SEMANTIC.md §2). ok/warn/bad/idle
 * are the Forge cockpit TONE_GLYPH set; info adds `i`.
 */
export const status = {
  glyph: { ok: '✓', warn: '!', bad: '✕', info: 'i', idle: '○' },
  shape: { ok: 'solid', warn: 'triangle-dashed', bad: 'diamond', info: 'circle-outline', idle: 'hollow' },
  opacity: { ok: 1, warn: 1, bad: 1, info: 1, idle: 0.5 },
  meaning: { ok: 'good / friendly', warn: 'warning', bad: 'bad / hostile', info: 'info / neutral', idle: 'idle / unavailable' },
} as const;

const gradients = {
  aurora: ['#1E1B4B', '#312E81', '#1E1B4B'] as const,
  auroraVivid: ['#8B5CF6', '#3B82F6', '#EC4899'] as const,
  brand: ['#7C3AED', '#A78BFA'] as const,
  brandSoft: ['#7C3AED44', '#A78BFA22'] as const,
  cosmic: ['#070B16', '#0F172A', '#0B1120'] as const,
  cosmicMesh: ['#0B1120', '#1E1B4B', '#0B1120'] as const,
  cyan: ['#1D4ED8', '#3B82F6'] as const,
  pink: ['#DB2777', '#F472B6'] as const,
  sunset: ['#F59E0B', '#EC4899'] as const,
  emerald: ['#059669', '#34D399'] as const,
  glass: ['rgba(255,255,255,0.06)', 'rgba(255,255,255,0.02)'] as const,
  glassStrong: ['rgba(255,255,255,0.12)', 'rgba(255,255,255,0.04)'] as const,
} as const;

const spacing = { none: 0, xs: 4, sm: 8, md: 12, base: 16, lg: 20, xl: 24, '2xl': 32, '3xl': 40, '4xl': 56, '5xl': 72 } as const;
const radii = { none: 0, xs: 4, sm: 8, md: 12, lg: 16, xl: 20, '2xl': 28, '3xl': 36, full: 9999, pill: 9999 } as const;

const FONT_UI = Platform.select({ ios: 'System', android: 'sans-serif', default: 'System' }) as string;
const FONT_MONO = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }) as string;
const typography = {
  fontFamily: { ui: FONT_UI, mono: FONT_MONO },
  display: { fontFamily: FONT_UI, fontSize: 34, lineHeight: 40, fontWeight: '800', letterSpacing: -0.5 } as TextStyle,
  h1: { fontFamily: FONT_UI, fontSize: 28, lineHeight: 34, fontWeight: '800', letterSpacing: -0.4 } as TextStyle,
  h2: { fontFamily: FONT_UI, fontSize: 22, lineHeight: 28, fontWeight: '700', letterSpacing: -0.3 } as TextStyle,
  h3: { fontFamily: FONT_UI, fontSize: 18, lineHeight: 24, fontWeight: '700', letterSpacing: -0.2 } as TextStyle,
  h4: { fontFamily: FONT_UI, fontSize: 16, lineHeight: 22, fontWeight: '700', letterSpacing: -0.1 } as TextStyle,
  metric: { fontFamily: FONT_UI, fontSize: 24, lineHeight: 28, fontWeight: '800', letterSpacing: 0.5, fontVariant: ['tabular-nums'] } as TextStyle,
  label: { fontFamily: FONT_UI, fontSize: 12, lineHeight: 16, fontWeight: '700', letterSpacing: 1.1, textTransform: 'uppercase' } as TextStyle,
  body: { fontFamily: FONT_UI, fontSize: 14, lineHeight: 20, fontWeight: '500' } as TextStyle,
  bodyLg: { fontFamily: FONT_UI, fontSize: 16, lineHeight: 24, fontWeight: '500' } as TextStyle,
  caption: { fontFamily: FONT_UI, fontSize: 12, lineHeight: 16, fontWeight: '600' } as TextStyle,
  micro: { fontFamily: FONT_UI, fontSize: 10, lineHeight: 14, fontWeight: '700', letterSpacing: 0.4, textTransform: 'uppercase' } as TextStyle,
  mono: { fontFamily: FONT_MONO, fontSize: 13, lineHeight: 18, fontWeight: '500' } as TextStyle,
  monoSm: { fontFamily: FONT_MONO, fontSize: 11, lineHeight: 14, fontWeight: '500' } as TextStyle,
  buttonLg: { fontFamily: FONT_UI, fontSize: 16, lineHeight: 20, fontWeight: '700', letterSpacing: -0.1 } as TextStyle,
  button: { fontFamily: FONT_UI, fontSize: 14, lineHeight: 18, fontWeight: '700' } as TextStyle,
  buttonSm: { fontFamily: FONT_UI, fontSize: 12, lineHeight: 16, fontWeight: '700' } as TextStyle,
} as const;

const elevation = {
  none: {} as ViewStyle,
  xs: Platform.select({ ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.18, shadowRadius: 2 }, android: { elevation: 1 }, default: {} }) as ViewStyle,
  sm: Platform.select({ ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.22, shadowRadius: 4 }, android: { elevation: 2 }, default: {} }) as ViewStyle,
  md: Platform.select({ ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.28, shadowRadius: 10 }, android: { elevation: 4 }, default: {} }) as ViewStyle,
  lg: Platform.select({ ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.34, shadowRadius: 18 }, android: { elevation: 8 }, default: {} }) as ViewStyle,
  xl: Platform.select({ ios: { shadowColor: '#000', shadowOffset: { width: 0, height: 14 }, shadowOpacity: 0.42, shadowRadius: 28 }, android: { elevation: 16 }, default: {} }) as ViewStyle,
  glow: Platform.select({ ios: { shadowColor: '#8B5CF6', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.55, shadowRadius: 18 }, android: { elevation: 8 }, default: {} }) as ViewStyle,
  glowCyan: Platform.select({ ios: { shadowColor: '#3B82F6', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.55, shadowRadius: 16 }, android: { elevation: 6 }, default: {} }) as ViewStyle,
} as const;

const motion = {
  duration: { instant: 0, micro: 80, fast: 150, base: 220, slow: 320, epic: 600 },
  easing: {
    standard: [0.4, 0, 0.2, 1] as [number, number, number, number],
    decelerate: [0, 0, 0.2, 1] as [number, number, number, number],
    accelerate: [0.4, 0, 1, 1] as [number, number, number, number],
    spring: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
  },
} as const;

const breathing = { gutter: 14, gutterLg: 18, rowGap: 12, rowGapLg: 16, sectionGap: 20, cardPadding: 14, cardGap: 12, minTouch: 44, minTouchSm: 38, safeBottomMin: 14, headerHeight: 56, rhythmText: 8 } as const;
const hitSlop = { sm: { top: 6, left: 6, right: 6, bottom: 6 }, md: { top: 10, left: 10, right: 10, bottom: 10 }, lg: { top: 14, left: 14, right: 14, bottom: 14 } } as const;

/**
 * HUD layout and timing rules (docs/UI_ART_KIT.md §3.1–3.5).
 * Safe zones are fractions of the screen; durations reference `motion`.
 */
export const hud = {
  safeZone: { titleSafe: 0.05, actionSafe: 0.025, thumbZone: 0.4, centreClear: 0.4 },
  minMovingTextSize: 14,
  motion: {
    stateIn: motion.duration.fast,
    stateOut: motion.duration.base,
    press: motion.duration.micro,
    pressScale: 0.97,
    shimmer: motion.duration.slow,
    ambientFade: motion.duration.slow * 10,
    maxFlashesPerSecond: 3,
    maxPulsingPerTier: 1,
  },
  glowMaxPerScreen: 1,
} as const;

/** Iconography grid, stroke and size table (docs/UI_ART_ICONOGRAPHY.md §1–5). */
export const iconography = {
  grid: {
    artboard: 24, padding: 2, liveArea: 20,
    keylines: { circle: 20, square: 18, portrait: { width: 16, height: 20 }, landscape: { width: 20, height: 16 } },
    squareCornerRadius: 2, opticalShiftX: 0.5, viewBox: '0 0 24 24',
  },
  sizes: [16, 20, 24, 32, 48] as const,
  spec: {
    16: { stroke: 1.5, padding: 1, minTouch: null, use: 'inline with caption/body, table status' },
    20: { stroke: 1.75, padding: 1.5, minTouch: 44, use: 'list rows, buttons with body label' },
    24: { stroke: 2, padding: 2, minTouch: 44, use: 'default; tab bar, toolbar, HUD contextual' },
    32: { stroke: 2.5, padding: 2.5, minTouch: 48, use: 'HUD critical, empty states' },
    48: { stroke: 3, padding: 4, minTouch: null, use: 'feature tiles, onboarding, results' },
  },
  strokeStyle: { strokeLinecap: 'round', strokeLinejoin: 'round', fill: 'none', stroke: 'currentColor' },
  domains: ['nav', 'hud', 'forge', 'status', 'action', 'social', 'store'] as const,
} as const;

/**
 * 30 runtime skins (moved here from theme/skins.ts so this file is the single
 * edit point). Row: id, name, emoji, bg, bgElevated, primary, primaryHover,
 * accentCyan, accentPink, accentGold. theme/skins.ts derives bgSubtle,
 * onPrimary, primarySoft and borderFocus from these rows.
 */
export const DEFAULT_SKIN_ID = 'hyperwave';
export const skinPalettes = [
  ['hyperwave', 'Hyperwave', '🌌', '#0b0820', '#15103a', '#c026d3', '#e879f9', '#3B82F6', '#f472b6', '#fbbf24'],
  ['midnight', 'Midnight', '🌑', '#070910', '#10131f', '#3b82f6', '#60a5fa', '#60A5FA', '#818cf8', '#fcd34d'],
  ['aurora', 'Aurora', '🌠', '#04130f', '#082018', '#10b981', '#34d399', '#3B82F6', '#a3e635', '#fde047'],
  ['ember', 'Ember', '🔥', '#170a06', '#23110a', '#f97316', '#fb923c', '#fbbf24', '#f87171', '#fde68a'],
  ['forest', 'Forest', '🌲', '#08120b', '#0e1d13', '#22c55e', '#4ade80', '#60A5FA', '#a3e635', '#facc15'],
  ['mono', 'Mono', '⬜', '#0a0a0a', '#161616', '#d4d4d4', '#fafafa', '#a3a3a3', '#737373', '#e5e5e5'],
  ['sakura', 'Sakura', '🌸', '#1a0d14', '#26121d', '#ec4899', '#f472b6', '#f9a8d4', '#c084fc', '#fbcfe8'],
  ['oceanic', 'Oceanic', '🌊', '#04121a', '#072030', '#3B82F6', '#60A5FA', '#3B82F6', '#60A5FA', '#93C5FD'],
  ['neon', 'Neon', '💚', '#060d06', '#0c180c', '#84cc16', '#a3e635', '#3B82F6', '#f0abfc', '#fde047'],
  ['sunset', 'Sunset', '🌇', '#1a0a0f', '#27101a', '#fb7185', '#fda4af', '#fb923c', '#c084fc', '#fcd34d'],
  ['glacier', 'Glacier', '🧊', '#080f17', '#0e1a26', '#93C5FD', '#BFDBFE', '#93C5FD', '#c4b5fd', '#DBEAFE'],
  ['vapor', 'Vapor', '🪐', '#0f0a1a', '#1a1130', '#a78bfa', '#c4b5fd', '#3B82F6', '#f0abfc', '#fde68a'],
  ['goldnoir', 'Gold Noir', '🪙', '#0c0a06', '#17130a', '#f5c451', '#fcd34d', '#d4a373', '#fbbf24', '#fde68a'],
  ['matrix', 'Matrix', '🟩', '#020a04', '#06140a', '#22c55e', '#4ade80', '#16a34a', '#15803d', '#86efac'],
  ['crimson', 'Crimson', '🩸', '#150407', '#23070c', '#ef4444', '#f87171', '#fb7185', '#fb923c', '#fca5a5'],
  ['lavender', 'Lavender', '💜', '#100c1a', '#1b1430', '#8b5cf6', '#a78bfa', '#c4b5fd', '#f0abfc', '#ddd6fe'],
  ['coffee', 'Coffee', '☕', '#120c08', '#1e150d', '#b45309', '#d97706', '#f59e0b', '#a16207', '#fcd34d'],
  ['arctic', 'Arctic', '❄️', '#0a0f14', '#121b24', '#60A5FA', '#93C5FD', '#BFDBFE', '#c4b5fd', '#DBEAFE'],
  ['toxic', 'Toxic', '☢️', '#0a0f02', '#141d06', '#a3e635', '#bef264', '#3B82F6', '#f0abfc', '#fde047'],
  ['royal', 'Royal', '👑', '#080a1a', '#0f1330', '#6366f1', '#818cf8', '#3B82F6', '#c084fc', '#fbbf24'],
  ['peach', 'Peach', '🍑', '#1a0f0a', '#281913', '#fb923c', '#fdba74', '#f472b6', '#fcd34d', '#fed7aa'],
  ['slate', 'Slate', '🪨', '#0a0c0f', '#141820', '#64748b', '#94a3b8', '#60A5FA', '#a78bfa', '#cbd5e1'],
  ['mint', 'Mint', '🌿', '#06120e', '#0b1f18', '#60A5FA', '#93C5FD', '#3B82F6', '#a3e635', '#BFDBFE'],
  ['blood', 'Blood Moon', '🌕', '#140505', '#220909', '#dc2626', '#ef4444', '#f97316', '#a855f7', '#fbbf24'],
  ['cyber', 'Cyber', '🤖', '#080612', '#100c22', '#2563EB', '#3B82F6', '#e879f9', '#f0abfc', '#fde047'],
  ['dune', 'Dune', '🏜️', '#120e07', '#1f180d', '#d97706', '#f59e0b', '#fbbf24', '#ea580c', '#fde68a'],
  ['nebula', 'Nebula', '✨', '#0b0718', '#150e2c', '#a855f7', '#c084fc', '#3B82F6', '#f472b6', '#fcd34d'],
  ['rosegold', 'Rose Gold', '🌹', '#160c0f', '#23131a', '#fda4af', '#fecdd3', '#f9a8d4', '#fbbf24', '#fde68a'],
  ['obsidian', 'Obsidian', '⬛', '#050507', '#0d0d12', '#818cf8', '#a5b4fc', '#60A5FA', '#c084fc', '#e5e7eb'],
  ['citrus', 'Citrus', '🍋', '#0f1003', '#1b1d06', '#eab308', '#facc15', '#84cc16', '#f97316', '#fde047'],
] as const;
export type SkinPaletteRow = (typeof skinPalettes)[number];

/**
 * Default export. `colors` is the LIVE dark palette (skinStore mutates it in
 * place); `colorModes` is the {dark, light} pair. Bindings that live on this
 * object are deliberately NOT also named exports, so consumers read them as
 * `theme.x` without tripping import/no-named-as-default-member (lint:ci).
 * Named exports are reserved for values that are not on this object.
 */
const theme = { colors: colors.dark, colorModes: colors, gradients, spacing, radii, typography, elevation, motion, hitSlop, breathing, palette } as const;
export type DesignTheme = typeof theme;
export default theme;
