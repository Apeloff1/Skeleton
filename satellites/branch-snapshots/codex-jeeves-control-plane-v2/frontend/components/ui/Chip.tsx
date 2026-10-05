/**
 * <Chip> — pill-shaped tag / filter / category selector.
 *
 * 2026-02 — Added a Reanimated `scale: 0.96` press animation for parity
 * with FeatureCard so chip interactions feel responsive and tactile.
 */
import React from 'react';
import { Pressable, Text, View, ViewStyle, StyleProp } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import theme from '../../theme/tokens';

interface ChipProps {
  label: string;
  icon?: keyof typeof Ionicons.glyphMap;
  active?: boolean;
  accentColor?: string;
  count?: number | string;
  onPress?: () => void;
  size?: 'sm' | 'base';
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export const Chip: React.FC<ChipProps> = ({
  label, icon, active, accentColor, count, onPress, size = 'base', style, testID,
}) => {
  const accent   = accentColor || theme.colors.primary;
  const height   = size === 'sm' ? 26 : 32;
  const paddingH = size === 'sm' ? 10 : 14;
  const fontSize = size === 'sm' ? 11 : 13;

  const scale = useSharedValue(1);
  const anim  = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return (
    <Animated.View style={[anim, style]}>
      <Pressable
        testID={testID}
        onPress={onPress}
        onPressIn={()  => { scale.value = withSpring(0.96, { damping: 18, stiffness: 320 }); }}
        onPressOut={() => { scale.value = withSpring(1,    { damping: 14, stiffness: 220 }); }}
        style={({ pressed }) => ({
          height, paddingHorizontal: paddingH,
          borderRadius: theme.radii.full,
          flexDirection: 'row', alignItems: 'center', gap: 6,
          backgroundColor: active ? accent + '22' : theme.colors.surface,
          borderWidth: 1,
          borderColor: active ? accent : theme.colors.border,
          opacity: pressed ? 0.9 : 1,
        })}
        hitSlop={theme.hitSlop.sm}
      >
        {icon && (
          <Ionicons
            name={icon}
            size={size === 'sm' ? 11 : 13}
            color={active ? accent : theme.colors.textMuted}
          />
        )}
        <Text style={{
          color: active ? accent : theme.colors.textMuted,
          fontSize, fontWeight: '700',
        }}>
          {label}
        </Text>
        {count !== undefined && (
          <View style={{
            minWidth: 18, paddingHorizontal: 5,
            height: size === 'sm' ? 16 : 18,
            borderRadius: theme.radii.full,
            backgroundColor: active ? accent + '33' : theme.colors.bgSubtle,
            alignItems: 'center', justifyContent: 'center',
          }}>
            <Text style={{
              color: active ? accent : theme.colors.textDim,
              fontSize: 9, fontWeight: '800',
            }}>
              {count}
            </Text>
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
};

export default Chip;
