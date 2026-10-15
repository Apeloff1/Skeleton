// ============================================================================
// CODEDOCK - LOADING SCREEN COMPONENT
// ============================================================================

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, Easing } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';
import { VERSION, CODENAME } from '../../constants/config';

interface LoadingScreenProps {
  colors: ThemeColors;
  message?: string;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ colors, message }) => {
  const rotateAnim = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Rotate animation
    Animated.loop(
      Animated.timing(rotateAnim, {
        toValue: 1,
        duration: 2000,
        easing: Easing.linear,
        useNativeDriver: NATIVE_DRIVER,
      })
    ).start();

    // Pulse animation
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.1, duration: 800, useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: NATIVE_DRIVER }),
      ])
    ).start();

    // Fade in
    Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: NATIVE_DRIVER }).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rotation = rotateAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Animated.View style={[styles.container, { backgroundColor: colors.background, opacity: fadeAnim }]}>
      <Animated.View style={[styles.logoContainer, { transform: [{ scale: pulseAnim }] }]}>
        <View style={[styles.logoBg, { backgroundColor: colors.primary + '20' }]}>
          <Animated.View style={{ transform: [{ rotate: rotation }] }}>
            <Ionicons name="code-slash" size={48} color={colors.primary} />
          </Animated.View>
        </View>
      </Animated.View>
      
      <Text style={[styles.title, { color: colors.text }]}>CodeDock Quantum</Text>
      <Text style={[styles.subtitle, { color: colors.textMuted }]}>{CODENAME} v{VERSION}</Text>
      
      <View style={styles.loadingContainer}>
        <Animated.View style={[styles.loadingBar, { backgroundColor: colors.surfaceAlt }]}>
          <Animated.View 
            style={[
              styles.loadingProgress, 
              { backgroundColor: colors.primary, transform: [{ scaleX: pulseAnim }] }
            ]} 
          />
        </Animated.View>
        <Text style={[styles.loadingText, { color: colors.textMuted }]}>
          {message || 'Initializing quantum compiler...'}
        </Text>
      </View>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  logoContainer: {
    marginBottom: 24,
  },
  logoBg: {
    width: 100,
    height: 100,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 14,
    marginTop: 4,
  },
  loadingContainer: {
    marginTop: 48,
    width: '60%',
    alignItems: 'center',
  },
  loadingBar: {
    width: '100%',
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
  },
  loadingProgress: {
    width: '50%',
    height: '100%',
    borderRadius: 2,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 12,
  },
});

export default LoadingScreen;
