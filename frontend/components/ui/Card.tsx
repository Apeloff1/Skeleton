/**
 * <FeatureCard> — premium tappable card for the Menu hub and similar lists.
 *
 *  Glassy background, gradient icon halo, hot badge, accessible hit target.
 */
import React from 'react';
import { Pressable, View, Text, StyleSheet, Platform, ViewStyle, StyleProp } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import theme from '../../theme/tokens';

interface FeatureCardProps {
  title: string;
  desc?: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  hot?: boolean;
  pinned?: boolean;
  onPress: () => void;
  onLongPress?: () => void;
  testID?: string;
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
  /** width % for grid layout — '48%' default (2-col). Pass '32%' for 3-col. */
  widthPct?: string;
}

export const FeatureCard: React.FC<FeatureCardProps> = ({
  title, desc, icon, color, hot, pinned, onPress, onLongPress, testID, accessibilityLabel, style, widthPct = '48%',
}) => {
  const handlePress = () => {
    if (Platform.OS !== 'web') {
      Haptics.selectionAsync().catch(() => {});
    }
    onPress();
  };

  const handleLongPress = onLongPress
    ? () => {
        if (Platform.OS !== 'web') {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
        }
        onLongPress();
      }
    : undefined;

  return (
    <Pressable
      onPress={handlePress}
      onLongPress={handleLongPress}
      delayLongPress={380}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || title}
      style={({ pressed }) => ([
        styles.card,
        { width: widthPct as any },
        hot && { borderColor: color + '66' },
        pinned && { borderColor: '#FBBF24AA', borderWidth: 1.5 },
        pressed && { transform: [{ scale: 0.98 }], opacity: 0.92 },
        style,
      ]) as any}
    >
      {/* Subtle gradient wash on hot cards */}
      {hot && (
        <LinearGradient
          colors={[color + '22', 'transparent']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[StyleSheet.absoluteFillObject, { pointerEvents: 'none' }]}
        />
      )}
      {/* Icon halo */}
      <View style={[styles.iconHalo, { backgroundColor: color + '22', borderColor: color + '44' }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <Text style={styles.title} numberOfLines={1}>{title}</Text>
      {desc ? <Text style={styles.desc} numberOfLines={2}>{desc}</Text> : null}
      {hot && (
        <View style={[styles.hotPill, { backgroundColor: color }]}>
          <Ionicons name="star" size={9} color="#FFFFFF" />
        </View>
      )}
    </Pressable>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    minHeight: 124,
    position: 'relative',
    overflow: 'hidden',
    ...theme.elevation.xs,
  },
  iconHalo: {
    width: 38, height: 38,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    justifyContent: 'center', alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  title: {
    color: theme.colors.text,
    fontSize: 13, fontWeight: '700',
    letterSpacing: -0.1,
    marginBottom: 2,
  },
  desc: {
    color: theme.colors.textMuted,
    fontSize: 11, lineHeight: 15,
    fontWeight: '500',
    // ✨ 2026-05 polish — pin 2-line height so neighbour cards in the same
    // grid row stay perfectly aligned even when descriptions differ in
    // length. Removes the "ragged bottoms" the user flagged as messy.
    minHeight: 30,
  },
  hotPill: {
    position: 'absolute', top: 8, right: 8,
    width: 18, height: 18, borderRadius: 9,
    justifyContent: 'center', alignItems: 'center',
  },
});

export default FeatureCard;
