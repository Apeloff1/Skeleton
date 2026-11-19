/**
 * SafeButton Component v11.4
 * Mobile-optimized button with haptic feedback, proper touch targets, and accessibility
 */

import React, { useCallback, memo } from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  View,
  Platform,
  Vibration,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success';
type ButtonSize = 'sm' | 'md' | 'lg';

interface SafeButtonProps {
  title?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  iconPosition?: 'left' | 'right';
  variant?: ButtonVariant;
  size?: ButtonSize;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  haptic?: boolean;
  fullWidth?: boolean;
  style?: ViewStyle;
  textStyle?: TextStyle;
  accessibilityLabel?: string;
  testID?: string;
  colors?: any;
}

const SIZE_CONFIGS = {
  sm: { height: 36, paddingH: 12, iconSize: 16, fontSize: 13 },
  md: { height: 44, paddingH: 16, iconSize: 18, fontSize: 14 },
  lg: { height: 52, paddingH: 20, iconSize: 20, fontSize: 16 },
};

const VARIANT_COLORS = {
  primary: { bg: '#3B82F6', text: '#FFFFFF', border: '#3B82F6' },
  secondary: { bg: 'transparent', text: '#3B82F6', border: '#3B82F6' },
  ghost: { bg: 'transparent', text: '#6B7280', border: 'transparent' },
  danger: { bg: '#EF4444', text: '#FFFFFF', border: '#EF4444' },
  success: { bg: '#10B981', text: '#FFFFFF', border: '#10B981' },
};

export const SafeButton = memo(function SafeButton({
  title,
  icon,
  iconPosition = 'left',
  variant = 'primary',
  size = 'md',
  onPress,
  disabled = false,
  loading = false,
  haptic = true,
  fullWidth = false,
  style,
  textStyle,
  accessibilityLabel,
  testID,
  colors,
}: SafeButtonProps) {
  const sizeConfig = SIZE_CONFIGS[size];
  const variantColors = colors ? {
    bg: variant === 'primary' ? colors.primary : 
        variant === 'secondary' ? 'transparent' :
        variant === 'ghost' ? 'transparent' :
        variant === 'danger' ? colors.error :
        colors.success,
    text: variant === 'secondary' || variant === 'ghost' ? colors.text : '#FFFFFF',
    border: variant === 'primary' ? colors.primary :
            variant === 'secondary' ? colors.border :
            variant === 'ghost' ? 'transparent' :
            variant === 'danger' ? colors.error :
            colors.success,
  } : VARIANT_COLORS[variant];

  const handlePress = useCallback(() => {
    if (disabled || loading) return;

    if (haptic) {
      if (Platform.OS === 'ios') {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      } else {
        Vibration.vibrate(10);
      }
    }

    onPress();
  }, [disabled, loading, haptic, onPress]);

  const opacity = disabled || loading ? 0.5 : 1;

  return (
    <TouchableOpacity
      onPress={handlePress}
      disabled={disabled || loading}
      activeOpacity={0.7}
      accessibilityLabel={accessibilityLabel || title}
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading }}
      testID={testID}
      style={[
        styles.button,
        {
          height: sizeConfig.height,
          paddingHorizontal: sizeConfig.paddingH,
          backgroundColor: variantColors.bg,
          borderColor: variantColors.border,
          borderWidth: variant === 'secondary' ? 1.5 : 0,
          opacity,
        },
        fullWidth && styles.fullWidth,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator size="small" color={variantColors.text} />
      ) : (
        <View style={styles.content}>
          {icon && iconPosition === 'left' && (
            <Ionicons
              name={icon}
              size={sizeConfig.iconSize}
              color={variantColors.text}
              style={title ? styles.iconLeft : undefined}
            />
          )}
          {title && (
            <Text
              style={[
                styles.text,
                {
                  fontSize: sizeConfig.fontSize,
                  color: variantColors.text,
                },
                textStyle,
              ]}
            >
              {title}
            </Text>
          )}
          {icon && iconPosition === 'right' && (
            <Ionicons
              name={icon}
              size={sizeConfig.iconSize}
              color={variantColors.text}
              style={title ? styles.iconRight : undefined}
            />
          )}
        </View>
      )}
    </TouchableOpacity>
  );
});

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    minWidth: 44,
  },
  fullWidth: {
    width: '100%',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: {
    fontWeight: '600',
  },
  iconLeft: {
    marginRight: 8,
  },
  iconRight: {
    marginLeft: 8,
  },
});
