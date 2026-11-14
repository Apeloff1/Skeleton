/**
 * Text and TextInput that honour the Studio text-size preference.
 *
 * Studio screens set fixed font sizes in StyleSheets. Without this wrapper
 * the Settings "Text size" choice only reached the shared primitives, so
 * long questionnaire copy and run results stayed at their base size. These
 * drop-in replacements scale fontSize/lineHeight by the resolved studio
 * scale and switch off system font scaling only when the user picked an
 * explicit size (so the two never multiply).
 */
import React from 'react';
import { StyleSheet, Text, TextInput, type TextInputProps, type TextProps, type TextStyle } from 'react-native';
import { scaledText, useStudioA11y, type StudioA11y } from './a11yContext';

/** Flatten any style prop and scale its type metrics. Pure; exported for tests. */
export function scaleStyle(style: TextProps['style'], a11y: StudioA11y): TextProps['style'] {
  if (a11y.textScale === 1 || style == null) return style;
  const flat = StyleSheet.flatten(style) as TextStyle | undefined;
  return flat ? scaledText(flat, a11y) : style;
}

function fontScalingProp(explicit: boolean | undefined, a11y: StudioA11y): boolean | undefined {
  if (explicit !== undefined) return explicit;
  return a11y.allowSystemFontScaling ? undefined : false;
}

export const ScaledText = React.forwardRef<Text, TextProps>(function ScaledText(
  { style, allowFontScaling, ...rest }, ref,
) {
  const a11y = useStudioA11y();
  return <Text ref={ref} {...rest} style={scaleStyle(style, a11y)} allowFontScaling={fontScalingProp(allowFontScaling, a11y)} />;
});

export const ScaledTextInput = React.forwardRef<TextInput, TextInputProps>(function ScaledTextInput(
  { style, allowFontScaling, ...rest }, ref,
) {
  const a11y = useStudioA11y();
  return (
    <TextInput
      ref={ref}
      {...rest}
      style={scaleStyle(style as TextProps['style'], a11y) as TextInputProps['style']}
      allowFontScaling={fontScalingProp(allowFontScaling, a11y)}
    />
  );
});
