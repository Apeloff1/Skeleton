/**
 * Achievement Notification Component v12.0
 * 
 * Displays animated achievement pop-ups when users earn new achievements.
 * Integrates with the Synergy API for real-time achievement tracking.
 */

import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  TouchableOpacity,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';


export interface Achievement {
  id: string;
  name: string;
  description?: string;
  xp: number;
  icon?: string;
  tier?: 'bronze' | 'silver' | 'gold' | 'platinum';
}

interface AchievementNotificationProps {
  achievement: Achievement | null;
  onDismiss: () => void;
  colors: any;
}

const TIER_COLORS = {
  bronze: '#CD7F32',
  silver: '#C0C0C0',
  gold: '#FFD700',
  platinum: '#E5E4E2',
};

const TIER_ICONS = {
  bronze: 'medal-outline',
  silver: 'medal',
  gold: 'trophy',
  platinum: 'diamond',
};

export const AchievementNotification: React.FC<AchievementNotificationProps> = ({
  achievement,
  onDismiss,
  colors,
}) => {
  const slideAnim = useRef(new Animated.Value(-200)).current;
  const scaleAnim = useRef(new Animated.Value(0.8)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (achievement) {
      setVisible(true);
      
      // Haptic feedback
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }

      // Entrance animation
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: 0,
          useNativeDriver: NATIVE_DRIVER,
          tension: 50,
          friction: 8,
        }),
        Animated.spring(scaleAnim, {
          toValue: 1,
          useNativeDriver: NATIVE_DRIVER,
          tension: 50,
          friction: 6,
        }),
      ]).start();

      // Glow animation loop
      Animated.loop(
        Animated.sequence([
          Animated.timing(glowAnim, {
            toValue: 1,
            duration: 1000,
            useNativeDriver: NATIVE_DRIVER,
          }),
          Animated.timing(glowAnim, {
            toValue: 0,
            duration: 1000,
            useNativeDriver: NATIVE_DRIVER,
          }),
        ])
      ).start();

      // Auto-dismiss after 5 seconds
      const timer = setTimeout(() => {
        handleDismiss();
      }, 5000);

      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [achievement]);

  const handleDismiss = () => {
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: -200,
        duration: 300,
        useNativeDriver: NATIVE_DRIVER,
      }),
      Animated.timing(scaleAnim, {
        toValue: 0.8,
        duration: 300,
        useNativeDriver: NATIVE_DRIVER,
      }),
    ]).start(() => {
      setVisible(false);
      onDismiss();
    });
  };

  if (!visible || !achievement) return null;

  const tier = achievement.tier || 'bronze';
  const tierColor = TIER_COLORS[tier];
  const tierIcon = TIER_ICONS[tier] as keyof typeof Ionicons.glyphMap;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: colors.surface,
          borderColor: tierColor,
          transform: [
            { translateY: slideAnim },
            { scale: scaleAnim },
          ],
        },
      ]}
    >
      {/* Glow effect */}
      <Animated.View
        style={[
          styles.glowEffect,
          {
            backgroundColor: tierColor,
            opacity: glowAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [0.1, 0.3],
            }),
          },
        ]}
      />

      <TouchableOpacity
        style={styles.content}
        onPress={handleDismiss}
        activeOpacity={0.9}
      >
        {/* Icon */}
        <View style={[styles.iconContainer, { backgroundColor: tierColor + '30' }]}>
          <Ionicons name={tierIcon} size={32} color={tierColor} />
        </View>

        {/* Text content */}
        <View style={styles.textContainer}>
          <Text style={[styles.title, { color: tierColor }]}>
            🎉 Achievement Unlocked!
          </Text>
          <Text style={[styles.name, { color: colors.text }]}>
            {achievement.name}
          </Text>
          {achievement.description && (
            <Text style={[styles.description, { color: colors.textMuted }]}>
              {achievement.description}
            </Text>
          )}
          <View style={styles.xpContainer}>
            <Ionicons name="star" size={14} color="#FFD700" />
            <Text style={[styles.xp, { color: '#FFD700' }]}>
              +{achievement.xp} XP
            </Text>
          </View>
        </View>

        {/* Close button */}
        <TouchableOpacity style={styles.closeButton} onPress={handleDismiss}>
          <Ionicons name="close" size={20} color={colors.textMuted} />
        </TouchableOpacity>
      </TouchableOpacity>

      {/* Progress bar */}
      <Animated.View
        style={[
          styles.progressBar,
          {
            backgroundColor: tierColor,
            width: glowAnim.interpolate({
              inputRange: [0, 1],
              outputRange: ['100%', '0%'],
            }),
          },
        ]}
      />
    </Animated.View>
  );
};

// Achievement queue manager for multiple achievements
interface AchievementQueueProps {
  achievements: Achievement[];
  onClear: () => void;
  colors: any;
}

export const AchievementQueue: React.FC<AchievementQueueProps> = ({
  achievements,
  onClear,
  colors,
}) => {
  const [currentIndex, setCurrentIndex] = useState(0);

  const handleDismiss = () => {
    if (currentIndex < achievements.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setCurrentIndex(0);
      onClear();
    }
  };

  if (achievements.length === 0) return null;

  return (
    <AchievementNotification
      achievement={achievements[currentIndex]}
      onDismiss={handleDismiss}
      colors={colors}
    />
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 60,
    left: 16,
    right: 16,
    borderRadius: 16,
    borderWidth: 2,
    overflow: 'hidden',
    elevation: 10,
    zIndex: 1000,
  },
  glowEffect: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  iconContainer: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  textContainer: {
    flex: 1,
  },
  title: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 2,
  },
  name: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 2,
  },
  description: {
    fontSize: 12,
    marginBottom: 4,
  },
  xpContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  xp: {
    fontSize: 14,
    fontWeight: '600',
  },
  closeButton: {
    padding: 8,
  },
  progressBar: {
    height: 3,
  },
});

export default AchievementNotification;
