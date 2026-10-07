/**
 * StarfallBackground
 * -------------------------------------------------------------------
 * Full-screen animated background of falling stars with subtle rotation
 * and length-trail. Pure RN Animated API — no extra deps. Renders
 * absolutely-positioned and pointerEvents='none' so it can sit underneath
 * any screen content without interfering with touch.
 *
 * 2026-02 — Android-S20 hardening:
 *   • Default streak count dropped 36 → 18. Each streak runs an infinite
 *     Animated.parallel loop with native driver; on Samsung S20 / Exynos
 *     990 the bridge starts dropping frames around 30+ concurrent loops,
 *     and StarfallBackground is decorative only.
 *   • Shadow (shadowRadius:6) dropped on Android — Android's shadow
 *     compositing is GPU-expensive (often 2-4x cost vs iOS) and gives
 *     marginal visual benefit on dark streaks.
 *   • Each streak's start callback is wrapped in try/catch so a bridge
 *     glitch can never crash the screen.
 */
import { NATIVE_DRIVER } from '../utils/platformStyles';
import React, { useEffect, useMemo, useRef } from 'react';
import { View, Animated, Easing, Dimensions, StyleSheet, Platform } from 'react-native';

interface StarfallProps {
  count?: number;        // number of streaks (default 18 — was 36)
  colorBase?: string;    // hex like '#a78bfa'
  speedMs?: [number, number]; // [min, max] fall duration
}

const { width: W, height: H } = Dimensions.get('window');

const StreakRow: React.FC<{
  x: number; delay: number; durationMs: number; size: number;
  rotate: number; opacityPeak: number; color: string;
}> = ({ x, delay, durationMs, size, rotate, opacityPeak, color }) => {
  const translateY = useRef(new Animated.Value(-60)).current;
  const opacity    = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // 2026-06 — Android-S20 hard-crash fix:
    // The previous implementation recursed via `.start(cb => loop())`,
    // which re-created an `Animated.parallel` (3+ Animated nodes) on the
    // JS thread on EVERY iteration, forever. During a long boot dwell on
    // a 520/cold-start backend, dozens of these per-streak object churns
    // accumulated native-bridge nodes and OOM-crashed the app on Exynos.
    //
    // New approach: a SINGLE native-driven `Animated.loop`. The native
    // driver runs the loop autonomously with zero per-iteration JS-thread
    // work and reuses the same animation nodes (resetBeforeIteration).
    // The initial `delay` is applied once up front for the diagonal
    // stagger, then the loop runs continuously.
    const fall = Animated.timing(translateY, {
      toValue: H + 60,
      duration: durationMs,
      easing: Easing.in(Easing.quad),
      useNativeDriver: NATIVE_DRIVER,
    });
    const fade = Animated.sequence([
      Animated.timing(opacity, { toValue: opacityPeak, duration: durationMs * 0.18, useNativeDriver: NATIVE_DRIVER }),
      Animated.timing(opacity, { toValue: opacityPeak, duration: durationMs * 0.55, useNativeDriver: NATIVE_DRIVER }),
      Animated.timing(opacity, { toValue: 0,           duration: durationMs * 0.27, useNativeDriver: NATIVE_DRIVER }),
    ]);
    const anim = Animated.sequence([
      Animated.delay(delay),
      // resetBeforeIteration (default true) snaps translateY/opacity back
      // to their initial values (-60 / 0) before each loop iteration.
      Animated.loop(Animated.parallel([fall, fade])),
    ]);
    try { anim.start(); } catch { /* bridge glitch — decorative only */ }
    return () => {
      try { anim.stop(); } catch {}
      try { translateY.stopAnimation(); } catch {}
      try { opacity.stopAnimation(); } catch {}
    };
  }, [translateY, opacity, durationMs, delay, opacityPeak]);

  return (
    <Animated.View
      style={[
        styles.streak,
        {
          left: x,
          width: size * 0.6,
          height: size * 8,
          backgroundColor: color,
          transform: [{ translateY }, { rotate: `${rotate}deg` }],
          opacity,
          ...(Platform.OS === 'web'
            // @ts-ignore — web-only style key
            ? { boxShadow: `0px 0px 6px ${color}` }
            : Platform.OS === 'ios' ? { shadowColor: color } : {}),
        },
      ]}
    />
  );
};

export const StarfallBackground: React.FC<StarfallProps> = ({
  count = 18,
  colorBase = '#a78bfa',
  speedMs = [1800, 4200],
}) => {
  // Build deterministic-per-mount streak descriptors so the layout is stable
  const streaks = useMemo(() => {
    const arr: { x: number; delay: number; dur: number; size: number; rotate: number; opacityPeak: number; color: string }[] = [];
    for (let i = 0; i < count; i++) {
      const sizeRoll = Math.random();
      arr.push({
        x: Math.random() * (W + 40) - 20,
        delay: Math.random() * 2200,
        dur: speedMs[0] + Math.random() * (speedMs[1] - speedMs[0]),
        size: 2 + sizeRoll * 3.5,
        rotate: 10 + Math.random() * 8,                  // slight diagonal
        opacityPeak: 0.35 + Math.random() * 0.55,
        color: i % 7 === 0 ? '#fcd34d' : (i % 11 === 0 ? '#93C5FD' : colorBase),
      });
    }
    return arr;
  }, [count, colorBase, speedMs]);

  return (
    <View style={[styles.container, { pointerEvents: 'none' }]}>
      {streaks.map((s, i) => (
        <StreakRow
          key={i}
          x={s.x}
          delay={s.delay}
          durationMs={s.dur}
          size={s.size}
          rotate={s.rotate}
          opacityPeak={s.opacityPeak}
          color={s.color}
        />
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    overflow: 'hidden',
  },
  streak: {
    position: 'absolute',
    top: 0,
    borderRadius: 999,
    // 2026-02 — shadow elided on Android (S20 GPU is 2-4x more expensive
    // than iOS for compositing soft shadows on small moving views).
    ...Platform.select({
      ios: {
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.9,
        shadowRadius: 6,
      },
      default: {},
    }),
  },
});

export default StarfallBackground;
