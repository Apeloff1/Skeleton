/**
 * <ActionButton> — dependency-light accessible button for foundation screens.
 *
 * Token colours only, 44 px minimum target (WCAG 2.5.8), visible focus ring on
 * web (2.4.7/2.4.11), role/label/state exposed to assistive tech (4.1.2), and a
 * busy state that keeps the label announced. Unlike the gradient/haptics
 * `components/primitives/Button`, it renders in Node SSR tests and on any host.
 */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { MIN_TOUCH_TARGET } from './a11y';
import { color, textVariants } from './tokens';

export type ActionButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

export interface ActionButtonProps {
  label: string;
  onPress?: () => void;
  variant?: ActionButtonVariant;
  disabled?: boolean;
  busy?: boolean;
  /** Spoken label when it must differ from the visible label. */
  accessibilityLabel?: string;
  accessibilityHint?: string;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}

export function ActionButton({
  label, onPress, variant = 'primary', disabled, busy, accessibilityLabel, accessibilityHint, testID, style,
}: ActionButtonProps) {
  const inactive = !!disabled || !!busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: !!busy }}
      aria-disabled={inactive || undefined}
      aria-busy={busy || undefined}
      disabled={inactive}
      onPress={inactive ? undefined : onPress}
      testID={testID}
      style={({ pressed, focused }: { pressed: boolean; focused?: boolean }) => [
        styles.base,
        styles[variant],
        pressed && !inactive ? styles.pressed : null,
        focused ? styles.focused : null,
        inactive ? styles.inactive : null,
        style,
      ]}
    >
      {busy ? (
        <View aria-hidden importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
          <ActivityIndicator size="small" color={variant === 'primary' ? color.onPrimary : color.text} />
        </View>
      ) : null}
      <Text style={[textVariants.label, styles.text, variant === 'primary' ? styles.onPrimary : null]} allowFontScaling maxFontSizeMultiplier={2}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: MIN_TOUCH_TARGET, minWidth: MIN_TOUCH_TARGET, paddingHorizontal: 16, borderRadius: 10,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1,
  },
  primary: { backgroundColor: color.primary, borderColor: color.primary },
  secondary: { backgroundColor: color.surfaceRaised, borderColor: color.border },
  danger: { backgroundColor: color.surfaceRaised, borderColor: color.danger },
  ghost: { backgroundColor: 'transparent', borderColor: 'transparent' },
  pressed: { opacity: 0.85 },
  focused: { outlineColor: color.focus, outlineWidth: 2, outlineStyle: 'solid', outlineOffset: 2 } as ViewStyle,
  inactive: { opacity: 0.6 },
  text: { color: color.text },
  onPrimary: { color: color.onPrimary },
});

export default ActionButton;
