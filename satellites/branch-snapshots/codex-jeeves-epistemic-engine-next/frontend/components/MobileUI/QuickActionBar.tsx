/**
 * QuickActionBar Component v11.4
 * Clean, minimal action bar with power-aware animations
 */

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { memo, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Platform,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';

/** Darken a hex color toward black by `factor` (0..1) for a subtle gradient end-stop. */
function shade(hex: string, factor: number): string {
  const m = (hex || '#000').replace('#', '');
  const full = m.length === 3 ? m.split('').map((c) => c + c).join('') : m;
  const r = Math.round(parseInt(full.slice(0, 2), 16) * factor);
  const g = Math.round(parseInt(full.slice(2, 4), 16) * factor);
  const b = Math.round(parseInt(full.slice(4, 6), 16) * factor);
  return `rgb(${r}, ${g}, ${b})`;
}

interface QuickAction {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  label?: string;
  color: string;
  badge?: string | number;
  badgeColor?: string;
  onPress: () => void;
  testID?: string;
  accessibilityLabel?: string;
}

interface QuickActionBarProps {
  primaryAction: QuickAction;
  secondaryActions: QuickAction[];
  colors: any;
  reduceAnimations?: boolean;
}

export const QuickActionBar = memo(function QuickActionBar({
  primaryAction,
  secondaryActions,
  colors,
  reduceAnimations = false,
}: QuickActionBarProps) {
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (reduceAnimations) return;

    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 1.05,
          duration: 1500,
          useNativeDriver: NATIVE_DRIVER,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 1500,
          useNativeDriver: NATIVE_DRIVER,
        }),
      ])
    );
    pulse.start();

    return () => pulse.stop();
  }, [reduceAnimations, pulseAnim]);

  const handlePress = (action: QuickAction) => {
    if (Platform.OS === 'ios') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }
    action.onPress();
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* Primary Action (AI) */}
      <Animated.View style={[styles.primaryWrapper, !reduceAnimations && { transform: [{ scale: pulseAnim }] }]}>
        <TouchableOpacity
          onPress={() => handlePress(primaryAction)}
          activeOpacity={0.88}
          accessibilityRole="button"
          accessibilityLabel={primaryAction.label || primaryAction.id}
          testID={primaryAction.testID || `quick-action-${primaryAction.id}`}
          style={[styles.primaryShadow, { shadowColor: primaryAction.color }]}
        >
          <LinearGradient
            colors={[primaryAction.color, shade(primaryAction.color, 0.7)]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.primaryButton}
          >
            <View style={styles.primaryIconChip}>
              <Ionicons name={primaryAction.icon} size={17} color="#FFFFFF" />
            </View>
            {primaryAction.label && (
              <Text style={styles.primaryLabel} numberOfLines={1}>
                {primaryAction.label}
              </Text>
            )}
            {primaryAction.badge && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{primaryAction.badge}</Text>
              </View>
            )}
          </LinearGradient>
        </TouchableOpacity>
      </Animated.View>

      {/* Secondary Actions */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.secondaryScroll}
        contentContainerStyle={styles.secondaryContainer}
      >
        {secondaryActions.map((action) => (
          <TouchableOpacity
            key={action.id}
            style={[styles.secondaryButton, { backgroundColor: action.color + '15' }]}
            onPress={() => handlePress(action)}
            activeOpacity={0.7}
            accessibilityLabel={action.accessibilityLabel || action.label || action.id}
            accessibilityRole="button"
            testID={action.testID || `quick-action-${action.id}`}
          >
            <Ionicons name={action.icon} size={22} color={action.color} />
            {action.badge && (
              <View style={[styles.miniBadge, { backgroundColor: action.badgeColor || action.color }]}>
                <Text style={styles.miniBadgeText}>{action.badge}</Text>
              </View>
            )}
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  primaryWrapper: {
    flexShrink: 0,
  },
  primaryShadow: {
    borderRadius: 14,
    ...Platform.select({
      ios: { shadowOpacity: 0.32, shadowRadius: 8, shadowOffset: { width: 0, height: 3 } },
      android: { elevation: 4 },
      default: {},
    }),
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 14,
    gap: 9,
  },
  primaryIconChip: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.22)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  primaryLabel: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
    letterSpacing: 0.3,
    flexShrink: 1,
  },
  badge: {
    backgroundColor: 'rgba(255,255,255,0.24)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    marginLeft: 2,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  secondaryScroll: {
    flex: 1,
  },
  secondaryContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingRight: 4,
  },
  secondaryButton: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  miniBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  miniBadgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
  },
});
