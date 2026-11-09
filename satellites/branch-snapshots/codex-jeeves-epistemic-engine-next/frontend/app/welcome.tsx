/**
 * Welcome — First-launch animated splash with starfall background.
 * Sits at /welcome route. Auto-redirects to / after 4s OR on tap.
 * AsyncStorage flag prevents re-display on subsequent app opens.
 */
import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React, { useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, Animated, Easing, StyleSheet,
  StatusBar, Platform, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { safeSetItem } from '../utils/safeStorage';

const WELCOME_FLAG_KEY = '@codedock:welcome_seen:v1';

// Lazy-load Starfall via require so a starfall parse error doesn't kill
// the whole welcome route — the catch falls back to a static gradient.
let StarfallBackground: React.ComponentType<any> | null = null;
try {
   
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  StarfallBackground = require('../src/components/StarfallBackground').StarfallBackground;
} catch {
  StarfallBackground = null;
}

export default function WelcomeScreen() {
  const router = useRouter();
  const titleOpacity = useRef(new Animated.Value(0)).current;
  const titleScale   = useRef(new Animated.Value(0.9)).current;
  const subOpacity   = useRef(new Animated.Value(0)).current;
  const btnOpacity   = useRef(new Animated.Value(0)).current;
  const btnFloat     = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Staggered entrance — wrapped in try/catch so animation init never
    // crashes the screen (which would leave the user stuck).
    try {
      Animated.sequence([
        Animated.delay(200),
        Animated.parallel([
          Animated.timing(titleOpacity, { toValue: 1, duration: 900, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE_DRIVER }),
          Animated.spring(titleScale,   { toValue: 1, friction: 7, tension: 60, useNativeDriver: NATIVE_DRIVER }),
        ]),
        Animated.timing(subOpacity, { toValue: 1, duration: 700, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(btnOpacity, { toValue: 1, duration: 600, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE_DRIVER }),
      ]).start();
    } catch {
      // Animations failed — force all values to visible state so the
      // screen renders something usable.
      titleOpacity.setValue(1);
      titleScale.setValue(1);
      subOpacity.setValue(1);
      btnOpacity.setValue(1);
    }

    // Gentle floating button
    let float: Animated.CompositeAnimation | null = null;
    try {
      float = Animated.loop(
        Animated.sequence([
          Animated.timing(btnFloat, { toValue: 1, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
          Animated.timing(btnFloat, { toValue: 0, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE_DRIVER }),
        ])
      );
      float.start();
    } catch {/* swallow */}

    // Auto-advance safety net: if user hasn't tapped in 6 s, go to hub
    // anyway. Prevents being stuck on a frozen welcome screen.
    const auto = setTimeout(() => {
      handleEnter();
    }, 6000);

    return () => {
      try { float?.stop(); } catch {}
      clearTimeout(auto);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [titleOpacity, titleScale, subOpacity, btnOpacity, btnFloat]);

  const handleEnter = async () => {
    // safeSetItem has a 800ms hard timeout — never blocks navigation.
    try { await safeSetItem(WELCOME_FLAG_KEY, '1'); } catch { /* ignore */ }
    try { router.replace('/hub'); } catch {/* swallow */}
  };

  const btnTranslateY = btnFloat.interpolate({ inputRange: [0, 1], outputRange: [0, -4] });

  return (
    <Pressable onPress={handleEnter} style={styles.fill}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <View style={styles.bg}>
        {StarfallBackground ? (
          <StarfallBackground colorBase="#a78bfa" speedMs={[2200, 4800]} />
        ) : null}
      </View>

      <View style={[styles.content, { pointerEvents: 'box-none' }]}>
        <Animated.View
          style={[
            styles.titleRow,
            { opacity: titleOpacity, transform: [{ scale: titleScale }] },
          ]}
        >
          <Ionicons name="planet-outline" size={36} color="#a78bfa" style={{ marginRight: 12 }} />
          <Text style={styles.title}>CodeDock</Text>
        </Animated.View>

        <Animated.Text style={[styles.tagline, { opacity: titleOpacity }]}>
          Quantum Nexus
        </Animated.Text>

        <Animated.Text style={[styles.subtitle, { opacity: subOpacity }]}>
          Hyperscale game-build factory · 600K+ knowledge assets · live RAG
        </Animated.Text>

        <Animated.View
          style={[
            styles.btnWrap,
            { opacity: btnOpacity, transform: [{ translateY: btnTranslateY }] },
          ]}
        >
          <TouchableOpacity style={styles.btn} onPress={handleEnter} activeOpacity={0.8}>
            <Text style={styles.btnText}>Enter the Hub</Text>
            <Ionicons name="arrow-forward-outline" size={18} color="#fff" style={{ marginLeft: 8 }} />
          </TouchableOpacity>
          <Text style={styles.tapHint}>tap anywhere to continue</Text>
        </Animated.View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#0A0A0A' },
  bg:   { ...StyleSheet.absoluteFillObject },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  title: {
    color: '#fff',
    fontSize: 42,
    fontWeight: '900',
    letterSpacing: -1.2,
    ...(Platform.OS === 'web' ? {
      // @ts-ignore — web-only style key
      textShadow: '0px 0px 12px #a78bfa88',
    } : {
      textShadowColor: '#a78bfa88',
      textShadowOffset: { width: 0, height: 0 },
      textShadowRadius: 12,
    }),
  },
  tagline: {
    color: '#a78bfa',
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 4,
    textTransform: 'uppercase',
    marginBottom: 28,
  },
  subtitle: {
    color: '#d1d5db',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 320,
    marginBottom: 56,
  },
  btnWrap: { alignItems: 'center' },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#8B5CF6',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 999,
    ...(Platform.OS === 'web' ? {
      // @ts-ignore — web-only style key
      boxShadow: '0px 6px 18px rgba(124, 58, 237, 0.6)',
    } : {
      shadowColor: '#8B5CF6',
      shadowOpacity: 0.6,
      shadowRadius: 18,
      shadowOffset: { width: 0, height: 6 },
      elevation: 8,
    }),
  },
  btnText: { color: '#fff', fontSize: 15, fontWeight: '800', letterSpacing: 0.5 },
  tapHint: {
    marginTop: 16,
    color: '#9ca3af',
    fontSize: 11,
    fontStyle: 'italic',
    letterSpacing: 0.5,
  },
});
