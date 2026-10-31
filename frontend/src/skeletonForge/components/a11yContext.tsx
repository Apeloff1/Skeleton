/**
 * Optional studio text scale and reduced motion. Defaults match the cockpit
 * as it is today: system font scaling on, press feedback on.
 */
import React from 'react';
import type { TextStyle } from 'react-native';

export interface StudioA11y {
  reduceMotion: boolean;
  textScale: number;
  allowSystemFontScaling: boolean;
}

const DEFAULT_A11Y: StudioA11y = { reduceMotion: false, textScale: 1, allowSystemFontScaling: true };
const StudioA11yContext = React.createContext<StudioA11y>(DEFAULT_A11Y);

export function StudioA11yProvider({ value, children }: { value: StudioA11y; children: React.ReactNode }) {
  return <StudioA11yContext.Provider value={value}>{children}</StudioA11yContext.Provider>;
}

export function useStudioA11y(): StudioA11y {
  return React.useContext(StudioA11yContext);
}

export function scaledText(style: TextStyle, a11y: StudioA11y): TextStyle {
  if (a11y.textScale === 1) return style;
  const fontSize = typeof style.fontSize === 'number' ? Math.round(style.fontSize * a11y.textScale) : style.fontSize;
  const lineHeight = typeof style.lineHeight === 'number' ? Math.round(style.lineHeight * a11y.textScale) : style.lineHeight;
  return { ...style, fontSize, lineHeight };
}
