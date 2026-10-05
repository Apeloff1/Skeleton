/**
 * <Button> — 2026 SOTA touch target with haptics + spring animation.
 *
 *  Variants: primary, secondary, ghost, destructive, gradient
 *  Sizes:    sm (32), base (44 — iOS HIG), lg (52)
 *  Optional: icon (left), iconRight, loading, fullWidth, disabled
 */
import React from 'react';
import {
  Pressable, View, Text, ActivityIndicator, ViewStyle, StyleProp,
  TextStyle, Platform, StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import theme from '../../theme/tokens';

type Variant = 'primary' | 'secondary' | 'ghost' | 'destructive' | 'gradient';
type Size = 'sm' | 'base' | 'lg';

interface ButtonProps {
  label?: string;
  onPress?: () => void;
  variant?: Variant;
  size?: Size;
  icon?: keyof typeof Ionicons.glyphMap;
  iconRight?: keyof typeof Ionicons.glyphMap;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  haptic?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  gradient?: keyof typeof theme.gradients;
  testID?: string;
  accessibilityLabel?: string;
  children?: React.ReactNode;
}

const HEIGHTS: Record<Size, number> = { sm: 32, base: 44, lg: 52 };
const PADS:    Record<Size, number> = { sm: 12, base: 16, lg: 20 };
const ICON_SZ: Record<Size, number> = { sm: 14, base: 18, lg: 20 };

const tFor = (size: Size): TextStyle => (
  size === 'sm' ? theme.typography.buttonSm :
  size === 'lg' ? theme.typography.buttonLg :
  theme.typography.button
);

export const Button: React.FC<ButtonProps> = ({
  label, onPress, variant = 'primary', size = 'base',
  icon, iconRight, loading, disabled, fullWidth, haptic = true,
  style, textStyle, gradient = 'brand', testID, accessibilityLabel, children,
}) => {
  const isDisabled = disabled || loading;

  const handlePress = () => {
    if (isDisabled) return;
    if (haptic && Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }
    onPress?.();
  };

  const baseStyle: ViewStyle = {
    height: HEIGHTS[size],
    paddingHorizontal: PADS[size],
    borderRadius: theme.radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    overflow: 'hidden',
    alignSelf: fullWidth ? 'stretch' : 'flex-start',
    opacity: isDisabled ? 0.5 : 1,
  };

  let bg: string | undefined;
  let borderColor: string | undefined;
  let labelColor: string = theme.colors.text;
  let useGradient = false;

  switch (variant) {
    case 'primary':
      bg = theme.colors.primary;
      labelColor = theme.colors.text;
      break;
    case 'secondary':
      bg = theme.colors.surface;
      borderColor = theme.colors.borderStrong;
      labelColor = theme.colors.text;
      break;
    case 'ghost':
      bg = 'transparent';
      labelColor = theme.colors.text;
      break;
    case 'destructive':
      bg = theme.colors.danger;
      labelColor = '#fff';
      break;
    case 'gradient':
      useGradient = true;
      labelColor = '#fff';
      break;
  }

  const content = (
    <>
      {icon && !loading && (
        <Ionicons name={icon} size={ICON_SZ[size]} color={labelColor} />
      )}
      {loading && <ActivityIndicator size="small" color={labelColor} />}
      {(label || children) && (
        <Text style={[tFor(size), { color: labelColor }, textStyle]} numberOfLines={1}>
          {label ?? children}
        </Text>
      )}
      {iconRight && !loading && (
        <Ionicons name={iconRight} size={ICON_SZ[size]} color={labelColor} />
      )}
    </>
  );

  return (
    <Pressable
      onPress={handlePress}
      disabled={isDisabled}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || label}
      hitSlop={theme.hitSlop.sm}
      style={({ pressed }) => [
        baseStyle,
        !useGradient && { backgroundColor: bg, borderWidth: borderColor ? 1 : 0, borderColor },
        variant === 'primary' && theme.elevation.glow,
        pressed && !isDisabled && { transform: [{ scale: 0.97 }], opacity: 0.92 },
        style,
      ]}
    >
      {useGradient ? (
        <>
          <LinearGradient
            colors={theme.gradients[gradient] as any}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={StyleSheet.absoluteFillObject}
          />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {content}
          </View>
        </>
      ) : content}
    </Pressable>
  );
};

export default Button;
