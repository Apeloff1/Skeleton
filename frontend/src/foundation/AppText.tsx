import React from 'react';
import { Text, TextProps } from 'react-native';
import { color as colors, ColorToken, isHeadingVariant, TextVariant, textVariants } from './tokens';

export interface AppTextProps extends TextProps {
  variant?: TextVariant;
  color?: ColorToken;
  align?: 'auto' | 'left' | 'right' | 'center';
}

/** Typography primitive: tokens-only styling, headings announce as headers, font scaling on. */
export function AppText({ variant = 'body', color = 'text', align, style, accessibilityRole, ...rest }: AppTextProps) {
  return (
    <Text
      allowFontScaling
      maxFontSizeMultiplier={2}
      accessibilityRole={accessibilityRole ?? (isHeadingVariant(variant) ? 'header' : undefined)}
      style={[textVariants[variant], { color: colors[color] }, align ? { textAlign: align } : null, style]}
      {...rest}
    />
  );
}

export default AppText;
