// ============================================================================
// CODEDOCK QUANTUM NEXUS - THEME DEFINITIONS
// Version: 4.2.0 | Refactored Architecture
// ============================================================================

export interface ThemeColors {
  background: string;
  surface: string;
  surfaceAlt: string;
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

export const darkTheme: ThemeColors = {
  background: '#0A0A0F',
  surface: '#12121A',
  surfaceAlt: '#1A1A24',
  text: '#FFFFFF',
  textSecondary: '#A0A0B0',
  textMuted: '#606070',
  primary: '#6366F1',
  secondary: '#8B5CF6',
  accent: '#22D3EE',
  success: '#22C55E',
  warning: '#F59E0B',
  error: '#EF4444',
  border: '#2A2A3A',
  borderSubtle: '#1F1F2E',
  codeBackground: '#0D0D14',
  lineNumbers: '#404050',
  tutorial: '#8B5CF6',
  tutorialGlow: 'rgba(139, 92, 246, 0.3)',
  gold: '#FFD700',
  gradient: ['#6366F1', '#8B5CF6', '#A855F7'],
};

export const lightTheme: ThemeColors = {
  background: '#F8FAFC',
  surface: '#FFFFFF',
  surfaceAlt: '#F1F5F9',
  text: '#0F172A',
  textSecondary: '#475569',
  textMuted: '#94A3B8',
  primary: '#4F46E5',
  secondary: '#7C3AED',
  accent: '#0891B2',
  success: '#16A34A',
  warning: '#D97706',
  error: '#DC2626',
  border: '#E2E8F0',
  borderSubtle: '#F1F5F9',
  codeBackground: '#F8FAFC',
  lineNumbers: '#94A3B8',
  tutorial: '#7C3AED',
  tutorialGlow: 'rgba(124, 58, 237, 0.2)',
  gold: '#CA8A04',
  gradient: ['#4F46E5', '#7C3AED', '#9333EA'],
};

export const themes = {
  dark: darkTheme,
  light: lightTheme,
};

export type ThemeType = keyof typeof themes;
